from enum import Flag
import json
from operator import le
import frappe
import datetime
import re

def fetch_customer_type(customer):
    customer_group = frappe.db.sql(
        f"""SELECT customer_group FROM `tabCustomer` WHERE name = '{customer}'""",
        as_dict=True
    )
    customer_type = frappe.db.sql(
        f"""SELECT pch_customer_type FROM `tabCustomer Group` WHERE name = '{customer_group[0]["customer_group"]}'""",
        as_dict=True
    )
    return customer_type[0]

def fetch_stock_details(item_code, customer_type, settings):
    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]
    
    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))

    stock_data_batch = frappe.db.sql(f"""
		select batch_id, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
		from `tabBatch`
			join `tabStock Ledger Entry` ignore index (item_code, warehouse)
				on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
		where `tabStock Ledger Entry`.item_code = '{item_code}' AND warehouse in {warehouse}
			and `tabStock Ledger Entry`.is_cancelled = 0
		group by batch_id
		order by `tabBatch`.creation ASC
	""", as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code = '{item_code}' and warehouse in {warehouse} and (batch_no is null or batch_no = '')""",
        as_dict=True
    )
    
    print("done price")
    for data in stock_data_batchless:
        if data["actual_qty"] == None: continue
        stock_data_batch.append(data)
    print(stock_data_batch)
    return stock_data_batch

def fetch_item_details(item_code, customer_type, settings):
    stock_detail = fetch_stock_details(item_code, customer_type, settings)
    return stock_detail

def available_stock_details(item_code, customer_type, settings):
    today = datetime.date.today()

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]

    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))
       
    stock_data_batch = frappe.db.sql(f"""
            select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code = '{item_code}' AND warehouse in {warehouse}
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC, warehouse DESC
        """, as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code = '{item_code}' and warehouse in {warehouse} and (batch_no is null or batch_no = '')
        group by item_code, warehouse""",
        as_dict=True
    )

    sales_data = frappe.db.sql(
        f"""select sum(soi.qty - soi.delivered_qty) as pending_qty
        from `tabSales Order Item` as soi
            join `tabSales Order` as so on (soi.parent = so.name)
        where soi.docstatus < 2 and soi.item_code = '{item_code}' and soi.warehouse in {warehouse} and so.pch_picking_status != ''""", as_dict=True
    )
    
    print("expiry limit", settings["expiry_date_limit"])
    batch_total = 0
    for batch_info in stock_data_batch:
        if batch_info["expiry_date"] is not None: 
            date_delta = batch_info["expiry_date"] - today
            if date_delta.days < settings["expiry_date_limit"]: continue
            print("batch expiry", date_delta.days, "qty", batch_info["actual_qty"])
        batch_total += batch_info["actual_qty"]

    batchless_total = sum(data["actual_qty"] for data in stock_data_batchless)
    print("batch", batch_total)
    print("batchless", batchless_total)
    try:
        available_qty = batch_total + batchless_total - sales_data[0]["pending_qty"]
    except:
        available_qty = batch_total + batchless_total

    return dict(available_qty = available_qty, sales_qty = sales_data[0]["pending_qty"])

def fetch_average_price(stock_data, item_code):
    average_price_list = []
    average_qty_list = []
    average_price = 0
    stock_count = 0
    for data in stock_data:
        print("*"*20)
        print(item_code)
        print(data)
        try:
            average_qty_list.append(data["actual_qty"])
        except:
            pass
        if data["batch_id"] == '':
            print("None")
            price_list = frappe.db.sql(
                f"""SELECT price_list_rate FROM `tabItem Price` WHERE (batch_no IS NULL or batch_no = '') AND item_code = '{item_code}'""",
                as_dict=True
            )
            print("price list", price_list)
            try:
                average_price += price_list[0]["price_list_rate"] * data["actual_qty"]
                average_price_list.append(price_list[0]["price_list_rate"])
                stock_count += data["actual_qty"]
            except:
                pass
        else:
            price_list = frappe.db.sql(
                f"""SELECT price_list_rate FROM `tabItem Price` WHERE batch_no = '{data["batch_id"]}' AND item_code = '{item_code}'""",
                as_dict=True
            )
            try:
                average_price += price_list[0]["price_list_rate"] * data["actual_qty"]
                stock_count += data["actual_qty"]
                average_price_list.append(price_list[0]["price_list_rate"])
            except:
                price_list = frappe.db.sql(
                f"""SELECT price_list_rate FROM `tabItem Price` WHERE batch_no IS NULL AND item_code = '{item_code}'""",
                as_dict=True
                )
                try:
                    average_price += price_list[0]["price_list_rate"] * data["actual_qty"]
                    stock_count += data["actual_qty"]
                    average_price_list.append(price_list[0]["price_list_rate"])
                except:
                    pass

    if stock_count > 0:
        return dict(average_price = average_price/stock_count, price_list = average_price_list, qty_list = average_qty_list)
    else:
        return dict(average_price = average_price, price_list = average_price_list, qty_list = average_qty_list)

