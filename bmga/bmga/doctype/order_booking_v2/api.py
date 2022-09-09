from cProfile import label
from dataclasses import fields
import json
import frappe
import datetime
import re
from erpnext.accounts.utils import get_balance_on

from pymysql import NULL

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
    
    print('warehouse', warehouse)
    
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

    print('FETCH STOCK SETTINGS', settings)

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

def fetch_contract_rate(customer, item_code):
    cl = []
    c = frappe.db.sql(
        f""" select rti.item, rti.selling_price_for_customer, rti.discount_percentage_for_customer_from_mrp, rt.customer, rt.selling_price
    from `tabRate Contract Item` as rti
        inner join `tabRate Contract` as rt on rt.name = rti.parent
        inner join `tabItem` as i on i.item_code = '{item_code}'
    where rti.item = '{item_code}' and i.has_batch_no = 0 and rt.selling_price = 1
    group by rti.item
        """, as_dict = True
    )
    print(".....", c)
    # cl.append({"Item": c[0]["item"], "price":c[0]["selling_price_for_customer"]})
    ct = frappe.db.sql(f""" select b.item, b.pch_mrp, b.expiry_date
    from `tabBatch` as b
    where b.item = '{item_code}'
    order by b.expiry_date DESC
    """, as_dict = True
    )
    # print("..........1", ct[0]["item"])
    
    if len(ct)>0:
        cl.append({"Item": ct[0]["item"], "price":ct[0]["pch_mrp"]})
        print("cl.........", cl)
        return cl
    # return dict( c = c, ct = ct )
    # else:
    if len(c)>0:
        cl.append({"Item": c[0]["item"], "price":c[0]["selling_price_for_customer"]})
        print("cl......", c[0]["item"])
        return cl

def customer_rate_contract(customer):
    rc = frappe.db.sql(
        f"""select name from `tabRate Contract` where customer = '{customer}'""",
        as_dict=1
    )
    if len(rc) > 0: return dict(valid = True, name = rc[0]["name"])
    else : return dict(valid = False, name = None)

