from errno import EALREADY
import json
from operator import le
from tracemalloc import start
from braintree import Discount
import frappe
import datetime

from numpy import promote_types

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
    if len(warehouse) > 1:
        stock_data_batch = frappe.db.sql(f"""
	    	select batch_id, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
	    	from `tabBatch`
	    		join `tabStock Ledger Entry` ignore index (item_code, warehouse)
	    			on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
	    	where `tabStock Ledger Entry`.item_code = '{item_code}' AND warehouse in {tuple(warehouse)}
	    		and `tabStock Ledger Entry`.is_cancelled = 0
	    	group by batch_id
	    	order by `tabBatch`.creation ASC
	    """, as_dict=True)

        stock_data_batchless = frappe.db.sql(
            f"""select batch_no as batch_id, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
            where item_code = '{item_code}' and warehouse in {tuple(warehouse)} and (batch_no is null or batch_no = '')""",
            as_dict=True
        )
    else:
        stock_data_batch = frappe.db.sql(f"""
	    	select batch_id, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
	    	from `tabBatch`
	    		join `tabStock Ledger Entry` ignore index (item_code, warehouse)
	    			on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
	    	where `tabStock Ledger Entry`.item_code = '{item_code}' and warehouse = '{warehouse[0]}'
	    		and `tabStock Ledger Entry`.is_cancelled = 0
	    	group by batch_id
	    	order by `tabBatch`.creation ASC
	    """, as_dict=True)

        stock_data_batchless = frappe.db.sql(
            f"""select batch_no as batch_id, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
            where item_code = '{item_code}' and warehouse = '{warehouse[0]}' and (batch_no is null or batch_no = '')""",
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

def handle_stock_details(item_code, customer_type, settings):
    today = datetime.date.today()

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]

    if len(warehouse) > 1:        
        stock_data_batch = frappe.db.sql(f"""
                select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code = '{item_code}' AND warehouse in {tuple(warehouse)}
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by expiry_date ASC, warehouse DESC
            """, as_dict=True)

        stock_data_batchless = frappe.db.sql(
            f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
            where item_code = '{item_code}' and warehouse in {tuple(warehouse)} and (batch_no is null or batch_no = '')
            group by item_code, warehouse""",
            as_dict=True
        )

        sales_data = frappe.db.sql(
            f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where docstatus = 1 and item_code = '{item_code}' and warehouse in {tuple(warehouse)}""", as_dict=True
        )
    else:
        stock_data_batch = frappe.db.sql(f"""
                select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code = '{item_code}' AND warehouse = '{warehouse[0]}'
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by expiry_date ASC, warehouse DESC
            """, as_dict=True)

        stock_data_batchless = frappe.db.sql(
            f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
            where item_code = '{item_code}' and warehouse = '{warehouse[0]}' and (batch_no is null or batch_no = '')
            group by item_code, warehouse""",
            as_dict=True
        )
        
        sales_data = frappe.db.sql(
            f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where docstatus = 1 and item_code = '{item_code}' and warehouse = '{warehouse[0]}'""", as_dict=True
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

    return dict(available_qty = available_qty, stock_data = stock_data_batch.extend(stock_data_batchless), sales_qty = sales_data[0]["pending_qty"])

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
    
# Buy x get same x
def fetch_sales_promos_get_same_item(item_code, customer_type, free_warehouse):
    sales_promos_quantity = []
    promos_sale = []
    i = [x["item_code"] for x in item_code]
    print("Item",i)
    
    today = datetime.datetime.today()
    # if customer_type == "Retail":
    if len(item_code) > 1:
        sales_data = frappe.db.sql(
            f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code in {tuple(i)} and warehouse = '{free_warehouse}'""", as_dict=True
        )
        promos = frappe.db.sql(
            f""" select sp.start_date, sp.end_date, 
            pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
            pt.bought_item, sle.actual_qty
            from  `tabSales Promos` as sp  
            inner join `tabPromo Type 2` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
            where pt.bought_item in {tuple(i)} and sle.warehouse = '{free_warehouse}'
            """, as_dict = True
        )
    else:
        sales_data = frappe.db.sql(
            f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{i[0]}' and warehouse = '{free_warehouse}'""", as_dict=True
        )
        promos = frappe.db.sql(
            f""" select sp.start_date, sp.end_date, 
            pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
            pt.bought_item, sle.actual_qty
            from  `tabSales Promos` as sp  
            inner join `tabPromo Type 2` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
            where pt.bought_item = '{i[0]}' and sle.warehouse = '{free_warehouse}'
            """, as_dict = True
        )
    print("promos......", promos)
    if len(promos) > 0:
        for i in range (len(promos)):
            if(promos[i]["start_date"] <= today <= promos[i]["end_date"]): 
                for j in item_code:
                    if promos[i]["bought_item"] == j["item_code"]:
                        sales_promos_details = ((j["quantity_booked"])//(promos[i]["for_every_quantity_that_is_bought"]))
                        sales_promos_quantity = sales_promos_details*((promos[i]["quantity_of_free_items_thats_given"]))
                        qty = promos[i]["actual_qty"] - sales_data[0]["pending_qty"]
                        promos_sale.append({"qty":sales_promos_quantity, "bought_item":promos[i]["bought_item"], "promo_item": promos[i]["bought_item"], "w_qty" : qty})
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})
  