def fetch_fulfillment_settings(company):
    fs_name = frappe.db.sql(
        f"""SELECT name, expiry_date_limit FROM `tabFulfillment Settings V1` WHERE company = '{company}'""",
        as_dict=True
    )
    if fs_name:
        settings = frappe.db.sql(
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse, free_warehouse
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )
        settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
    else:
        settings = [None]
    return settings



# Available Qty for Promo
def available_stock_details_for_promos(item_code, customer_type, settings, expiry_date):
    print("item_code", item_code)
    today = datetime.date.today()
    stock_promo = []
    i = [x["item_code"] for x in item_code]
    i = re.sub(',\)$', ')', str(tuple(i)))
    
    print("Item",i)
      
    stock_data_batch = frappe.db.sql(f"""
            select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code in {i} AND warehouse = '{settings}'
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC, warehouse DESC
        """, as_dict=True)
    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code in {i} and warehouse = '{settings}' and (batch_no is null or batch_no = '')
        group by item_code, warehouse""",
        as_dict=True
    )

    stock_promo.extend(stock_data_batch)
    stock_promo.extend(stock_data_batchless)
    # print("Stock_promos")
    available_qty = {}
    for batch_info in stock_promo:
        try :
            if batch_info["expiry_date"] is not None: 
                date_delta = batch_info["expiry_date"] - today
                if date_delta.days < expiry_date: continue
                available_qty[batch_info["item_code"]] = available_qty.get(batch_info["item_code"], 0) + batch_info["actual_qty"]
        except: 
            available_qty[batch_info["item_code"]] = available_qty.get(batch_info["item_code"], 0) + batch_info["actual_qty"]
    # print(type(available_qty))
    return available_qty

#Rate Contract
def fetch_rate_contract(customer, item_code):
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
    rate_data = []
    print("item_code....",item_code)
    rate = frappe.db.sql (f""" select rti.item, rti.selling_price_for_customer, rti.discount_percentage_for_customer_from_mrp, rt.customer
    from `tabRate Contract Item` as rti
        inner join `tabRate Contract` as rt on rt.name = rti.parent
    where rti.item in {i} and rt.customer = '{customer}'
    group by rti.item
        """, as_dict = True)

    for i in range (len(rate)):
        for j in range (len(item_code)):
            if rate[i]["item"] == item_code[j]["item_code"]:
                rate_data.append({ "promo_type": "Rate Contract", "qty":item_code[j]["quantity_booked"], "bought_item": rate[i]["item"], "rate": rate[i]["selling_price_for_customer"], "dic" : rate[i]["discount_percentage_for_customer_from_mrp"], "w_qty" : item_code[j]["quantity_available"]})

    print("return vale....",rate_data)
    return rate_data      
    
# Buy x get same x
def fetch_sales_promos_get_same_item(item_code, customer_type, free_warehouse, expiry_date):
    promo_type = "Buy x get same x"
    sales_promos_quantity = []
    promos_sale = []
    sales_data = None
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
    print("Item",i)
    
    today = datetime.date.today()
    promos = frappe.db.sql (f""" select sp.start_date, sp.end_date, 
        pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
        pt.bought_item
        from  `tabSales Promos` as sp  
            inner join `tabPromo Type 2` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse = '{free_warehouse}'
        group by sle.item_code
        """, as_dict = True)
    
    print("promos......", promos)
    if len(promos) > 0:
        for i in range (len(promos)):
            if promos[i].get("start_date") is None: continue
            if(promos[i]["start_date"] <= today <= promos[i]["end_date"]): 
                for j in item_code:
                    if promos[i]["bought_item"] == j["item_code"]:
                        sales_data = frappe.db.sql(
                        f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{promos[i]["bought_item"]}' and warehouse = '{free_warehouse}'""", as_dict=True
                        )

                        print("sales", sales_data)
                        promo_qty = available_stock_details_for_promos(item_code, customer_type, free_warehouse, expiry_date)
                        print("Promo qty",promo_qty[promos[i]["bought_item"]])
                       
                        try:
                            if sales_data[0].get("pending_qty") is None: 
                                qty = promo_qty[promos[i]["bought_item"]]
                            else:
                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["bought_item"]]:
                                    qty =  promo_qty[promos[i]["bought_item"]] - sales_data[0]["pending_qty"]
                                else:
                                    continue
                        except:
                            qty = promo_qty[promos[i]["bought_item"]]
                        
                        sales_promos_details = ((j["quantity_booked"])//(promos[i]["for_every_quantity_that_is_bought"]))
                        sales_promos_quantity = sales_promos_details*((promos[i]["quantity_of_free_items_thats_given"]))

                        print("Wty........",qty)

                        print("Pty...........", sales_promos_quantity)
                        try:
                            if sales_promos_quantity <= qty:
                                sales_promos_quantity = sales_promos_quantity
        
                            else:
                                sales_promos_quantity = qty

                        except:
                            qty = promo_qty[promos[i]["bought_item"]]

                        promos_sale.append({"promo_type": promo_type  , "qty":sales_promos_quantity, "bought_item":promos[i]["bought_item"], "dic": "0", "rate": 0.0 , "promo_item": promos[i]["bought_item"], "w_qty" : qty})
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})
  