def fetch_batch_detail(batch, item_code):
    p = frappe.db.sql(
        f"""select pch_mrp, pch_ptr as price from `tabBatch` where batch_id = '{batch}' and item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0 and p[0].get('price') is not None: return dict(price = p[0].get('price'), rate_contract_check = 0, mrp = p[0].get('pch_mrp') )
    else : return dict(price = 0, rate_contract_check = 0, mrp = 0)

def fetch_batchless_detail(item_code):
    p = frappe.db.sql(
        f"""select rci.selling_price_for_customer as price, rci.mrp as mrp
        from `tabRate Contract Item` as rci
            join `tabRate Contract` as rc on (rc.name = rci.parent)
        where rc.selling_price = 1 and rci.item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0 and p[0].get('price') is not None: return dict(price = p[0].get('price'), rate_contract_check = 0, mrp= p[0].get('mrp'))
    else : return dict(price = 0, rate_contract_check = 0, mrp=0)


def rate_fetch_mrp_batch(batch, item_code):
    p = frappe.db.get_value('Batch', {'batch_id': batch, 'item': item_code}, 'pch_mrp', as_dict=1)
    return dict(price = p.get('pch_mrp', 0))

def rate_fetch_mrp_batchless(item_code):
    p = frappe.db.sql(
        f"""select rci.mrp
        from `tabRate Contract Item` as rci
            join `tabRate Contract` as rc on (rci.parent = rc.name)
        where rc.selling_price = 1 rci.item = '{item_code}'""",
        as_dict=1
    )

    if len(p) > 0:
        return dict(price = p.get('mrp', 0))
    else: return dict(price = 0)

def fetch_rate_contract_detail(batch, item_code, rate_contract_name):
    today = datetime.date.today()
    p = frappe.db.sql(
        f"""select start_date, end_date, selling_price_for_customer as price, discount_percentage_for_customer_from_mrp as discount, batched_item
        from `tabRate Contract Item`
        where item = '{item_code}' and parent = '{rate_contract_name}'""",
        as_dict=1
    )

    if len(p) > 0:
        if p[0].get('start_date') <= today <= p[0].get('end_date'):
            if p[0].get('price') > 0:
                print("PRICE FIXED **************")
                return dict(price = p[0].get('price'), rate_contract_check = 1)
            elif p[0].get('discount') > 0:
                discount = (100 - p[0].get('discount')) / 100
                print("/*-"*25)
                print(p[0].get('batched_item'), discount)
                if p[0].get('batched_item') == "Yes":
                    b = rate_fetch_mrp_batch(batch, item_code)
                    print(b)
                    return dict(price = b['price'] * discount, rate_contract_check = 1)
                else:
                    b = rate_fetch_mrp_batchless(item_code)
                    return dict(price = b['price'] * discount, rate_contract_check = 1)
            else: return dict(price = 0)
        elif batch != "" : return fetch_batch_detail(batch, item_code)
        else: return fetch_batchless_detail(item_code)
    elif batch != "" : return fetch_batch_detail(batch, item_code)
    else: return fetch_batchless_detail(item_code)

def fetch_batch_price(batch, item_code, rate_contract_name):
    print("RATE CONTRACT NAME", rate_contract_name)
    if rate_contract_name is None: return fetch_batch_detail(batch, item_code)
    else: return fetch_rate_contract_detail(batch, item_code, rate_contract_name)

def fetch_batchless_price(item_code, rate_contract_name):
    if rate_contract_name is None: return fetch_batchless_detail(item_code)
    else: return fetch_rate_contract_detail("", item_code, rate_contract_name)

def is_item_batched(item_code):
    d = frappe.db.sql(
        f"""select batch_id from `tabBatch`
        where item = '{item_code}'
        order by expiry_date DESC""",
        as_dict=1
    )
    print("BATCHED ******")
    print(d)
    if len(d) > 0:
        return dict(valid = True, batch = d[0]["batch_id"])
    else: return dict(valid = False, batch = "")

def fetch_rate_contract_price(item_code, rate_contract_name):
    is_batch = is_item_batched(item_code)
    if is_batch['valid']:
        return fetch_batch_price(is_batch['batch'], item_code, rate_contract_name)
    else:
        return fetch_batchless_price(item_code, rate_contract_name)

def fetch_average_price_v2(customer, item_code):
    rate_contract = customer_rate_contract(customer)
    return fetch_rate_contract_price(item_code, rate_contract["name"])

def fetch_item_brand(item_code):
    brand = frappe.db.sql(
        f"""select it.brand as brand
        from `tabItem` as it
       where it.item_code = '{item_code}'""",
        as_dict=1
    )
    return dict(brand_name = brand[0].get('brand'))

def fetch_average_price(stock_data, customer, item_code):
    average_price_list = []
    average_qty_list = []
    average_price = 0
    stock_count = 0

    cd = fetch_contract_rate(customer, item_code)
    if len(cd)>0:
        return dict(average_price = cd[0]["price"], price_list = [], qty_list = [])
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

def fetch_fulfillment_settings(company, customer):
    fs_name = frappe.db.sql(
        f"""SELECT name, expiry_date_limit FROM `tabFulfillment Settings V1` WHERE company = '{company}'""",
        as_dict=True
    )

    customer_expiry = frappe.db.get_value('Customer', customer, 'pch_expiry_date_limit', as_dict=1)

    if fs_name:
        settings = frappe.db.sql(
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse, free_warehouse
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )

        if customer_expiry.get('pch_expiry_date_limit', 0) > 0: settings[0]["expiry_date_limit"] = customer_expiry["pch_expiry_date_limit"]
        else: settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
    else:
        settings = [None]
    return settings


#Available qty for y item
def available_stock_details_for_promos_y_item(item_code, customer_type, settings, expiry_date, ):
    today = datetime.date.today()
    stock_promo = []
    
    i = [x["item_code"] for x in item_code]
    i = re.sub(',\)$', ')', str(tuple(i)))
    
    print("Item",i)
    stock_batch_promo = frappe.db.sql(f"""select pt.bought_item, pt.free_item
                    from  `tabSales Promos` as sp  
                        inner join `tabPromo Type 3` as pt on pt.parent = sp.name
                        inner join `tabStock Ledger Entry` as sle on pt.free_item = sle.item_code
                    where pt.bought_item in {i} and sle.warehouse = '{settings}'
                    group by sle.item_code """, as_dict=True)
    print("...................................", stock_batch_promo)
    for i in range(len(stock_batch_promo)):
            print(".....", stock_batch_promo[i]["free_item"])
            stock_data_batch = frappe.db.sql(f"""
                select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code = '{stock_batch_promo[i]["free_item"]}' AND warehouse = '{settings}'
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by expiry_date ASC, warehouse DESC
            """, as_dict=True)
            stock_data_batchless = frappe.db.sql(
                f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
                where item_code = '{stock_batch_promo[i]["free_item"]}' and warehouse = '{settings}' and (batch_no is null or batch_no = '')
                group by item_code, warehouse""",
                as_dict=True
            )
        
    stock_promo.extend(stock_data_batch)
    stock_promo.extend(stock_data_batchless)
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
    print("AVAILABLE_QTY", available_qty)
    return available_qty


# Available Qty for Promo
def available_stock_details_for_promos(item_code, customer_type, settings, expiry_date):
    print("item_code", item_code)
    
    today = datetime.date.today()
    stock_promo = []
    i = [x["item_code"] for x in item_code]
    i = re.sub(',\)$', ')', str(tuple(i)))
    
    print("Item",i)
    
    # for i in stock_batch_promo:
    #     print("...................................", i)
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
    print("AVAILABLE_QTY", available_qty)
    return available_qty
    
# Buy x get same x
def fetch_sales_promos_get_same_item(customer, item_code, customer_type, free_warehouse, expiry_date, order_list):
    promo_type = "Buy x get same x"
    # fullfillment_settings = fetch_fulfillment_settings(company)
    # print("ORDER LIST*****************", order_list)
    sales_check = sales_promo_checked(customer)
    sales_promos_quantity = []
    promos_sale = []
    sales_data = None
    promos = []
    seen = []
    # print("Item",i)
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
    today = datetime.date.today()
    # print("HAI***************************")
    promos = frappe.db.sql (f""" select sp.start_date, sp.end_date, 
        pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
        pt.bought_item
        from  `tabSales Promos` as sp  
            inner join `tabPromo Type 2` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse = '{free_warehouse}'
        group by sle.item_code
        """, as_dict = True)
    print("promos......1", promos)
    print("len.....", len(order_list))
    if sales_check == True:
        for t in range (len(order_list)):
            for p in range (len(promos)):
                print("RATECONTRACT....", order_list[t]["rate_contract_check"], order_list[t]["item_code"], promos[p]["bought_item"])
                if order_list[t]["rate_contract_check"] == 0 and order_list[t]["item_code"] == promos[p]["bought_item"]:
                    print('x -> x inside if')
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
                                        print("sales", sales_data)
                                        promo_qty = available_stock_details_for_promos(item_code, customer_type, free_warehouse, expiry_date)
                                        print(promo_qty)
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
                                        
                                        if qty > 0:
                                            if order_list[t]["item_code"] == promos[i]["bought_item"]:
                                                # print("HAI***************************")
                                                promos_sale.append({"promo_type": promo_type  , "qty":sales_promos_quantity, "bought_item":promos[i]["bought_item"], "dic": "0", "rate": 0.0 , "promo_item": promos[i]["bought_item"], "w_qty" : qty})

                                            else:
                                                #print("HAI***************************", order_list[t]["rate_contract_check"], order_list[t]["item_code"], promos[i]["bought_item"])
                                                continue
                else: continue      
    else:
        print("HAI.....")
            
            # except:
            #     pass
                    #promos_sale.append({"promo_type": "None"  , "qty":order_list[j]["quantity_booked"], "bought_item":order_list[j]["item_code"], "dic": "0", "rate":order_list[j]["average_price"] , "promo_item": order_list[j]["item_code"], "w_qty" : order_list[j]["quantity_available"]})
    print(".............1",promos_sale)
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

  

# buy x get another y item
def fetch_sales_promos_get_diff_item(customer, item_code, customer_type, free_warehouse, expiry_date, order_list):
    promo_type = "Buy x get another y item"
    sales_check = sales_promo_checked(customer)
    sales_promos_quantity = []
    print("freeware", free_warehouse)
    promos_sale = []
    promos = []
    free_items = []
    sales_data = None
    seen = []
    today = datetime.date.today()
    # if customer_type == "Retail":
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
    promos = frappe.db.sql (f""" select sp.start_date, sp.end_date, 
                    pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
                    pt.bought_item, pt.free_item
                    from  `tabSales Promos` as sp  
                        inner join `tabPromo Type 3` as pt on pt.parent = sp.name
                        inner join `tabStock Ledger Entry` as sle on pt.free_item = sle.item_code
                    where pt.bought_item in {i} and sle.warehouse = '{free_warehouse}'
                    group by sle.item_code
                    """, as_dict = True)
    print("Promos......2", promos)
    print("len.....", order_list)
    if sales_check == True:
        for t in range (len(order_list)):
            for p in range (len(promos)):
                if order_list[t]["rate_contract_check"] == 0 and order_list[t]["item_code"] == promos[p]["bought_item"]:
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
                                        f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{promos[i]["free_item"]}' and warehouse = '{free_warehouse}'""", as_dict=True
                                        )
                                        sales_promos_details = ((j["quantity_booked"])//(promos[i]["for_every_quantity_that_is_bought"]))
                                        sales_promos_quantity = sales_promos_details*((promos[i]["quantity_of_free_items_thats_given"]))

                                        promo_qty = available_stock_details_for_promos_y_item(item_code, customer_type, free_warehouse, expiry_date)
                                        
                                        try:
                                            if sales_data[0].get("pending_qty") is None: 
                                                qty = promo_qty[promos[i]["free_item"]]
                                            else:
                                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["free_item"]]:
                                                    qty =  promo_qty[promos[i]["free_item"]] - sales_data[0]["pending_qty"]
                                                else:
                                                    continue
                                        except:
                                            qty = promo_qty[promos[i]["free_item"]]


                                        try:
                                            if sales_promos_quantity <= qty:
                                                sales_promos_quantity = sales_promos_quantity
                                            else:
                                                sales_promos_quantity = qty

                                        except:
                                            qty = promo_qty[promos[i]["free_item"]]

                                        print("...............................................................", qty)
                                        if qty > 0:
                                            if order_list[t]["item_code"] == promos[i]["bought_item"]:
                                                promos_sale.append({"promo_type": promo_type, "qty" : sales_promos_quantity, "bought_item":promos[i]["bought_item"], "dic": "0", "rate": 0.0 ,"promo_item" : promos[i]["free_item"], "w_qty" : qty})
                                            else:
                                                print("sales qunt diif", sales_promos_quantity)
                                                continue
                else: continue
    else:
        print("Hai")                                         
    print(".......2", promos_sale)
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

# buy x get same and discount for ineligible qty
def fetch_sales_promos_get_same_item_discout(customer, item_code, customer_type, free_warehouse, expiry_date, order_list):
    promo_type = "Buy x get same and discount for ineligible qty"
    sales_check = sales_promo_checked(customer)
    sales_promos_quantity = []
    promos_sale = []
    promos = []
    sales_data = None
    seen = []
    # sales_promo_discount = []
    
    # warehouse = re.sub(',\)$', ')', str(tuple(free_warehouse)))
    today = datetime.date.today()
    # if customer_type == "Retail":
    i = [x["item_code"] for x in item_code]
    i = re.sub(',\)$', ')', str(tuple(i)))
    promos = frappe.db.sql(f""" select sp.start_date, sp.end_date, 
        pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
        pt.bought_item, pt.discount
        from  `tabSales Promos` as sp  
            inner join `tabPromo Type 5` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse  = '{free_warehouse}'
        group by sle.item_code
                    """ , as_dict = True)
    print("promos......3", promos)
    print("len.....", len(order_list))
    if sales_check == True:
        for t in range (len(order_list)):
            for p in range (len(promos)):
                print('rate contract', order_list[t]["rate_contract_check"])
                print('o_l b_i', order_list[t]["item_code"], promos[p]["bought_item"])
                if order_list[t]["rate_contract_check"] == 0 and order_list[t]["item_code"] == promos[p]["bought_item"]:
                    print('inside if')
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

                                        if qty > 0:
                                            if order_list[t]["item_code"] == promos[i]["bought_item"]:
                                                if sales_promos_dic == 0:
                                                    promos_sale.append({"promo_type": promo_type, "qty" : sales_promos_quantity, "bought_item":promos[i]["bought_item"], "dic": "0", "rate": 0.0 ,"promo_item" : promos[i]["bought_item"], "w_qty" : qty})
                                                    
                                                else:
                                                    promos_sale.append({ "promo_type": promo_type,"qty":sales_promos_quantity, "dic_qty": sales_promos_dic, "dic":sales_promo_discount,"rate": 0.0 , "bought_item":promos[i]["bought_item"], "promo_item": promos[i]["bought_item"], "w_qty" : qty, "amount":sales_promo_amount })        
                else: continue
    else:
        print("Hai")      
    print("..........3", promos_sale)
    
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

# Quantity based discount
def fetch_sales_promos_qty_based_discount(customer , item_code, customer_type, free_warehouse, expiry_date, order_list):
    promo_type = "Quantity based discount"
    sales_promos_quantity = []
    sales_check = sales_promo_checked(customer)
    promos_sale = []
    promos = []
    sales_data = None
    data = []
    
    today = datetime.date.today()
    # if customer_type == "Retail":
    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
   
    promos = frappe.db.sql (f""" select sp.start_date, sp.end_date, 
            pt.quantity_bought, pt.discount_percentage,
            pt.bought_item
            from  `tabSales Promos` as sp  
                inner join `tabPromo Type 1` as pt on pt.parent = sp.name
                inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
        where pt.bought_item in {i} and sle.warehouse = '{free_warehouse}' group by pt.discount_percentage
        """, as_dict = True)
    print("promos..........4", promos)
    print("len.....", len(order_list))
    data.append(promos)
    for item in item_code:
        qty_booked = item["quantity_booked"]
        amt = item["amount"]
        print(".....", qty_booked, amt)
    seen = []
    sales_promo_discount = None
    if sales_check == True:
        for t in range (len(order_list)):
            for p in range (len(promos)):
                if order_list[t]["rate_contract_check"] == 0 and order_list[t]["item_code"] == promos[p]["bought_item"]:
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
                                        
                                        dis = promos[i].get("discount_percentage")
                                        print("dis....", dis)

                                        print(j["amount"], j["quantity_booked"], j["item_code"] )
                                        for l in range ((len(promos) -1), -1, -1): 
                                            
                                            print("Quanty bought",promos[l]["quantity_bought"] )
                                            if j["quantity_booked"] >= promos[l]["quantity_bought"]:
                                                sales_promo_discount = j["average_price"] * (100 - promos[l]["discount_percentage"])/100
                                                print("..",sales_promo_discount)
                                                break
                                        promo_qty = available_stock_details_for_promos(item_code, customer_type, free_warehouse, expiry_date)
                                        try:
                                            if sales_data[0].get("pending_qty") is None: 
                                                qty = promo_qty[promos[i]["bought_item"]]

                                            else:
                                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["bought_item"]]:
                                                    qty =  promo_qty[promos[i]["bought_item"]] - sales_data[0]["pending_qty"]
                                                
                                        except:
                                            qty = promo_qty[promos[i]["bought_item"]]
                                            
                                        try:
                                            if sales_promos_quantity <= qty:
                                                sales_promos_quantity = sales_promos_quantity
                                            else:
                                                sales_promos_quantity = qty
                                        except:
                                            qty = promo_qty[promos[i]["bought_item"]]

                                        if qty > 0:
                                            
                                            if order_list[t]["item_code"] == promos[p]["bought_item"]:
                                                promos_sale.append({"promo_type": promo_type, "qty": 0 , "dic":sales_promo_discount, "dic_qty": j["quantity_booked"], "rate": 0.0 , "bought_item":promos[i]["bought_item"], "promo_item": promos[i]["bought_item"] , "w_qty" : qty})
                                            else:
                                                continue
                else: continue                  
    else:
        print("Hai")                                            
    
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})

