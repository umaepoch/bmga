import json
import frappe
import datetime
import re
from frappe.utils import flt

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
        sales_data[0]["pending_qty"] = 0
    
    if available_qty < 0:
        available_qty = 0

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
    
    stock_data_batch = frappe.db.sql(f"""
            select item as item_code, expiry_date, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code in {i} AND warehouse = '{settings}'
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC, warehouse DESC
        """, as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select item_code, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code in {i} and warehouse = '{settings}' and (batch_no is null or batch_no = '')
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
    
    print("AVAILABLE_QTY", available_qty)
    return available_qty
    
# Buy x get same x
def fetch_sales_promos_get_same_item(customer, item_code, customer_type, free_warehouse, expiry_date, order_list):
    promo_type = "Buy x get same x"
    sales_check = sales_promo_checked(customer)
    sales_promos_quantity = []
    promos_sale = []
    sales_data = None
    promos = []
    seen = []

    i = [x["item_code"] for x in item_code]
    i = re.sub(r',\)$', ')', str(tuple(i)))
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

                                        try:
                                            if sales_data[0].get("pending_qty") is None: 
                                                qty = promo_qty[promos[i]["bought_item"]]
                                            else:
                                                if sales_data[0]["pending_qty"] <= promo_qty[promos[i]["bought_item"]]:
                                                    qty =  promo_qty[promos[i]["bought_item"]] - sales_data[0]["pending_qty"]
                                                else:
                                                    continue
                                        except:
                                            try: qty = promo_qty[promos[i]["bought_item"]]
                                            except: qty = 0
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
                                            try: qty = promo_qty[promos[i]["bought_item"]]
                                            except: qty = 0
                                        
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
                                            try: qty = promo_qty[promos[i]["free_item"]]
                                            except: qty = 0


                                        try:
                                            if sales_promos_quantity <= qty:
                                                sales_promos_quantity = sales_promos_quantity
                                            else:
                                                sales_promos_quantity = qty

                                        except:
                                            try: qty = promo_qty[promos[i]["free_item"]]
                                            except: qty = 0

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
                                            try: qty = promo_qty[promos[i]["bought_item"]]
                                            except: qty = 0

                                        try:
                                            if sales_promos_quantity <= qty:
                                                sales_promos_quantity = sales_promos_quantity
                                            else:
                                                sales_promos_quantity = qty

                                        except:
                                            try: qty = promo_qty[promos[i]["bought_item"]]
                                            except: qty = 0

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
                                            try: qty = promo_qty[promos[i]["bought_item"]]
                                            except: qty = 0
                                            
                                        try:
                                            if sales_promos_quantity <= qty:
                                                sales_promos_quantity = sales_promos_quantity
                                            else:
                                                sales_promos_quantity = qty
                                        except:
                                            try: qty = promo_qty[promos[i]["bought_item"]]
                                            except: qty = 0

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
                        print('finding index ...', promo_sales_order)
                        for i, x in enumerate(promo_sales_order):
                            if x['item_code'] == order_list[o]["item_code"] and x['warehouse'] == warehouse and x['average_price'] == order_list[o]["average_price"] and x["promo_type"] == "None":
                                promo_sales_order.pop(i)
                        promo_sales_order.append({"item_code":sales_promo_discounted_amount[j]["promo_item"], "qty": sales_promo_discounted_amount[j]["dic_qty"], "average_price": sales_promo_discounted_amount[j]["dic"], "warehouse" : warehouse , "promo_type": sales_promo_discounted_amount[j]["promo_type"], "qty_available": order_list[o]["quantity_available"]})

                    elif order_list[o]["item_code"] == sales_promo_discounted_amount[j]["promo_item"] and sales_promo_discounted_amount[j]["promo_type"] == "Buy x get same and discount for ineligible qty":
                        print('finding index ...', promo_sales_order)
                        for i, x in enumerate(promo_sales_order):
                            if x['item_code'] == order_list[o]["item_code"] and x['warehouse'] == warehouse and x['average_price'] == order_list[o]["average_price"] and x["promo_type"] == "None":
                                promo_sales_order.pop(i)
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
    print('checking sales invoices')
    if len(s) > 0: 
        for x in s:
            if x['status'] != 'Paid':
                delta_day = x.get('due_date', 0) - today
                print(delta_day.days, template['credit_days'])
                if delta_day.days > int(template['credit_days']): return True
    return False

def verify_credit_limit(customer):
    template_name = frappe.db.get_list('Customer', filters = [{'name': customer}], fields = ['payment_terms'])
    if len(template_name) > 0:
        print('inside if')
        print(template_name)
        template = frappe.db.get_list('Payment Terms Template Detail', filters=[{'parent': template_name[0]['payment_terms']}], fields = ['credit_days', 'invoice_portion'])
        if len(template) > 0:
            if fetch_customer_sales_invoice(customer, template[0]): return True
        else:
            print('inside else')
            if fetch_customer_sales_invoice(customer, {'credit_days': 0}): return True
    else:
        print('inside else')
        if fetch_customer_sales_invoice(customer, {'credit_days': 0}): return True

    return False            

@frappe.whitelist(allow_guest= True)
def hello():
    return dict(msg = "Hello")

@frappe.whitelist()
def fulfillment_settings_container(company, customer):
    fulfillment_settings = fetch_fulfillment_settings(company, customer)
    return fulfillment_settings[0]


# Credit limit
def get_credit_limit(customer, company):
	credit_limit = None

	if customer:
		credit_limit = frappe.db.get_value("Customer Credit Limit",
			{'parent': customer, 'parenttype': 'Customer', 'company': company}, 'credit_limit')

		if not credit_limit:
			customer_group = frappe.get_cached_value("Customer", customer, 'customer_group')
			credit_limit = frappe.db.get_value("Customer Credit Limit",
				{'parent': customer_group, 'parenttype': 'Customer Group', 'company': company}, 'credit_limit')

	if not credit_limit:
		credit_limit = frappe.get_cached_value('Company',  company,  "credit_limit")

	return flt(credit_limit)

def get_customer_outstanding(customer, company, ignore_outstanding_sales_order=False, cost_center=None):
	# Outstanding based on GL Entries

	cond = ""
	if cost_center:
		lft, rgt = frappe.get_cached_value("Cost Center",
			cost_center, ['lft', 'rgt'])

		cond = """ and cost_center in (select name from `tabCost Center` where
			lft >= {0} and rgt <= {1})""".format(lft, rgt)

	outstanding_based_on_gle = frappe.db.sql("""
		select sum(debit) - sum(credit)
		from `tabGL Entry` where party_type = 'Customer'
		and party = %s and company=%s {0}""".format(cond), (customer, company))

	outstanding_based_on_gle = flt(outstanding_based_on_gle[0][0]) if outstanding_based_on_gle else 0

	# Outstanding based on Sales Order
	outstanding_based_on_so = 0

	# if credit limit check is bypassed at sales order level,
	# we should not consider outstanding Sales Orders, when customer credit balance report is run
	if not ignore_outstanding_sales_order:
		outstanding_based_on_so = frappe.db.sql("""
			select sum(base_grand_total*(100 - per_billed)/100)
			from `tabSales Order`
			where customer=%s and docstatus = 1 and company=%s
			and per_billed < 100 and status != 'Closed'""", (customer, company))

		outstanding_based_on_so = flt(outstanding_based_on_so[0][0]) if outstanding_based_on_so else 0

	# Outstanding based on Delivery Note, which are not created against Sales Order
	outstanding_based_on_dn = 0

	unmarked_delivery_note_items = frappe.db.sql("""select
			dn_item.name, dn_item.amount, dn.base_net_total, dn.base_grand_total
		from `tabDelivery Note` dn, `tabDelivery Note Item` dn_item
		where
			dn.name = dn_item.parent
			and dn.customer=%s and dn.company=%s
			and dn.docstatus = 1 and dn.status not in ('Closed', 'Stopped')
			and ifnull(dn_item.against_sales_order, '') = ''
			and ifnull(dn_item.against_sales_invoice, '') = ''
		""", (customer, company), as_dict=True)

	if not unmarked_delivery_note_items:
		return outstanding_based_on_gle + outstanding_based_on_so

	si_amounts = frappe.db.sql("""
		SELECT
			dn_detail, sum(amount) from `tabSales Invoice Item`
		WHERE
			docstatus = 1
			and dn_detail in ({})
		GROUP BY dn_detail""".format(", ".join(
			frappe.db.escape(dn_item.name)
			for dn_item in unmarked_delivery_note_items
		))
	)

	si_amounts = {si_item[0]: si_item[1] for si_item in si_amounts}

	for dn_item in unmarked_delivery_note_items:
		dn_amount = flt(dn_item.amount)
		si_amount = flt(si_amounts.get(dn_item.name))

		if dn_amount > si_amount and dn_item.base_net_total:
			outstanding_based_on_dn += ((dn_amount - si_amount)
				/ dn_item.base_net_total) * dn_item.base_grand_total

	return outstanding_based_on_gle + outstanding_based_on_so + outstanding_based_on_dn


def check_credit_limit(customer, company, ignore_outstanding_sales_order=False, extra_amount=0):
    credit_limit = get_credit_limit(customer, company)
    if not credit_limit:
        credit_limit = 0

    customer_outstanding = get_customer_outstanding(customer, company, ignore_outstanding_sales_order)
    if not customer_outstanding:
        customer_outstanding = 0

    if extra_amount > 0:
        customer_outstanding += flt(extra_amount)
    
    return customer_outstanding, credit_limit

@frappe.whitelist()
def customer_type_container(customer, company):
    customer_type = fetch_customer_type(customer)
    unpaid_amount, credit_limit = check_credit_limit(customer, company)
    v = verify_credit_limit(customer)
    return dict(customer_type = customer_type, unpaid_amount = unpaid_amount, credit_limit = credit_limit, credit_days = v)

# @frappe.whitelist()
# def sales_promos(item_code , customer_type, company, order_list, customer):
#     item_code = json.loads(item_code)
#     order_list= json.loads(order_list)

#     settings = fetch_fulfillment_settings(company, customer)
#     promos_qty = available_stock_details_for_promos(item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
#     sales_promos_same_item = fetch_sales_promos_get_same_item(customer, item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"], order_list)
#     sales_promo_diff_items = fetch_sales_promos_get_diff_item(customer, item_code, customer_type, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"], order_list)
#     sales_promo_discount = fetch_sales_promos_get_same_item_discout(customer, item_code, customer_type, settings[0]["free_warehouse"],  settings[0]["expiry_date_limit"], order_list)
#     sales_promo_quantity_discount = fetch_sales_promos_qty_based_discount(customer, item_code, customer_type, settings[0]["retail_primary_warehouse"],  settings[0]["expiry_date_limit"], order_list)
    
#     sales_promo_discounted_amount = sales_promo_discount["Promo_sales"] + sales_promo_quantity_discount["Promo_sales"]
    
#     sales_promos_items = sales_promos_same_item["Promo_sales"] + sales_promo_diff_items["Promo_sales"] + sales_promo_discount["Promo_sales"]
    
#     sales_order = sales_order_calculation(sales_promo_discounted_amount, sales_promos_items, order_list, customer_type, settings, settings[0]["free_warehouse"])

#     # for i, v in enumerate(sales_order['sales_order']):
#     #     if v.get('qty', 0) == 0:
#     #         sales_order['sales_order'].pop(i)
#     #     if v.get('promo_type', 'None') == 'None' and sales_order['sales_order'].index(v) != i:
#     #         sales_order['sales_order'].pop(i)

#     return dict(sales_order = sales_order,sales_promos_items= sales_promos_items, bought_item = item_code, sales_promos_same_item = sales_promos_same_item, sales_promo_diff_items = sales_promo_diff_items, sales_promo_discount= sales_promo_discount, promos_qty = promos_qty, sales_promo_discounted_amount = sales_promo_discounted_amount )

def check_promo_stock(item_code, qty, free_warehouse, expiry_days):
    today = datetime.date.today()
    
    stock_data_batch = frappe.db.sql(f"""
            select expiry_date, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code = '{item_code}' and warehouse = '{free_warehouse}'
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC, warehouse DESC
        """, as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code = '{item_code}' and warehouse = '{free_warehouse}' and (batch_no is null or batch_no = '')""",
        as_dict=True
    )

    batch_sum = 0
    if stock_data_batch:
        for x in stock_data_batch:
            if x["expiry_date"] is not None: 
                date_delta = x["expiry_date"] - today
                if date_delta.days < expiry_days: continue
                if x.get('actual_qty') is None: continue
                batch_sum += x['actual_qty']
    
    batchless_sum = 0
    if stock_data_batchless:
        if len(stock_data_batchless) > 0:
            if stock_data_batchless[0].get('actual_qty') is not None:
                batchless_sum += stock_data_batchless[0].get['actual_qty']
    
    available_qty = batch_sum + batchless_sum
    if qty <= available_qty: return dict(free_qty = qty, available_qty = available_qty)
    return dict(free_qty = available_qty, available_qty = available_qty)

def check_promo_1(i):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p1.discount_percentage as discount
            from `tabPromo Type 1` as p1
                join `tabSales Promos` as p on (p.name = p1.parent)
            where p1.bought_item = '{i['item_code']}' and p1.quantity_bought <= '{i['quantity_booked']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
            order by p1.quantity_bought DESC""",
            as_dict=1
    )

    if not p: return
    if not len(p) > 0: return

    discount_price = i['average_price'] * ((100 - p[0]['discount'])/100)
    return dict(discount_price = discount_price)

def check_promo_5(i, free_warehouse, expiry_days):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p5.quantity_of_free_items_thats_given as free_qty, p5.discount, p5.for_every_quantity_that_is_bought as bought_qty
            from `tabPromo Type 5` as p5
                join `tabSales Promos` as p on (p.name = p5.parent)
            where p5.bought_item = '{i['item_code']}' and p5.for_every_quantity_that_is_bought <= '{i['quantity_booked']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
            order by p5.for_every_quantity_that_is_bought DESC""",
            as_dict=1
    )
    if not p: return
    if not len(p) > 0: return

    fcalc_qty = i['quantity_booked']//p[0]['bought_qty'] * p[0]['free_qty']
    dicalc_qty = i['quantity_booked']%10
    normalcalc_qty = i['quantity_booked'] - dicalc_qty


    free_stock = check_promo_stock(i['item_code'], fcalc_qty, free_warehouse, expiry_days)
    return dict(discount_price = i['average_price'] * ((100 - p[0]['discount'])/100), dic_qty = dicalc_qty,
        free_qty = free_stock['free_qty'], free_available_qty = free_stock['available_qty'],
        normal_qty = normalcalc_qty)

def check_promo_2(i, free_warehouse, expiry_days):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p2.quantity_of_free_items_thats_given as free_qty, p2.for_every_quantity_that_is_bought as bought_qty
            from `tabPromo Type 2` as p2
                join `tabSales Promos` as p on (p.name = p2.parent)
            where p2.bought_item = '{i['item_code']}' and p2.for_every_quantity_that_is_bought <= '{i['quantity_booked']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
            order by p2.for_every_quantity_that_is_bought DESC""",
            as_dict=1
    )

    if not p: return
    if not len(p) > 0: return

    fcalc_qty = i['quantity_booked']//p[0]['bought_qty'] * p[0]['free_qty']

    free_stock = check_promo_stock(i['item_code'], fcalc_qty, free_warehouse, expiry_days)
    return dict(free_item = i['item_code'], free_qty = free_stock['free_qty'],
        free_available_qty = free_stock['available_qty'])