# buy x get another y item
def fetch_sales_promos_get_diff_item(item_code, customer_type, free_warehouse, expiry_date):
    promo_type = "Buy x get another y item"
    sales_promos_quantity = []
    print("freeware", free_warehouse)
    promos_sale = []
    free_items = []
    sales_data = None
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
    today = datetime.date.today()
    # if customer_type == "Retail":
    promos = frappe.db.sql (f""" select sp.start_date, sp.end_date, 
        pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
        pt.bought_item, pt.free_item
        from  `tabSales Promos` as sp  
            inner join `tabPromo Type 3` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.free_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse = '{free_warehouse}'
        group by sle.item_code
        """, as_dict = True)
    # print("......", promos)
    if len(promos) > 0:
        for i in range (len(promos)):
            if promos[i].get("start_date") is None: continue
            if(promos[i]["start_date"] <= today <= promos[i]["end_date"]): 
                for j in item_code:
                    if promos[i]["bought_item"] == j["item_code"]:
                        sales_data = frappe.db.sql(
                        f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{promos[i]["free_item"]}' and warehouse = '{free_warehouse}'""", as_dict=True
                        )
                        sales_promos_details = ((j["quantity_booked"])//(promos[i]["for_every_quantity_that_is_bought"]))
                        sales_promos_quantity = sales_promos_details*((promos[i]["quantity_of_free_items_thats_given"]))

                        promo_qty = available_stock_details_for_promos(item_code, customer_type, free_warehouse, expiry_date)

                        try:
                            if sales_data[0].get("pending_qty") is None: 
                                qty = promo_qty[promos[i]["bought_item"]]
                            else:
                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["bought_item"]]:
                                    qty =  promo_qty[promos[i]["bought_item"]] - sales_data[0]["pending_qty"]
                                else:
                                    continue
                        except:
                            qty = promo_qty[promos[i]["bought_item"]]


                        try:
                            if sales_promos_quantity <= qty:
                                sales_promos_quantity = sales_promos_quantity
                            else:
                                sales_promos_quantity = qty

                        except:
                            qty = promo_qty[promos[i]["bought_item"]]

                        promos_sale.append({"promo_type": promo_type, "qty" : sales_promos_quantity, "bought_item":promos[i]["bought_item"], "dic": "0", "rate": 0.0 ,"promo_item" : promos[i]["free_item"], "w_qty" : qty})
                        print("sales qunt diif", sales_promos_quantity)
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