def sales_order_calculation(sales_promo_discounted_amount, sales_promos_items, order_list,customer_type, settings, free_warehouse):
    promo_sales_order= []
    if customer_type == "Retail":
        warehouse = settings[0]["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        warehouse = settings[0]["hospital_warehouse"]
    elif customer_type == "Institutional":
        warehouse = settings[0]["institutional_warehouse"]

    # if (len(sales_promo_discounted_amount)) > 0 and len(sales_promos_items) > 0:

    for o in range (len(order_list)):
        if order_list[o]["rate_contract_check"] == 1:
            promo_sales_order.append({"promo_type": "None"  , "qty":order_list[o]["quantity_booked"] , "item_code":order_list[o]["item_code"], "dic": "0", "average_price": order_list[o]["average_price"] , "warehouse" : warehouse , "qty_available" : order_list[o]["quantity_available"]})    
        
    for i in range (len(sales_promos_items)):
        for j in range (len(order_list)):
            if order_list[j]["rate_contract_check"] == 0 and order_list[j]["item_code"] == sales_promos_items[i]["promo_item"]:
                if sales_promos_items[i]["promo_type"] == "Buy x get same x" and sales_promos_items[i]["promo_item"] == order_list[j]["item_code"]:
                    promo_sales_order.append({"item_code":order_list[j]["item_code"], "qty": order_list[j]["quantity_booked"], "average_price": order_list[j]["average_price"], "warehouse" : warehouse, "qty_available":order_list[j]["quantity_available"], "promo_type" : "None"})
    
    for i in range (len(sales_promos_items)):
        for j in range (len(order_list)):
            # print("RATE>...........********", sales_promos_items[i]["promo_type"])
            if order_list[j]["rate_contract_check"] == 0 and order_list[j]["item_code"] == sales_promos_items[i]["bought_item"]:            
                if sales_promos_items[i]["promo_type"] == "Buy x get another y item":
                    # print("Hello....")
                    promo_sales_order.append({"item_code":order_list[j]["item_code"], "qty": order_list[j]["quantity_booked"], "average_price": order_list[j]["average_price"], "warehouse" : warehouse, "qty_available":order_list[j]["quantity_available"], "promo_type" : "None"})

            # else:
            #     if order_list[o]["rate_contract_check"] == 1 and order_list[o]["item_code"] == sales_promos_items[i]["promo_item"]:
            #         promo_sales_order.append({"promo_type": "None"  , "qty":order_list[o]["quantity_booked"] , "item_code":order_list[o]["item_code"], "dic": "0", "average_price": order_list[o]["average_price"] , "warehouse" : warehouse , "w_qty" : order_list[o]["quantity_available"]}) 
    
    for o in range (len(order_list)):
        for j in range (len(sales_promo_discounted_amount)):
            print("...............", sales_promo_discounted_amount)
            if order_list[o]["rate_contract_check"] == 0 and order_list[o]["item_code"] == sales_promo_discounted_amount[j]["promo_item"]:
                if sales_promo_discounted_amount[j]["promo_type"] == "Buy x get same and discount for ineligible qty":
                    # print("iiiiiii....2",o, j)
                    if order_list[o]["item_code"] == sales_promo_discounted_amount[j]["promo_item"]:
                        if sales_promo_discounted_amount[j].get("dic_qty") is not None:
                            order_list[o]["quantity_booked"] = order_list[o]["quantity_booked"] - sales_promo_discounted_amount[j]["dic_qty"]
                            # print("order......", order_list[o]["quantity_booked"])
                            print('finding index ...', promo_sales_order)
                            for i, x in enumerate(promo_sales_order):
                                if x['item_code'] == order_list[o]["item_code"] and x['warehouse'] == warehouse and x['average_price'] == order_list[o]["average_price"] and x["promo_type"] == "None":
                                    promo_sales_order.pop(i)
                            promo_sales_order.append({"item_code":order_list[o]["item_code"], "qty": order_list[o]["quantity_booked"], "average_price": order_list[o]["average_price"], "warehouse" : warehouse, "qty_available":order_list[o]["quantity_available"], "promo_type" : "None"})
                        else:
                            print('finding index ...', promo_sales_order)
                            for i, x in enumerate(promo_sales_order):
                                if x['item_code'] == order_list[o]["item_code"] and x['warehouse'] == warehouse and x['average_price'] == order_list[o]["average_price"] and x["promo_type"] == "None":
                                    promo_sales_order.pop(i)
                            promo_sales_order.append({"promo_type": "None"  , "qty":order_list[o]["quantity_booked"] , "item_code":order_list[o]["item_code"], "dic": "0", "average_price": order_list[o]["average_price"] , "warehouse" : warehouse , "qty_available" : order_list[o]["quantity_available"]})      
    

    for i in range (len(sales_promos_items)):
        for o in range (len(order_list)):
            # if order_list[o]["rate_contract_check"] == 1 and order_list[o]["item_code"] == sales_promos_items[i]["promo_item"]:
            #     promo_sales_order.append({"promo_type": "None"  , "qty":order_list[o]["quantity_booked"] , "item_code":order_list[o]["item_code"], "dic": "0", "average_price": order_list[o]["average_price"] , "warehouse" : warehouse , "w_qty" : order_list[o]["quantity_available"]}) 
            if order_list[o]["rate_contract_check"] == 0 and order_list[o]["item_code"] == sales_promos_items[i]["bought_item"]:
                if sales_promos_items[i]["promo_type"] == "Buy x get same x":
                    promo_sales_order.append({"item_code":sales_promos_items[i]["promo_item"], "qty": sales_promos_items[i]["qty"], "average_price": sales_promos_items[i]["rate"], "warehouse" : free_warehouse, "promo_type": sales_promos_items[i]["promo_type"], "qty_available": sales_promos_items[i]["w_qty"]})
                elif sales_promos_items[i]["promo_type"] == "Buy x get another y item":
                    promo_sales_order.append({"item_code":sales_promos_items[i]["promo_item"], "qty": sales_promos_items[i]["qty"], "average_price": sales_promos_items[i]["rate"], "warehouse" : free_warehouse, "promo_type": sales_promos_items[i]["promo_type"], "qty_available": sales_promos_items[i]["w_qty"]})
                else:
                    promo_sales_order.append({"item_code":sales_promos_items[i]["promo_item"], "qty": sales_promos_items[i]["qty"], "average_price": sales_promos_items[i]["rate"], "warehouse" : free_warehouse, "promo_type": sales_promos_items[i]["promo_type"], "qty_available": sales_promos_items[i]["w_qty"]})

            #     if order_list[o]["rate_contract_check"] == 1 and order_list[o]["item_code"] == sales_promos_items[i]["promo_item"]:
            #         promo_sales_order.append({"promo_type": "None"  , "qty":order_list[o]["quantity_booked"] , "item_code":order_list[o]["item_code"], "dic": "0", "average_price": order_list[o]["average_price"] , "warehouse" : warehouse , "w_qty" : order_list[o]["quantity_available"]})


    for j in range (len(sales_promo_discounted_amount)):
        for o in range (len(order_list)):
            if order_list[o]["rate_contract_check"] == 0 and order_list[o]["item_code"] == sales_promo_discounted_amount[j]["promo_item"]:
                if sales_promo_discounted_amount[j].get("dic_qty") is not None:
                    if order_list[o]["item_code"] == sales_promo_discounted_amount[j]["promo_item"] and sales_promo_discounted_amount[j]["promo_type"] == "Quantity based discount":
                        # print("Hello......")
                        promo_sales_order.append({"item_code":sales_promo_discounted_amount[j]["promo_item"], "qty": sales_promo_discounted_amount[j]["dic_qty"], "average_price": sales_promo_discounted_amount[j]["dic"], "warehouse" : warehouse , "promo_type": sales_promo_discounted_amount[j]["promo_type"], "qty_available": order_list[o]["quantity_available"]})

                    elif order_list[o]["item_code"] == sales_promo_discounted_amount[j]["promo_item"] and sales_promo_discounted_amount[j]["promo_type"] == "Buy x get same and discount for ineligible qty":
                        promo_sales_order.append({"item_code":sales_promo_discounted_amount[j]["promo_item"], "qty": sales_promo_discounted_amount[j]["dic_qty"], "average_price": sales_promo_discounted_amount[j]["dic"], "warehouse" : warehouse , "promo_type": sales_promo_discounted_amount[j]["promo_type"], "qty_available": order_list[o]["quantity_available"]})
                    
    
    if (len(sales_promo_discounted_amount)) == 0 and len(sales_promos_items) == 0:
        # for j in range (len(sales_promo_discounted_amount)):
        for i in range (len(order_list)):
            if order_list[i]["rate_contract_check"] == 0:
                promo_sales_order.append({"promo_type": "None" ,"qty":order_list[i]["quantity_booked"] , "item_code":order_list[i]["item_code"], "dic": "0", "average_price": order_list[i]["average_price"] , "warehouse" : warehouse , "qty_available" : order_list[i]["quantity_available"]})
    
    print(".........",promo_sales_order)

    return dict({"sales_order" : promo_sales_order})

@frappe.whitelist()
def sales_promo_checked(customer):
    sp = frappe.db.sql(f"""
        select c.pch_sales_promo
        from `tabCustomer` as c
        where c.name = '{customer}' and c.pch_sales_promo = 1
    """ , as_dict = True)
    
    if len(sp)>0:
        return True
    else:
        return False


def fetch_customer_sales_invoice(customer, template):
    today = datetime.date.today()

    s = frappe.db.get_list('Sales Invoice', filters = [{'customer': customer}], fields = ['status', 'due_date'])
    if len(s) > 0: 
        for x in s:
            if x['status'] != 'Paid':
                delta_day = today - x.get('due_date', 0)
                print(delta_day.days, template['credit_days'])
                if delta_day.days > int(template['credit_days']): return True
    return False

def verify_credit_limit(customer):
    template_name = frappe.db.get_list('Customer', filters = [{'name': customer}], fields = ['payment_terms'])
    if len(template_name) > 0:
        template = frappe.db.get_list('Payment Terms Template Detail', filters=[{'parent': template_name[0]['payment_terms']}], fields = ['credit_days', 'invoice_portion'])
        if len(template) > 0:
            if fetch_customer_sales_invoice(customer, template[0]): return True
    return False              


def get_unpaid_amount(customer):
	response = get_balance_on(party_type='Customer', party=customer)
	return response

def get_credit_limit(customer):
    cl = frappe.get_list('Customer Credit Limit', filters = [{'parent': customer}], fields = ['credit_limit'])
    if len(cl) > 0: return cl[0]['credit_limit']
    else: return 0

@frappe.whitelist(allow_guest= True)
def hello():
    return dict(msg = "Hello")

@frappe.whitelist()
def fulfillment_settings_container(company, customer):
    fulfillment_settings = fetch_fulfillment_settings(company, customer)
    return fulfillment_settings[0]

@frappe.whitelist()
def customer_type_container(customer):
    customer_type = fetch_customer_type(customer)
    unpaid_amount = get_unpaid_amount(customer)
    credit_limit = get_credit_limit(customer)
    print('credit limit backend', credit_limit)
    v = verify_credit_limit(customer)
    return dict(customer_type = customer_type, unpaid_amount = unpaid_amount, credit_limit = credit_limit, verification = v)

@frappe.whitelist()
def sales_promos(item_code , customer_type, company, order_list, customer):
    item_code = json.loads(item_code)
    order_list= json.loads(order_list)

    settings = fetch_fulfillment_settings(company, customer)
    promos_qty = available_stock_details_for_promos(item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
    sales_promos_same_item = fetch_sales_promos_get_same_item(customer, item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"], order_list)
    sales_promo_diff_items = fetch_sales_promos_get_diff_item(customer, item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"], order_list)
    sales_promo_discount = fetch_sales_promos_get_same_item_discout(customer, item_code, customer_type, settings[0]["free_warehouse"],  settings[0]["expiry_date_limit"], order_list)
    sales_promo_quantity_discount = fetch_sales_promos_qty_based_discount(customer, item_code, customer_type, settings[0]["retail_primary_warehouse"],  settings[0]["expiry_date_limit"], order_list)
    
    sales_promo_discounted_amount = sales_promo_discount["Promo_sales"] + sales_promo_quantity_discount["Promo_sales"]
    
    for i, v in enumerate(sales_promo_discounted_amount):
        if v.get('qty', 0) == 0:
            sales_promo_discounted_amount.pop(i)
    
    sales_promos_items = sales_promos_same_item["Promo_sales"] + sales_promo_diff_items["Promo_sales"] + sales_promo_discount["Promo_sales"]
    
    for i, v in enumerate(sales_promos_items):
        if v.get('qty', 0) == 0:
            sales_promos_items.pop(i)
    
    print('done')
    
    sales_order = sales_order_calculation(sales_promo_discounted_amount, sales_promos_items, order_list, customer_type, settings, settings[0]["free_warehouse"])


    return dict(sales_order = sales_order,sales_promos_items= sales_promos_items, bought_item = item_code, sales_promos_same_item = sales_promos_same_item, sales_promo_diff_items = sales_promo_diff_items, sales_promo_discount= sales_promo_discount, promos_qty = promos_qty, sales_promo_discounted_amount = sales_promo_discounted_amount )


def check_promo_type_1(item_code):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p1.bought_item
            from `tabPromo Type 1` as p1
                join `tabSales Promos` as p on (p.name = p1.parent)
            where p1.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return 1
    return 0


def check_promo_type_2(item_code):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p2.bought_item
            from `tabPromo Type 2` as p2
                join `tabSales Promos` as p on (p.name = p2.parent)
            where p2.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return 1
    return 0


def check_promo_type_3(item_code):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p3.bought_item
            from `tabPromo Type 3` as p3
                join `tabSales Promos` as p on (p.name = p3.parent)
            where p3.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return 1
    return 0


def check_promo_type_5(item_code):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p5.bought_item
            from `tabPromo Type 5` as p5
                join `tabSales Promos` as p on (p.name = p5.parent)
            where p5.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return 1
    return 0


def check_item_promo(item_code):
    type_1 = check_promo_type_1(item_code)
    type_2 = check_promo_type_2(item_code)
    type_3 = check_promo_type_3(item_code)
    type_5 = check_promo_type_5(item_code)

    if type_1 == 1 or type_2 == 1 or type_3 == 1 or type_5 == 1: return 1
    return 0

def check_sales_promo(customer, item_code):
    c = frappe.db.get_value('Customer', {'name': customer}, 'pch_sales_promo', as_dict=1)
    i = check_item_promo(item_code)
    if c.get('pch_sales_promo', 0) == 1 and i == 1: return 1
    return 0

@frappe.whitelist()
def item_qty_container(company, item_code, customer_type, customer = None):
    fulfillment_settings = fetch_fulfillment_settings(company, customer)
    stock_detail = fetch_item_details(item_code, customer_type, fulfillment_settings[0])
    handled_stock = available_stock_details(item_code, customer_type, fulfillment_settings[0])
    if not customer == None:
        price_details = fetch_average_price_v2(customer, item_code)
    else:
        price_details = None
    if not customer == None:
        brand_name =  fetch_item_brand(item_code)
    else:
        brand_name = None
    sales_check = check_sales_promo(customer, item_code)
    return dict(promo_check = sales_check, available_qty = handled_stock["available_qty"], price_details = price_details, stock_detail = stock_detail, qty_detail = handled_stock, brand_name = brand_name) 


def fetch_gst_detail(company):
    d = frappe.db.sql(
        f"""select fsd.gst_out_state, fsd.gst_in_state
        from `tabFulfillment Settings Details V1` as fsd
            join `tabFulfillment Settings V1` as fs on (fs.name = fsd.parent)
        where fs.company = '{company}'""",
        as_dict=1
    )

    if len(d) > 0: return d[0]
    else: frappe.throw('ADD GST detail to Fulfillement Settings!!!')


def check_customer_state(customer, company):
    company_code = -1
    customer_code = -2

    address = frappe.db.get_list('Address', fields=['name'])
    for a in address:
        doc = frappe.get_doc('Address', a['name']).as_dict()
        try:
            if doc.address_type == 'Shipping': continue
            if doc.get('links')[0].get('link_name') == customer: customer_code = doc.gst_state_number
            if doc.get('links')[0].get('link_name') == company: company_code = doc.gst_state_number
        except:
            continue

    print('/*-+'*50)
    print(customer_code, company_code)
    print('/*-+'*50)
    
    return dict(valid = company_code == customer_code, customer_code = customer_code, company_code = company_code)
    

def fetch_tax_detail(name):
    d = frappe.db.sql(
        f"""select charge_type, account_head, rate, description
        from `tabSales Taxes and Charges` where parent = '{name}'
        order by modified DESC""",
        as_dict=1
    )

    h = {}
    list(map(lambda x: h.update({x['account_head']: x['rate']}), d))

    if len(d) > 0:
        return dict(detail = d, tax = h)
    else:
        frappe.throw(f'Sales Taxes and Charges detail not found for {name}')



def fetch_item_tax(item_code):
    today = datetime.date.today()

    r = frappe.db.sql(
        f"""select ittd.tax_rate, ittd.tax_type
        from `tabItem Tax Template Detail` as ittd
            join `tabItem Tax Template` as itt on (itt.name = ittd.parent)
                join `tabItem Tax` as it on (it.item_tax_template = itt.name)
        where it.parent = '{item_code}' and (valid_from is null or valid_from = '' or valid_from <= '{today}')
        order by valid_from DESC""",
        as_dict=1
    )

    handled = {}
    list(map(lambda x: handled.update({x['tax_type']: x['tax_rate']}), r))

    if len(r) > 0: return dict(valid = True, tax_rate = handled)
    else: return dict(valid = False, tax_rate = None)


def fetch_company_abbr(company):
    a = frappe.db.get_value('Company', {'name': company}, 'abbr', as_dict=1)
    return a.get('abbr')


@frappe.whitelist()
def sales_order_container(customer, company, customer_type, sales_order):
    print("ORDER.......",sales_order)

    abbr = fetch_company_abbr(company)
    print(abbr)

    gst_detail = fetch_gst_detail(company)
    customer_in_state = check_customer_state(customer, company)
    print(customer_in_state)
    if customer_in_state.get('valid'):
        tax = gst_detail['gst_in_state']
        tax_detail = fetch_tax_detail(gst_detail['gst_in_state'])
    else:
        tax = gst_detail['gst_out_state']
        tax_detail = fetch_tax_detail(gst_detail['gst_out_state'])

    
    delivery_warehouse = ""
    fulfillment_settings = fetch_fulfillment_settings(company, customer)
    # print("SETTINGS IN SALES ORDER", fulfillment_settings)
    delivery_warehouse = ""
    if customer_type == "Retail":
        delivery_warehouse = fulfillment_settings[0]["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        delivery_warehouse = fulfillment_settings[0]["hospital_warehouse"]
    elif customer == "Institutional":
        delivery_warehouse = fulfillment_settings[0]["institutional_warehouse"]

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
        # 'taxes_and_charges': tax,
        "items": [],
        "taxes": [],
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
        if data["quantity"] > data["quantity_available"]:
            if data["promo_type"] == "None" or data["promo_type"] == "Quantity based discount" or data["promo_type"] == "Buy x get same and discount for ineligible qty":
                if data["quantity_available"] > 0:
                    # item_tax = fetch_item_tax(data['item_code'])
                    # if item_tax.get('valid'):
                    #     if customer_in_state.get('valid'):
                    #         cgst += (data['average'] * item_tax['tax_rate'].get(f'Input Tax CGST - {abbr}')/100) * data['quantity']
                    #         sgst += (data['average'] * item_tax['tax_rate'].get(f'Input Tax SGST - {abbr}')/100) * data['quantity']
                    #     else:
                    #         igst += (data['average'] * item_tax['tax_rate'].get(f'Input Tax IGST - {abbr}')/100) * data['quantity']
                    # else:
                    #     if customer_in_state.get('valid'):
                    #         pass
                    #     else:
                    #         igst += (data['average'] * tax_detail['tax'].get(f'Output Tax IGST - {abbr}')/100) * data['quantity']

                    innerJson_so = {
                        "doctype": "Sales Order Item",
                        "item_code": data["item_code"],
                        "qty": data["quantity_available"],
                        "rate": data["average"],
                    }

                    innerJson_qo = {
                        "doctype": "Quotation Item",
                        "item_code": data["item_code"],
                        "qty": data["quantity"] - data["quantity_available"],
                        "rate": data["average"],
                    }
                else:
                    innerJson_qo = {
                        "doctype": "Quotation Item",
                        "item_code": data["item_code"],
                        "qty": data["quantity"],
                        "rate": data["average"],
                    }
        else:
            # item_tax = fetch_item_tax(data['item_code'])
            # if item_tax.get('valid'):
            #     if customer_in_state.get('valid'):
            #         cgst += (data['average'] * item_tax['tax_rate'].get(f'Input Tax CGST - {abbr}')/100) * data['quantity']
            #         sgst += (data['average'] * item_tax['tax_rate'].get(f'Input Tax SGST - {abbr}')/100) * data['quantity']
            #     else:
            #         igst += (data['average'] * item_tax['tax_rate'].get(f'Input Tax IGST - {abbr}')/100) * data['quantity']
            # else:
            #     if customer_in_state.get('valid'):
            #         pass
            #     else:
            #         igst += (data['average'] * tax_detail['tax'].get(f'Output Tax IGST - {abbr}')/100) * data['quantity']
            
            # print('igst', igst)
            # print('sgst', sgst)
            # print('cgst', cgst)

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
    
    innerJson_tax_list = []
    if customer_in_state.get('valid'):
        for x in tax_detail['detail']:
            if x.get('account_head') == f'Output Tax SGST - {abbr}':
                print('SGST', x.get('description'))
                innerJson_tax_list.append({
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": x["charge_type"],
                    "account_head": x["account_head"],
                    "description": x["description"],
                })
            else:
                innerJson_tax_list.append({
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": x["charge_type"],
                    "account_head": x["account_head"],
                    "description": x["description"],
                })
    else:
        innerJson_tax_list.append({
            "doctype": "Sales Taxes and Charges",
            "charge_type": tax_detail['detail'][0]["charge_type"],
            "account_head": tax_detail['detail'][0]["account_head"],
            "description": tax_detail['detail'][0]["description"],
        })

    outerJson_so['taxes'].extend(innerJson_tax_list)
    print(outerJson_so['taxes'])

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

    return dict(customer_in_state = customer_in_state, so_name = so_name, qo_name = qo_name, outerJson_qo = outerJson_qo, outerJson_so = outerJson_so, outerJson = outerJson_so)

@frappe.whitelist()
def update_pending_reason(name, total_amount, unpaid_amount, credit_limit, credit_days = False):    
    msg = ''
    
    doc = frappe.get_doc('Order Booking V2', name)
        
    if total_amount + unpaid_amount > credit_limit:
        msg = 'Credit limit exceeded'
    
    if credit_days:
        msg = 'Credit days exceeded'
    
    doc.pending_reason = msg
    doc.save('Update')
    
    return msg

@frappe.whitelist()
def reject_order(name):
    doc = frappe.get_doc('Order Booking V2', name)
    doc.pch_status = "Rejected"

    doc.save('Update')

@frappe.whitelist()
def approve_order(name, so_name, qo_name):
    doc = frappe.get_doc('Order Booking V2', name)
    doc.pch_status = "Approved"
    doc.order_booking_so = so_name
    doc.hunting_quotation = qo_name

    doc.save('Update')

@frappe.whitelist()
def fetch_order_items(name):
    doc = frappe.get_doc('Order Booking V2', name).as_dict()

    return dict(order_booking_items_v2 = doc.order_booking_items_v2,
        promos = doc.promos, promos_discount = doc.promos_discount,
        sales_order_preview = doc.sales_order_preview)

@frappe.whitelist()
def pending_order(name):
    doc = frappe.get_doc('Order Booking V2', name)

    if doc.pending_reason:
        doc.pch_status = "Pending"
        doc.save('Update')
        doc.submit()

@frappe.whitelist()
def submit_order(name):
    doc = frappe.get_doc('Order Booking V2', name)

    doc.pch_status = "Approved"
    doc.save('Update')
    doc.submit()