def check_promo_3(i, free_warehouse, expiry_days):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p3.free_item, p3.for_every_quantity_that_is_bought as bought_qty, p3.quantity_of_free_items_thats_given as free_qty
            from `tabPromo Type 3` as p3
                join `tabSales Promos` as p on (p.name = p3.parent)
            where p3.bought_item = '{i['item_code']}' and p3.for_every_quantity_that_is_bought <= '{i['quantity_booked']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
            order by p3.for_every_quantity_that_is_bought DESC""",
            as_dict=1
    )

    if not p: return
    if not len(p) > 0: return

    fcalc_qty = i['quantity_booked']//p[0]['bought_qty'] * p[0]['free_qty']
    free_item = p[0]['free_item']
    free_stock = check_promo_stock(free_item, fcalc_qty, free_warehouse, expiry_days)
    return dict(free_item = free_item, free_qty = free_stock['free_qty'],
        free_available_qty = free_stock['available_qty'])

def handle_sales_promo(i, settings):
    default_preview_added = False
    sales_preview = []
    promo_discount = []
    promo_free = []

    p1 = check_promo_1(i)
    if p1:
        promo_type = 'Quantity based discount'
        promo_discount.append(
            promo_discount_helper(i['item_code'], i['item_code'], i['quantity_booked'], p1['discount_price'], promo_type, i['quantity_booked'] * p1['discount_price'])
        )
        sales_preview.append(
            sales_preview_helper(i['item_code'], i['quantity_available'], i['quantity_booked'], p1['discount_price'], settings[0]["retail_primary_warehouse"], promo_type)
        )
        default_preview_added = True
    else:
        p5 = check_promo_5(i, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
        if p5:
            promo_type = 'Buy x get same and discount for ineligible qty'
            promo_discount.append(
                promo_discount_helper(i['item_code'], i['item_code'], p5['dic_qty'], p5['discount_price'], promo_type, p5['dic_qty'] * p5['discount_price'])
            )
            sales_preview.append(
                sales_preview_helper(i['item_code'], i['quantity_available'], p5['dic_qty'], p5['discount_price'], settings[0]["retail_primary_warehouse"], promo_type)
            )
            if p5['free_available_qty'] > 0:
                promo_free.append(
                    promo_free_helper(i['item_code'], i['item_code'], p5['free_qty'], 0, p5['free_available_qty'], promo_type)
                )
                sales_preview.append(
                    sales_preview_helper(i['item_code'], p5['free_available_qty'], p5['free_qty'], 0, settings[0]["free_warehouse"], promo_type)
                )
            sales_preview.append(
                sales_preview_helper(i['item_code'], i['quantity_available'], p5['normal_qty'], i['average_price'], settings[0]["retail_primary_warehouse"], 'None')
            )
            default_preview_added = True
    
    p2 = check_promo_2(i, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
    if p2:
        if p2['free_available_qty'] > 0:
            promo_type = 'Buy x get same x'
            promo_free.append(
                promo_free_helper(i['item_code'], p2['free_item'], p2['free_qty'], 0, p2['free_available_qty'], promo_type)
            )
            sales_preview.append(
                sales_preview_helper(i['item_code'], p2['free_available_qty'], p2['free_qty'], 0, settings[0]["free_warehouse"], promo_type)
            )
            if not default_preview_added:
                sales_preview.append(
                    sales_preview_helper(i['item_code'], i['quantity_available'], i['quantity_booked'], i['average_price'], settings[0]["retail_primary_warehouse"], 'None')
                )
                default_preview_added = True
    
    p3 = check_promo_3(i, settings[0]["free_warehouse"], settings[0]["expiry_date_limit"])
    if p3:
        if p3['free_available_qty'] > 0:
            promo_type = 'Buy x get another y item'
            promo_free.append(
                promo_free_helper(i['item_code'], p3['free_item'], p3['free_qty'], 0, p3['free_available_qty'], promo_type)
            )
            sales_preview.append(
                sales_preview_helper(p3['free_item'], p3['free_available_qty'], p3['free_qty'], 0, settings[0]["free_warehouse"], promo_type)
            )
            if not default_preview_added:
                sales_preview.append(
                    sales_preview_helper(i['item_code'], i['quantity_available'], i['quantity_booked'], i['average_price'], settings[0]["retail_primary_warehouse"], 'None')
                )
                default_preview_added = True

    if not default_preview_added:
        sales_preview.append(
            sales_preview_helper(i['item_code'], i['quantity_available'], i['quantity_booked'], i['average_price'], settings[0]["retail_primary_warehouse"], 'None')
        )
    
    return sales_preview, promo_discount, promo_free

def promo_discount_helper(bought_item, free_item, dic_qty, dic, promo_type, amount):
    return {
        'bought_item': bought_item,
        'free_item': free_item,
        'dic_qty': dic_qty,
        'dic': dic,
        'promo_type': promo_type,
        'amount': amount
    }

def sales_preview_helper(item_code, qty_available, qty, average_price, warehouse, promo_type):
    return {
        'item_code': item_code,
        'qty_available': qty_available,
        'qty': qty,
        'average_price': average_price,
        'warehouse': warehouse,
        'promo_type': promo_type
    }

def promo_free_helper(bought_item, free_item, quantity, price, warehouse_quantity, promo_type):
    return {
        'bought_item': bought_item,
        'free_item': free_item,
        'qty': quantity,
        'price': price,
        'warehouse_quantity': warehouse_quantity,
        'promo_type': promo_type
    }

def sales_preview_cumulative(orders:list):
    f_list = []
    for i, val in enumerate(orders):
        f_list.append({
            'item_code': val['item_code'],
            'qty_available': val['qty_available'],
            'average_price': val['average_price'],
            'warehouse': val['warehouse'],
            'promo_type': val['promo_type']
        })

    for i, val in enumerate(f_list):
        if not orders[i]['qty'] > 0: 
            orders.pop(i)
            f_list.pop(i)
            continue

        if i != f_list.index(val):
            orders[f_list.index(val)]['qty'] += orders[i]['qty']
            orders.pop(i)
            f_list.pop(i)

    return orders

def free_preview_cumulative(orders: list):
    f_list = []
    for i, val in enumerate(orders):
        f_list.append({
            'bought_item': val['bought_item'],
            'free_item': val['free_item'],
            'price': val['price'],
            'warehouse_quantity': val['warehouse_quantity'],
            'promo_type': val['promo_type']
        })

    for i, val in enumerate(f_list):
        if not orders[i]['qty'] > 0: 
            orders.pop(i)
            f_list.pop(i)
            continue

        if i != f_list.index(val):
            orders[f_list.index(val)]['qty'] += orders[i]['qty']
            orders.pop(i)
            f_list.pop(i)

    return orders

def discount_preview_cumulative(orders: list):
    f_list = []
    for i, val in enumerate(orders):
        f_list.append({
            'bought_item': val['bought_item'],
            'free_item': val['free_item'],
            'dic': val['dic'],
            'promo_type': val['promo_type'],
            'amount': val['amount']
        })

    for i, val in enumerate(f_list):
        if not orders[i]['dic_qty'] > 0: 
            orders.pop(i)
            f_list.pop(i)
            continue

        if i != f_list.index(val):
            orders[f_list.index(val)]['dic_qty'] += orders[i]['dic_qty']
            orders.pop(i)
            f_list.pop(i)

    return orders

def quotation_preview_cumulative(orders:list):
    f_list = []
    for i, val in enumerate(orders):
        f_list.append({
            'item_code': val['item_code'],
            'average': val['average'],
        })

    for i, val in enumerate(f_list):
        if not orders[i]['quantity'] > 0: 
            orders.pop(i)
            f_list.pop(i)
            continue

        if i != f_list.index(val):
            orders[f_list.index(val)]['quantity'] += orders[i]['quantity']
            orders.pop(i)
            f_list.pop(i)

    return orders

def customer_allowed_for_promo(customer):
    a = frappe.db.get_value('Customer', {'name': customer}, 'pch_sales_promo', as_dict=1)
    if not a: return False
    if a.get('pch_sales_promo') is None: return False
    if a.get('pch_sales_promo', 0) != 1: return False
    return True 

def handle_quotation_preview(q):
    return {
        'item_code': q['item_code'],
        'quantity': q['qty'],
        'average': q['average_price']
    }

@frappe.whitelist()
def sales_promos(company, customer, order_list):
    order_list = json.loads(order_list)
    settings = fetch_fulfillment_settings(company, customer)

    order_preview = []
    quotation_preview = []
    promo_discount = []
    promo_free = []

    for x in order_list:
        if x.get('rate_contract'):
            order_preview.append(
                sales_preview_helper(x['item_code'], x['quantity_available'], x['quantity_booked'], x['average_price'], settings[0]["retail_primary_warehouse"], 'None')
            )
            continue

        print('*'*150)
        s = {}
        q = {}
        
        if x['quantity_available'] < x['quantity_booked']:
            if x['quantity_available'] > 0:
                s.update(x)
                s['quantity_booked'] = s['quantity_available']

            q.update(x)
            q['qty'] = q['quantity_booked'] - q['quantity_available']
        else:
            s.update(x)

        sales_promo_appicable = customer_allowed_for_promo(customer)
        if not sales_promo_appicable:
            if bool(s):
                order_preview.append(
                    sales_preview_helper(s['item_code'], s['quantity_available'], s['quantity_booked'], s['average_price'], settings[0]["retail_primary_warehouse"], 'None')
                )
        
        print('sales order', s, bool(s))
        print('quatation order', q, bool(q))
        
        if bool(s) and sales_promo_appicable:
            p_preview, p_discount, p_free = handle_sales_promo(x, settings)

            order_preview.extend(p_preview)
            promo_discount.extend(p_discount)
            promo_free.extend(p_free)
        
        if bool(q):
            q_preview = handle_quotation_preview(q)

            quotation_preview.append(q_preview)
    
    order_preview = sales_preview_cumulative(order_preview)
    promo_discount = discount_preview_cumulative(promo_discount)
    promo_free = free_preview_cumulative(promo_free)
    quotation_preview = quotation_preview_cumulative(quotation_preview)

    s_total = 0
    q_total = 0
    if order_preview:
        s_total = sum(sp['qty'] * sp['average_price'] for sp in order_preview)
    if quotation_preview:
        q_total = sum(qp['quantity'] * qp['average'] for qp in quotation_preview)
    
    total = s_total + q_total
    print(total)
    
    return dict(sales_preview = order_preview, quotation_preview = quotation_preview, discount_preview = promo_discount, free_preview = promo_free, total_amount = total)
    

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
def sales_order_container(customer, company, customer_type, sales_preview, quotation_preview):
    
    sales_preview = json.loads(sales_preview)
    quotation_preview = json.loads(quotation_preview)

    abbr = fetch_company_abbr(company)

    gst_detail = fetch_gst_detail(company)
    customer_in_state = check_customer_state(customer, company)
    if customer_in_state.get('valid'):
        tax = gst_detail['gst_in_state']
        tax_detail = fetch_tax_detail(gst_detail['gst_in_state'])
    else:
        tax = gst_detail['gst_out_state']
        tax_detail = fetch_tax_detail(gst_detail['gst_out_state'])

    
    delivery_warehouse = ""
    fulfillment_settings = fetch_fulfillment_settings(company, customer)
    delivery_warehouse = ""
    if customer_type == "Retail":
        delivery_warehouse = fulfillment_settings[0]["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        delivery_warehouse = fulfillment_settings[0]["hospital_warehouse"]
    elif customer == "Institutional":
        delivery_warehouse = fulfillment_settings[0]["institutional_warehouse"]

    delivery_date = datetime.datetime.today()
    delivery_date = delivery_date + datetime.timedelta(2)
    
    outerJson_so = {
        "doctype": "Sales Order",
        "naming_series": "SO-DL-",
        "customer": customer,
        "delivery_date": delivery_date,
        "pch_picking_status": "Ready for Picking",
        "pch_sales_order_purpose": "Delivery",
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

    for s in sales_preview:
        innerJson_so = {
            "doctype": "Sales Order Item",
            "item_code": s["item_code"],
            "qty": s["quantity"],
            "rate": s["average"],
            "warehouse": s["warehouse"],
            "promo_type": s["promo_type"]
        }

        outerJson_so["items"].append(innerJson_so)
    
    for q in quotation_preview:
        innerJson_qo = {
            "doctype": "Quotation Item",
            "item_code": q["item_code"],
            "qty": q["quantity"],
            "rate": q["average"],
        }

        outerJson_qo["items"].append(innerJson_qo)
    
    innerJson_tax_list = []
    if customer_in_state.get('valid'):
        for x in tax_detail['detail']:
            if x.get('account_head') == f'Output Tax SGST - {abbr}':
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

    so_name = ""
    qo_name = ""

    if outerJson_so["items"]:
        doc_so = frappe.new_doc("Sales Order")
        doc_so.update(outerJson_so)
        doc_so.save()
        so_name = doc_so.name

    if outerJson_qo["items"]:
        doc_qo = frappe.new_doc("Quotation")
        doc_qo.update(outerJson_qo)
        doc_qo.save()
        qo_name = doc_qo.name

    return dict(so_name = so_name, qo_name = qo_name)

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