# buy x get same and discount for ineligible qty
def fetch_sales_promos_get_same_item_discout(item_code, customer_type, free_warehouse, expiry_date):
    promo_type = "Buy x get same and discount for ineligible qty"
    sales_promos_quantity = []
    promos_sale = []
    sales_data = None
    # sales_promo_discount = []
    i = [x["item_code"] for x in item_code]
    i = re.sub(',\)$', ')', str(tuple(i)))
    # warehouse = re.sub(',\)$', ')', str(tuple(free_warehouse)))
    today = datetime.date.today()
    # if customer_type == "Retail":
    query = (f""" select sp.start_date, sp.end_date, 
        pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
        pt.bought_item, pt.discount
        from  `tabSales Promos` as sp  
            inner join `tabPromo Type 5` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse  = '{free_warehouse}'
        group by sle.item_code
        """)
    promos = frappe.db.sql ( query, as_dict = True)
    # print("promos......", promos)
    print(promos)
    if len(promos) > 0:
        for i in range (len(promos)):
            if promos[i].get("start_date") is None: continue
            if(promos[i]["start_date"] <= today <= promos[i]["end_date"]): 
                for j in item_code:
                    if promos[i]["bought_item"] == j["item_code"]:
                        sales_data = frappe.db.sql(
                        f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{promos[i]["bought_item"]}' and warehouse = '{free_warehouse}'""", as_dict=True
                        )
                        sales_promos_dic = ((j["quantity_booked"])%(promos[i]["for_every_quantity_that_is_bought"]))
                        print("dicount", sales_promos_dic)
                        sales_promo_discount = j["average_price"] * (100 - promos[i]["discount"])/100
                        sales_promos_details = ((j["quantity_booked"])//(promos[i]["for_every_quantity_that_is_bought"]))
                        sales_promos_quantity = sales_promos_details*((promos[i]["quantity_of_free_items_thats_given"]))
                        sales_promo_amount = sales_promos_dic * sales_promo_discount
                        
                        promo_qty = available_stock_details_for_promos(item_code, customer_type, free_warehouse, expiry_date)

                        try:
                            if sales_data[0].get("pending_qty") is None: 
                                qty = promo_qty[promos[i]["bought_item"]]
                            else:
                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["bought_item"]]:
                                    qty =  promo_qty[promos[i]["bought_item"]] - sales_data[0]["pending_qty"]
                                else:
                                    continue
                        except:
                            qty = promo_qty[promos[i]["bought_item"]]

                        try:
                            if sales_promos_quantity <= qty:
                                sales_promos_quantity = sales_promos_quantity
                            else:
                                sales_promos_quantity = qty

                        except:
                            qty = promo_qty[promos[i]["bought_item"]]
                         
                        promos_sale.append({ "promo_type": promo_type,"qty":sales_promos_quantity, "dic_qty": sales_promos_dic, "dic":sales_promo_discount,"rate": 0.0 , "bought_item":promos[i]["bought_item"], "promo_item": promos[i]["bought_item"], "w_qty" : qty, "amount":sales_promo_amount })
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