# buy x get another y item
def fetch_sales_promos_get_diff_item(item_code, customer_type, free_warehouse):
    sales_promos_quantity = []
    print("freeware", free_warehouse)
    promos_sale = []
    free_items = []
    i = [x["item_code"] for x in item_code]
    
    today = datetime.datetime.today()
    # if customer_type == "Retail":
    if len(item_code) > 1:
        
        promos = frappe.db.sql(
            f""" select sp.start_date, sp.end_date, 
            pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
            pt.bought_item, pt.free_item, sle.actual_qty
            from  `tabSales Promos` as sp  
            inner join `tabPromo Type 3` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
            where pt.bought_item in {tuple(i)} and sle.warehouse = '{free_warehouse}'
            """, as_dict = True
        )
    else:
        promos = frappe.db.sql(
            f""" select sp.start_date, sp.end_date, 
            pt.for_every_quantity_that_is_bought, pt.quantity_of_free_items_thats_given,
            pt.bought_item, pt.free_item, sle.actual_qty
            from  `tabSales Promos` as sp  
            inner join `tabPromo Type 3` as pt on pt.parent = sp.name
            inner join `tabStock Ledger Entry` as sle on pt.bought_item = sle.item_code
            where pt.bought_item = '{i[0]}' and sle.warehouse = '{free_warehouse}'
            """, as_dict = True
        )
    print("......", promos)
    if len(promos) > 0:
        for i in range (len(promos)):
            free_items.append(promos[i]["free_item"])
            if len(free_items) > 1:
                sales_data = frappe.db.sql(
                    f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code in {tuple(free_items)} and warehouse = '{free_warehouse}'""", as_dict=True
                )
            else:
                sales_data = frappe.db.sql(
                    f"""select sum(qty - delivered_qty) as pending_qty from `tabSales Order Item` where item_code = '{free_items[0]}' and warehouse = '{free_warehouse}'""", as_dict=True
                )

            if(promos[i]["start_date"] <= today <= promos[i]["end_date"]): 
                for j in item_code:
                    if promos[i]["bought_item"] == j["item_code"]:
                        sales_promos_details = ((j["quantity_booked"])//(promos[i]["for_every_quantity_that_is_bought"]))
                        sales_promos_quantity = sales_promos_details*((promos[i]["quantity_of_free_items_thats_given"]))
                        qty = promos[i]["actual_qty"] - sales_data[0]["pending_qty"]
                        promos_sale.append({"qty" : sales_promos_quantity, "bought_item":promos[i]["bought_item"], "promo_item" : promos[i]["free_item"], "w_qty" : promos[i]["actual_qty"], "w_qty" : qty})
                        print("sales qunt diif", sales_promos_quantity)
    return dict({"Promo_sales" : promos_sale, "Promos" : promos, "sales_data" : sales_data})



@frappe.whitelist()
def fulfillment_settings_container(company):
    fulfillment_settings = fetch_fulfillment_settings(company)
    return fulfillment_settings[0]

@frappe.whitelist()
def customer_type_container(customer):
    customer_type = fetch_customer_type(customer)
    return customer_type

@frappe.whitelist()
def sales_promos(item_code, customer_type, company):
    item_code = json.loads(item_code)
    settings = fetch_fulfillment_settings(company)
    print("settings", settings)
    print('item code received', item_code, type(item_code))
    sales_promos_same_item = fetch_sales_promos_get_same_item(item_code, customer_type, settings[0]["free_warehouse"])
    print("Sales Promo....", sales_promos_same_item)
    sales_promo_diff_items = fetch_sales_promos_get_diff_item(item_code, customer_type, settings[0]["free_warehouse"])
    print("Sales promo diff items",sales_promo_diff_items)
    sales_promos_items = sales_promos_same_item["Promo_sales"] + sales_promo_diff_items["Promo_sales"]
    print("sales promos items", sales_promos_items)

    return dict(sales_promos_items= sales_promos_items, bought_item = item_code, sales_promos_same_item = sales_promos_same_item, sales_promo_diff_items = sales_promo_diff_items )



@frappe.whitelist()
def item_qty_container(company, item_code, customer_type):
    fulfillment_settings = fetch_fulfillment_settings(company)
    stock_detail = fetch_item_details(item_code, customer_type, fulfillment_settings[0])
    handled_stock = handle_stock_details(item_code, customer_type, fulfillment_settings[0])
    price_details = fetch_average_price(stock_detail, item_code)
    # sales_promo = fetch_sales_promos(item_code)
    return dict(available_qty = handled_stock["available_qty"], average_price = price_details["average_price"], price_details = price_details, stock_detail = stock_detail, qty_detail = handled_stock) 

@frappe.whitelist()
def sales_order_container(customer, order_list, company, customer_type, free_promos):
    print(order_list)
    fulfillment_settings = fetch_fulfillment_settings(company)
    if customer_type == "Retail":
        delivery_warehouse = fulfillment_settings[0]["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        delivery_warehouse = fulfillment_settings[0]["hospital_warehouse"]
    elif customer == "Institutional":
        delivery_warehouse = fulfillment_settings[0]["institutional_warehouse"]
    free_promos = json.loads(free_promos)
    order_list = json.loads(order_list)
    delivery_date = datetime.datetime.today()
    delivery_date = delivery_date + datetime.timedelta(2)
    outerJson_so = {
        "doctype": "Sales Order",
        "naming_series": "SO-DL-",
        "customer": customer,
        "delivery_date": delivery_date,
        "pch_sales_order_purpose": "Delivery",
        "set_warehouse": delivery_warehouse,
        "items": [],
    }

    outerJson_qo = {
        "doctype": "Quotation",
        "naming_series": "QTN-DL-",
        "party_name": customer,
        "set_warehouse": delivery_warehouse,
        "items": []
    }

    for data in order_list:
        if data["quantity_booked"] == 0: continue
        if data["quantity_booked"] > data["quantity_available"]:
            if data["quantity_available"] > 0:
                innerJson_so = {
                    "doctype": "Sales Order Item",
                    "item_code": data["item_code"],
                    "qty": data["quantity_available"],
                    "rate": data["average_price"],
                }
            innerJson_qo = {
                "doctype": "Quotation Item",
                "item_code": data["item_code"],
                "qty": data["quantity_booked"] - data["quantity_available"],
                "rate": data["average_price"],
            }
        else:
            innerJson_so = {
                    "doctype": "Sales Order Item",
                    "item_code": data["item_code"],
                    "qty": data["quantity_booked"],
                    "rate": data["average_price"],
                }
        try:
            outerJson_so["items"].append(innerJson_so)
        except:
            pass
        try:
            outerJson_qo["items"].append(innerJson_qo)
        except:
            pass

    for free in free_promos:
        if free["warehouse_quantity"] > 0:
            innerJson_so = {
                    "doctype": "Sales Order Item",
                    "item_code": free["free_items"],
                    "qty": free["quantity"],
                    "warehouse": "Free - YR"
                }
        try:
            outerJson_so["items"].append(innerJson_so)
        except:
            pass
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