# Qty based discount
def fetch_sales_promos_qty_based_discount(item_code, customer_type, free_warehouse, expiry_date):
    promo_type = "Amount based discount"
    promos_sale = []
    sales_data = None
    data = []
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
    today = datetime.date.today()
    # if customer_type == "Retail":
    promos = frappe.db.sql (f""" select sp.start_date, sp.end_date, 
            pt.quantity_bought, pt.discount_percentage,
            pt.bought_item
            from  `tabSales Promos` as sp  
                inner join `tabPromo Type 1` as pt on pt.parent = sp.name
                inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse = '{free_warehouse}' group by pt.discount_percentage
        """, as_dict = True)
    data.append(promos)
    for item in item_code:
        qty_booked = item["quantity_booked"]
        amt = item["amount"]
        print(".....", qty_booked, amt)

    seen = []
    sales_promo_discount = None

    if len(promos) > 0:
        for i in range ((len(promos) -1), -1, -1):
            print()
            if promos[i]["bought_item"] in seen:
                continue
            seen.append(promos[i]["bought_item"])
            print("IIIII", i)
            if promos[i].get("start_date") is None: continue
            if(promos[i]["start_date"] <= today <= promos[i]["end_date"]): 
                for j in item_code:
                    if promos[i]["bought_item"] == j["item_code"]:
                        sales_data = frappe.db.sql(
                        f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{promos[i]["bought_item"]}' and warehouse = '{free_warehouse}'""", as_dict=True
                        )
                        # qty_booked = item_code[0].get("")
                        dis = promos[i].get("discount_percentage")
                        print("dis....", dis)
                        print(j["amount"], j["quantity_booked"], j["item_code"] )
                        for l in range ((len(promos) -1), -1, -1): 
                            print("per......", promos[l]["discount_percentage"] )
                            if j["quantity_booked"] >= promos[l]["quantity_bought"]:
                                sales_promo_discount = j["average_price"] * (100 - promos[i]["discount_percentage"])/100
                                print("..",sales_promo_discount)
                                break
                        promo_qty = available_stock_details_for_promos(item_code, customer_type, free_warehouse, expiry_date)

                        
                        try:
                            if sales_data[0].get("pending_qty") is None: 
                                qty = promo_qty[promos[i]["bought_item"]]
                            else:
                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["bought_item"]]:
                                    qty =  promo_qty[promos[i]["bought_item"]] - sales_data[0]["pending_qty"]
                                else:
                                    continue
                        except:
                            qty = promo_qty[promos[i]["bought_item"]]

                        try:
                            if sales_promos_quantity <= qty:
                                sales_promos_quantity = sales_promos_quantity
                            else:
                                sales_promos_quantity = qty
                        except:
                            qty = promo_qty[promos[i]["bought_item"]]
                         
                        promos_sale.append({"promo_type": promo_type, "qty": 0 , "dic":sales_promo_discount, "dic_qty": j["quantity_booked"], "rate": 0.0 , "bought_item":promos[i]["bought_item"], "promo_item": promos[i]["bought_item"] , "w_qty" : qty})
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

def sales_order_calculation(sales_promo_discounted_amount, sales_promos_items, order_list, warehouse, free_warehouse, rate_contract):
    promo_sales_order= []
    
    flag = True
    if len(sales_promo_discounted_amount)> 0:
        for i in range (len(order_list)):

            print("len", len(order_list))
            print("...iiiiii........1", order_list[i]["item_code"], order_list[i]["quantity_booked"])
            for j in range (len(sales_promo_discounted_amount)):
                print("jjjjj.......1", sales_promo_discounted_amount[j]["bought_item"])
                if order_list[i]["quantity_booked"] != sales_promo_discounted_amount[j]["dic_qty"]:
                    print("iiiiiii....2",i, j)
                    if order_list[i]["item_code"] == sales_promo_discounted_amount[j]["promo_item"]:
                        print("iiiiiii....2",i, j)
                        order_list[i]["quantity_booked"] = order_list[i]["quantity_booked"] - sales_promo_discounted_amount[j]["dic_qty"]
                        promo_sales_order.append({"item_code":order_list[i]["item_code"], "qty": order_list[i]["quantity_booked"], "average_price": order_list[i]["average_price"], "warehouse" : warehouse, "qty_available":order_list[i]["quantity_available"], "promo_type" : "None"})
                    # else:
                    #     promo_sales_order.append({"item_code":order_list[i]["item_code"], "qty": order_list[i]["quantity_booked"], "average_price": order_list[i]["average_price"], "warehouse" : warehouse, "qty_available":order_list[i]["quantity_available"], "promo_type" : "None"})
                else:
                    print("iiiiiii....3",i, j)

                    if order_list[i]["quantity_booked"] == sales_promo_discounted_amount[j]["dic_qty"] and order_list[i]["item_code"] == sales_promo_discounted_amount[j]["promo_item"]:
                        print("iiiiiii....4",i, j)
                        flag = False
                        print("iiiiiii....4",i, j)
                    else:
                        promo_sales_order.append({"item_code":order_list[i]["item_code"], "qty": order_list[i]["quantity_booked"], "average_price": order_list[i]["average_price"], "warehouse" : warehouse, "promo_type": "None", "qty_available":order_list[i]["quantity_available"]})
            # print(".......Promosalesorder", promo_sales_order)
    else:
        print("...........iiiiiiiii")
        for i in range (len(order_list)):
            promo_sales_order.append({"item_code":order_list[i]["item_code"], "qty": order_list[i]["quantity_booked"], "average_price": order_list[i]["average_price"], "warehouse" : warehouse, "promo_type": "None", "qty_available":order_list[i]["quantity_available"]})

    for s in range (len(sales_promo_discounted_amount)):
        for i in range(len(order_list)):
            if order_list[i]["item_code"] == sales_promo_discounted_amount[j]["promo_item"]:
                promo_sales_order.append({"item_code":sales_promo_discounted_amount[s]["promo_item"], "qty": sales_promo_discounted_amount[s]["dic_qty"], "average_price": sales_promo_discounted_amount[s]["dic"], "warehouse" : warehouse , "promo_type": sales_promo_discounted_amount[s]["promo_type"], "qty_available": sales_promo_discounted_amount[s]["w_qty"]})
                print(".......promodis", promo_sales_order)
    
    for j in range (len(rate_contract)):
        for i in range (len(order_list)):
            if order_list[i]["item_code"] == rate_contract[j]["bought_item"]:
                promo_sales_order.append({"item_code": rate_contract[j]["bought_item"], "qty":rate_contract[j]["qty"], "average_price": rate_contract[j]["rate"], "warehouse" : warehouse, "promo_type": "Rate Contract", "qty_available": rate_contract[j]["w_qty"]})
    
    for l in range (len(sales_promos_items)):
        promo_sales_order.append({"item_code":sales_promos_items[l]["promo_item"], "qty": sales_promos_items[l]["qty"], "average_price": sales_promos_items[l]["rate"], "warehouse" : free_warehouse, "promo_type": sales_promos_items[l]["promo_type"], "qty_available": sales_promos_items[l]["w_qty"]})

        print("........promosales", promo_sales_order)

    return dict({"sales_order" : promo_sales_order})

    
@frappe.whitelist()
def fulfillment_settings_container(company):
    fulfillment_settings = fetch_fulfillment_settings(company)
    return fulfillment_settings[0]

@frappe.whitelist()
def customer_type_container(customer):
    customer_type = fetch_customer_type(customer)
    return customer_type

@frappe.whitelist()
def sales_promos(item_code, customer_type, company, order_list, customer):
    item_code = json.loads(item_code)
    order_list= json.loads(order_list)
    rate_contract = fetch_rate_contract(customer, item_code)
    settings = fetch_fulfillment_settings(company)
    promos_qty = available_stock_details_for_promos(item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
    sales_promos_same_item = fetch_sales_promos_get_same_item(item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
    sales_promo_diff_items = fetch_sales_promos_get_diff_item(item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
    sales_promo_discount = fetch_sales_promos_get_same_item_discout(item_code, customer_type, settings[0]["free_warehouse"],  settings[0]["expiry_date_limit"])
    sales_promo_quantity_discount = fetch_sales_promos_qty_based_discount(item_code, customer_type, settings[0]["free_warehouse"],  settings[0]["expiry_date_limit"])
    sales_promo_discounted_amount = sales_promo_discount["Promo_sales"] + sales_promo_quantity_discount["Promo_sales"]
    sales_promos_items = sales_promos_same_item["Promo_sales"] + sales_promo_diff_items["Promo_sales"] + sales_promo_discount["Promo_sales"]
    sales_order = sales_order_calculation(sales_promo_discounted_amount, sales_promos_items, order_list, settings[0]["retail_primary_warehouse"], settings[0]["free_warehouse"], rate_contract)
  
    

    return dict( rate_contract=rate_contract, sales_order = sales_order,sales_promos_items= sales_promos_items, bought_item = item_code, sales_promos_same_item = sales_promos_same_item, sales_promo_diff_items = sales_promo_diff_items, sales_promo_discount= sales_promo_discount, promos_qty = promos_qty, sales_promo_discounted_amount = sales_promo_discounted_amount )



@frappe.whitelist()
def item_qty_container(company, item_code, customer_type):
    fulfillment_settings = fetch_fulfillment_settings(company)
    stock_detail = fetch_item_details(item_code, customer_type, fulfillment_settings[0])
    handled_stock = available_stock_details(item_code, customer_type, fulfillment_settings[0])
    price_details = fetch_average_price(stock_detail, item_code)
    # sales_promo = fetch_sales_promos(item_code)
    return dict(available_qty = handled_stock["available_qty"], average_price = price_details["average_price"], price_details = price_details, stock_detail = stock_detail, qty_detail = handled_stock) 

@frappe.whitelist()
def sales_order_container(customer, order_list, company, customer_type, free_promos, promo_dis, sales_order):
    print(order_list)
    
    delivery_warehouse = ""
    fulfillment_settings = fetch_fulfillment_settings(company)
    # print("SETTINGS IN SALES ORDER", fulfillment_settings)
    delivery_warehouse = ""
    if customer_type == "Retail":
        delivery_warehouse = fulfillment_settings[0]["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        delivery_warehouse = fulfillment_settings[0]["hospital_warehouse"]
    elif customer == "Institutional":
        delivery_warehouse = fulfillment_settings[0]["institutional_warehouse"]
    free_promos = json.loads(free_promos)
    promo_dis = json.loads(promo_dis)
    order_list = json.loads(order_list)
    delivery_date = datetime.datetime.today()
    sales_order = json.loads(sales_order)
    delivery_date = delivery_date + datetime.timedelta(2)
    outerJson_so = {
        "doctype": "Sales Order",
        "naming_series": "SO-DL-",
        "customer": customer,
        "delivery_date": delivery_date,
        "pch_picking_status": "Ready for Picking",
        "pch_sales_order_purpose": "Delivery",
        "set_warehouse": delivery_warehouse,
        "items": [],
        "ignore_pricing_rule" : 1,
    }

    outerJson_qo = {
        "doctype": "Quotation",
        "naming_series": "QTN-DL-",
        "party_name": customer,
        "set_warehouse": delivery_warehouse,
        "items": []
    }
    for data in sales_order:
        if data["promo_type"] == None:
            if data["quantity"] > data["quantity_available"]:
                if data["quantity_available"] > 0:
                    innerJson_so = {
                        "doctype": "Sales Order Item",
                        "item_code": data["item_code"],
                        "qty": data["quantity"],
                        "rate": data["average"],
                    }
                innerJson_qo = {
                    "doctype": "Quotation Item",
                    "item_code": data["item_code"],
                    "qty": data["quantity"],
                    "rate": data["average"],
                }
        else:
            innerJson_so = {
                "doctype": "Sales Order Item",
                "item_code": data["item_code"],
                "qty": data["quantity"],
                "rate": data["average"],
                "promo_type" : data["promo_type"],
                "warehouse": data["warehouse"],

            }
            
        try:
            outerJson_so["items"].append(innerJson_so)
        except:
            pass
        try:
            outerJson_qo["items"].append(innerJson_qo)
        except:
            pass

    # for free in free_promos:
    #     if int(free["warehouse_quantity"]) > 0:
    #         innerJson_so = {
    #                 "doctype": "Sales Order Item",
    #                 "item_code": free["free_items"],
    #                 "qty": free["quantity"],
    #                 "rate": free["price"],
    #                 "promo_type" : free["promo_type"],
    #                 "warehouse": fulfillment_settings[0]["free_warehouse"],
                    
    #             }
    #     try:
    #         outerJson_so["items"].append(innerJson_so)
    #     except:
    #         pass

    # for dis in promo_dis:
    #     # if int(dis["warehouse_quantity"]) > 0:
    #     innerJson_so = {
    #             "doctype": "Sales Order Item",
    #             "item_code": dis["free_item"],
    #             "qty": dis["quantity"],
    #             "rate": dis["discount"],
    #             "promo_type" : dis["promo_type"],
    #             "warehouse": fulfillment_settings[0]["retail_primary_warehouse"],
                
    #         }
    #     try:
    #         outerJson_so["items"].append(innerJson_so)
    #     except:
    #         pass

    print(outerJson_qo)
    so_name = ""
    qo_name = ""
    if len(outerJson_so["items"]) > 0:
        doc_so = frappe.new_doc("Sales Order")
        doc_so.update(outerJson_so)
        doc_so.save()
        so_name = doc_so.name

    if len(outerJson_qo["items"]) > 0:
        doc_qo = frappe.new_doc("Quotation")
        doc_qo.update(outerJson_qo)
        doc_qo.save()
        qo_name = doc_qo.name

    return dict(so_name = so_name, qo_name = qo_name, outerJson_qo = outerJson_qo, outerJson_so = outerJson_so, outerJson = outerJson_so)