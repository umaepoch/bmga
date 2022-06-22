import json
import frappe
import datetime
import re

def fetch_item_list(so_name):
    item_list = frappe.db.sql(
        f"""SELECT item_code, qty, warehouse, name as so_detail, promo_type  FROM `tabSales Order Item` WHERE parent = '{so_name}'""",
        as_dict=True
    )

    print("*-+"*50)
    print("ITEM LIST")
    for i in item_list:
        print(i)
    print("*-+"*50)

    return item_list

def fetch_customer_type(so_name):
    customer = frappe.db.sql(
        f"""SELECT customer FROM `tabSales Order` WHERE name = '{so_name}'""",
        as_dict=True
    )
    customer_group = frappe.db.sql(
        f"""SELECT customer_group FROM `tabCustomer` WHERE name = '{customer[0]["customer"]}'""",
        as_dict=True
    )
    customer_type = frappe.db.sql(
        f"""SELECT pch_customer_type FROM `tabCustomer Group` WHERE name = '{customer_group[0]["customer_group"]}'""",
        as_dict=True
    )
    return customer_type[0]["pch_customer_type"]

def fetch_fulfillment_settings(company):
    fs_name = frappe.db.sql(
        f"""SELECT name, expiry_date_limit FROM `tabFulfillment Settings V1` WHERE company = '{company}'""",
        as_dict=True
    )
    if fs_name:
        settings = frappe.db.sql(
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse, qc_and_dispatch, free_warehouse
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )
        settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
    else:
        settings = [None]
    return settings[0]

def fetch_pick_put_list_data(customer_type, sales_list, settings):
    items = [data["item_code"] for data in sales_list]
    items = re.sub(r',\)$', ')', str(tuple(items)))

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"], settings["free_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"], settings["free_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"], settings["free_warehouse"]]
    
    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))

    pick_put_list_stock = frappe.db.sql(
        f"""select ppli.item as item_code, ppli.batch, ppli.batch_picked, ppli.warehouse, ppli.quantity_to_be_picked, ppli.quantity_picked, ppli.warehouse
        from `tabPick Put List Items` as ppli
            join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
        where ppli.item in {items} and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse in {warehouse}""",
        as_dict=1
    )

    return pick_put_list_stock

def update_stock_detail_with_picked_stock(stock_data, free_data, picked_data):
    print("*"*100)
    for s in stock_data:
        print(s)

    struct_pick = {}

    print("-"*100)
    for p in picked_data:
        print(p)
        if p["quantity_picked"] is not None:
            p_qty = p["quantity_picked"]
        elif p["quantity_to_be_picked"] is not None:
            p_qty = p["quantity_to_be_picked"]
        else:
            p_qty = 0
        
        if p["batch_picked"] is not None:
            p_batch = p["batch_picked"]
        elif p["batch"] is not None:
            p_batch = p["batch"]
        else:
            p_batch = ''
        if p["warehouse"] not in struct_pick:  
            struct_pick[p["warehouse"]] = {}
            struct_pick[p["warehouse"]][p["item_code"]] = {}
            struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty  
            if p["item_code"] not in struct_pick[p["warehouse"]]:
                struct_pick[p["warehouse"]][p["item_code"]] = {}
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
            else:
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
        else:
            if p["item_code"] not in struct_pick[p["warehouse"]]:
                struct_pick[p["warehouse"]][p["item_code"]] = {}
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
            else:
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
    
    print("Struct pick")
    print(struct_pick)     
    for s in stock_data:
        try:
            if s["actual_qty"] > struct_pick[s["warehouse"]][s["item_code"]][s["batch_id"]]:
                s["actual_qty"] -= struct_pick[s["warehouse"]][s["item_code"]][s["batch_id"]]
            else:
                s["actual_qty"] = 0
        except:
            pass
    
    for f in free_data:
        try:
            if f["actual_qty"] > struct_pick[f["warehouse"]][f["item_code"]][f["batch_id"]]:
                f["actual_qty"] -= struct_pick[f["warehouse"]][f["item_code"]][f["batch_id"]]
            else:
                f["actual_qty"] = 0
        except:
            pass
    
    print("stock after pick -")
    for s in stock_data:
        print(s)
    
    print("free after pick -")
    for f in free_data:
        print(f)
    
    return stock_data, free_data
        

def fetch_stock_details(customer_type, sales_list, settings):
    items = [data["item_code"] for data in sales_list]
    items = re.sub(r',\)$', ')', str(tuple(items)))

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]

    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))
    
    if settings["retail_primary_warehouse"] >= settings["retail_bulk_warehouse"] :
        warehouse_order = "DESC"
    else:
        warehouse_order = "ASC"
    
    print("QUERY", 
    f"""
        select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabStock Ledger Entry`.item_code in {items} AND warehouse in {warehouse}
            and `tabStock Ledger Entry`.is_cancelled = 0
        group by batch_id, warehouse
        order by warehouse {warehouse_order}, expiry_date ASC
    """)

    stock_data_batch = frappe.db.sql(f"""
        select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabStock Ledger Entry`.item_code in {items} AND warehouse in {warehouse}
            and `tabStock Ledger Entry`.is_cancelled = 0
        group by batch_id, warehouse
        order by warehouse {warehouse_order}, expiry_date ASC
    """, as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code in {items} and warehouse in {warehouse} and (batch_no is null or batch_no = '')
        group by item_code, warehouse
        order by warehouse {warehouse_order}""",
        as_dict=True
    )
    
    for data in stock_data_batchless:
        if data.get("actual_qty") is None: continue
        stock_data_batch.append(data)

    return stock_data_batch

def handle_stock_data(stock_data):
    stock_map = {}
    for data in stock_data:
        if data["item_code"] not in stock_map:
            stock_map[data["item_code"]] = []
        batch = {}
        batch["batch_no"] = data["batch_id"]
        batch["warehouse"] = data["warehouse"]
        batch["stock_uom"] = data["stock_uom"]
        try:
            batch["expiry_date"] = data["expiry_date"]
        except:
            pass
        batch["actual_qty"] = data["actual_qty"]
        stock_map[data["item_code"]].append(batch) 
    return stock_map

def handle_free_data(free_data):
    stock_map = {}
    for data in free_data:
        if data["item_code"] not in stock_map:
            stock_map[data["item_code"]] = []
        batch = {}
        batch["batch_no"] = data["batch_id"]
        batch["warehouse"] = data["warehouse"]
        batch["stock_uom"] = data["stock_uom"]
        try:
            batch["expiry_date"] = data["expiry_date"]
        except:
            pass
        batch["actual_qty"] = data["actual_qty"]
        stock_map[data["item_code"]].append(batch) 
    return stock_map

def fetch_wbs_location(customer_type, sales_list, settings):
    print('*'*50)
    print(sales_list)
    items = [data["item_code"] for data in sales_list]
    # print(items)
    if customer_type == "Retail":
        warehouse = settings["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        warehouse = settings["hospital_warehouse"]
    elif customer_type == "Institutional":
        warehouse = settings["institutional_warehouse"]

    wbs_setting_id = frappe.db.sql(
        f"""select name, start_date from `tabWBS Settings` where warehouse = '{warehouse}' order by start_date DESC""", as_dict=True
    )
    if len(wbs_setting_id) == 0:
        return {}
    wbs_location_list = []
    for item in items:
        wbs_location = frappe.db.sql(
            f"""select item_code, `tabWBS Storage Location`.name_of_attribute_id, `tabWBS Storage Location`.name, `tabWBS Storage Location`.rarb_warehouse
            from `tabWBS Stored Items`
                join `tabWBS Storage Location`
                    on (`tabWBS Stored Items`.parent = `tabWBS Storage Location`.name)
            where item_code = '{item}' and wbs_settings_id = '{wbs_setting_id[0]["name"]}'""", as_dict=True
        )
        if len(wbs_location) > 0:
            # print("SPCIFIC")
            # print(wbs_location)
            wbs_location_list.append(wbs_location[0])
        else:
            # fetch from wbs stock balance report
            wbs_location_anyitem = frappe.db.sql(
                f"""select item_code, `tabStock Entry Detail`.creation, `tabWBS Storage Location`.name_of_attribute_id, `tabWBS Storage Location`.name, `tabWBS Storage Location`.rarb_warehouse 
                from `tabStock Entry Detail`
                    join `tabWBS Storage Location`
                        on (target_warehouse_storage_location = `tabWBS Storage Location`.name)
                where item_code = '{item}' and target_warehouse_storage_location is not null and `tabStock Entry Detail`.docstatus = 1
                order by `tabStock Entry Detail`.creation DESC""",
                as_dict=True
            )
            if len(wbs_location_anyitem) > 0:
                wbs_location_list.append(wbs_location_anyitem[0])
            

    wbs_structured = {}
    for data in wbs_location_list:
        if data["rarb_warehouse"] not in wbs_structured:
            wbs_structured[data["rarb_warehouse"]] = {}
        if data["item_code"] not in wbs_structured[data["rarb_warehouse"]]:
            wbs_structured[data["rarb_warehouse"]][data["item_code"]] = {}
        wbs_structured[data["rarb_warehouse"]][data["item_code"]]["wbs_storage_location_id"] = data["name_of_attribute_id"]
        wbs_structured[data["rarb_warehouse"]][data["item_code"]]["wbs_storage_location"] = data["name"]
    print("+"*100)
    print(wbs_structured)
    return wbs_structured

def sales_order_handle(sales_list, stock_data, free_data, wbs_details, settings):
    today = datetime.date.today()
    pick_up_list = []
    free_pick_list = []

    for sales in sales_list:
        to_pickup = sales["qty"]
        print("SALES LIST", sales)
        if sales["warehouse"] != settings['free_warehouse']:
            print("Normal Data")
            if stock_data.get(sales["item_code"]) is None: continue
            for stock in stock_data[sales["item_code"]]:
                if stock["actual_qty"] == 0: continue
                try:
                    date_delta = stock["expiry_date"] - today
                    if date_delta.days < settings['expiry_date']: continue
                except:
                    pass
                pick_up = {}
                pick_up["item_code"] = sales["item_code"]
                pick_up["stock_uom"] = stock["stock_uom"]
                pick_up["warehouse"] = stock["warehouse"]
                pick_up["promo_type"] = sales["promo_type"]
                pick_up["so_detail"] = sales["so_detail"]
                try:
                    pick_up["wbs_storage_location_id"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location_id"]
                    pick_up["wbs_storage_location"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location"]
                except:
                    pick_up["wbs_storage_location_id"] = ''
                    pick_up["wbs_storage_location"] = ''
                if stock["actual_qty"] >= to_pickup:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = to_pickup
                    stock["actual_qty"] -= to_pickup
                    to_pickup = 0
                else:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = stock["actual_qty"]
                    to_pickup -= stock["actual_qty"]
                    stock["actual_qty"] = 0
                pick_up_list.append(pick_up)
                if to_pickup == 0: break
        else:
            print("Free Data")
            if free_data.get(sales["item_code"]) is None: continue
            for stock in free_data[sales["item_code"]]:
                if stock["actual_qty"] == 0: continue
                try:
                    date_delta = stock["expiry_date"] - today
                    if date_delta.days < settings['expiry_date']: continue
                except:
                    pass
                pick_up = {}
                pick_up["item_code"] = sales["item_code"]
                pick_up["stock_uom"] = stock["stock_uom"]
                pick_up["warehouse"] = stock["warehouse"]
                pick_up["promo_type"] = sales["promo_type"]
                pick_up["so_detail"] = sales["so_detail"]
                try:
                    pick_up["wbs_storage_location_id"] = wbs_details[settings["retail_primary_warehouse"]][sales["item_code"]]["wbs_storage_location_id"]
                    pick_up["wbs_storage_location"] = wbs_details[settings["retail_primary_warehouse"]][sales["item_code"]]["wbs_storage_location"]
                except:
                    pick_up["wbs_storage_location_id"] = ''
                    pick_up["wbs_storage_location"] = ''
                if stock["actual_qty"] >= to_pickup:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = to_pickup
                    stock["actual_qty"] -= to_pickup
                    to_pickup = 0
                else:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = stock["actual_qty"]
                    to_pickup -= stock["actual_qty"]
                    stock["actual_qty"] = 0
                free_pick_list.append(pick_up)
                if to_pickup == 0: break
        
    return pick_up_list + free_pick_list

def fetch_free_stock_detail(free_list, free_warehouse):
    print("Free warehouse fetch!")
    items = [data["item_code"] for data in free_list]

    if not (len(items) > 0): return []

    items = re.sub(r',\)$', ')', str(tuple(items)))

    stock_data_batch = frappe.db.sql(f"""
        select batch_id, `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabStock Ledger Entry`.item_code in {items} and warehouse = '{free_warehouse}'
            and `tabStock Ledger Entry`.is_cancelled = 0
        group by batch_id, warehouse
        order by expiry_date ASC
    """, as_dict=True)
    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code in {items} and warehouse = '{free_warehouse}' and (batch_no is null or batch_no = '')
        group by item_code, warehouse
        """,
        as_dict=True
    )
    
    for data in stock_data_batchless:
        if data.get("actual_qty") is None: continue
        stock_data_batch.append(data)
    
    print("*-/"*50)
    for data in stock_data_batch:
        print(data)
    
    return stock_data_batch

@frappe.whitelist()
def item_list_container(so_name, company):
    fulfillment_settings = fetch_fulfillment_settings(company)
    print("Settings", fulfillment_settings)
    customer_type = fetch_customer_type(so_name)

    if customer_type == "Retail":
        warehouse = fulfillment_settings["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        warehouse = fulfillment_settings["hospital_warehouse"]
    elif customer_type == "Institutional":
        warehouse = fulfillment_settings["institutional_warehouse"]

    sales_list = fetch_item_list(so_name)
    print()
    print("SALES LIST", sales_list)
    free_list = list(filter(lambda x:x["warehouse"] == fulfillment_settings["free_warehouse"], sales_list))
    print()
    print("Free List", free_list)
    order_list = list(filter(lambda x:x["warehouse"] in warehouse, sales_list))
    print()
    print("Order List", order_list)

    stock_data = fetch_stock_details(customer_type, order_list, fulfillment_settings)
    free_data = fetch_free_stock_detail(free_list, fulfillment_settings["free_warehouse"])
    p_stock = fetch_pick_put_list_data(customer_type, order_list, fulfillment_settings)
    print("*"*100)
    for p in p_stock:
        print(p)
    stock_data, free_data = update_stock_detail_with_picked_stock(stock_data, free_data, p_stock)
    print("STOCK DATA")
    for s in stock_data:
        print(s)
    handled_data = handle_stock_data(stock_data)
    handled_free = handle_free_data(free_data)
    print("HANDLED FREE")
    print(handled_free)
    print("HANDLED DATA")
    print(handled_data)
    wbs_details = fetch_wbs_location(customer_type, sales_list, fulfillment_settings)
    pick_put_list = sales_order_handle(sales_list, handled_data, handled_free, wbs_details, fulfillment_settings)
    return dict(free_data = free_data, order_list = order_list, free_list = free_list, p_stock = p_stock, wbs_details = wbs_details, pick_put_list = pick_put_list ,sales_list = sales_list, customer_type = customer_type, settings = fulfillment_settings, stock_data = handled_data)

def get_customer(so_name):
    customer = frappe.db.sql(
        f"""select customer from `tabSales Order` where name = '{so_name}'""", as_dict=1
    )
    return customer[0].customer

def fetch_batch_detail(batch, item_code):
    p = frappe.db.sql(
        f"""select pch_ptr as price from `tabBatch` where batch_id = '{batch}' and item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0 and p[0].get('price') is not None: return dict(price = p[0].get('price'))
    else : return dict(price = 0)

def fetch_batchless_detail(item_code):
    p = frappe.db.sql(
        f"""select rci.selling_price_for_customer as price
        from `tabRate Contract Item` as rci
            join `tabRate Contract` as rc on (rc.name = rci.parent)
        where rc.selling_price = 1 and rci.item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0 and p[0].get('price') is not None: return dict(price = p[0].get('price'))
    else : return dict(price = 0)

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
                    b = fetch_batch_detail(batch, item_code)
                    print(b)
                    return dict(price = b['price'] * discount)
                else:
                    b = fetch_batchless_detail(item_code)
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

def fetch_storage_location_from_id(id):
    location = frappe.db.sql(
        f"""select name from `tabWBS Storage Location` where name_of_attribute_id = '{id}'""",
        as_dict=1
    )

    return location[0]

def get_so_detail(so_name, item_code, warehouse, batch, qty):
    so_detail = frappe.db.sql(
        f"""select name from `tabSales Order Item`
        where parent = '{so_name}' and item_code = '{item_code}' and warehouse = '{warehouse}' and pch_batch_no = '{batch}' and qty = '{qty}'""",
        as_dict=1
    )
    
    return so_detail[0]

def generate_sales_invoice_json(customer, customer_type, so_name, sales_order, company, item_list, settings):
    due_date = datetime.datetime.today()
    discount = 1
    # due_date = due_date + datetime.timedelta(2)

    outerJson = {
        "doctype": "Sales Invoice",
        "naming_series": "SINV-DL-",
        "company": company,
        "customer": customer,
        "due_date": due_date,
        "update_stock": 1,
        "items": []
    }
    print("*"*150)
    print("SALES INVOICE")
    for item in item_list:
        print(item)
        
        qty, batch = ppli_qty_and_batch(item)
        if qty == 0: continue

        rate_contract = customer_rate_contract(customer) 
        if not rate_contract["valid"]:
            if item.get("promo_type") == "Buy x get same and discount for ineligible qty":
                discount = fetch_promo_type_5(item, sales_order, customer_type, settings)
            elif item.get("promo_type") == "Amount based discount":
                discount = fetch_promo_type_1(item, sales_order, customer_type, settings)
            else:
                discount = 1

        if item["warehouse"] == settings["free_warehouse"]:
            rate = {"price": 0}
        else:
            if batch:
                rate = fetch_batch_price(batch, item["item"], rate_contract["name"])
            else:
                rate = fetch_batchless_price(item["item"], rate_contract["name"])
        
        rate["price"] = rate["price"] * discount
        
        print("qty", qty)
        print(type(qty))
        print("batch", batch)
        print("rate", rate)
        print("*"*100)

        if qty <= 0: continue
        so_detail = get_so_detail(so_name, item['item'], item['warehouse'], batch, qty)
        if item.get("wbs_storage_location") != '' and item.get('warehouse') != settings['free_warehouse']:
            storage_id = item["wbs_storage_location"]
            storage_location = fetch_storage_location_from_id(storage_id)
            print("*" * 50)
            print("location", storage_location["name"], storage_id)
            innerJson = {
                "doctype": "Sales Invoice Item",
                "item_code": item["item"],
                "qty": qty,
                "price_list_rate": rate["price"],
                "rate": rate["price"],
                "warehouse": item["warehouse"],
                "warehouse_storage_location": storage_location["name"],
                "storage_location_id": storage_id,
                "batch_no": batch,
                "sales_order": so_name,
                "so_detail": so_detail['name'],
                "delivered_qty": qty
            }
        else:
            innerJson = {
                "doctype": "Sales Invoice Item",
                "item_code": item["item"],
                "qty": qty,
                "price_list_rate": rate["price"],
                "rate": rate["price"],
                "warehouse": item["warehouse"],
                "batch_no": batch,
                "sales_order": so_name,
                "so_detail": so_detail['name'],
                "delivered_qty": qty,
            }

        outerJson["items"].append(innerJson)

    """ for d in outerJson["items"]:
        print(d["item_code"], d["sales_order"], d["warehouse"], d["so_detail"], d["delivered_qty"], d["rate"]) """
    return outerJson

def ppli_qty_and_batch(item):
    if item.get("quantity_picked") is None:
        if item.get("quantity_to_be_picked") is None: qty = 0
        else: qty = item.get("quantity_to_be_picked")
    else:
        try:
            qty = int(item["quantity_picked"])
        except:
            qty = item.get("quantity_to_be_picked") 
    if item.get("batch_picked") is None:
        batch = item.get("batch")
    else:
        batch = item.get("batch_picked")
    
    return qty, batch

def discount_item_price(i, qty):
    today = datetime.date.today()

    d = frappe.db.sql(
        f"""select pt1.bought_item, pt1.discount_percentage, pt1.quantity_bought
        from `tabPromo Type 1` as pt1
            join `tabSales Promos` as sp on (sp.name = pt1.parent)
        where pt1.bought_item = '{i["item"]}' and sp.start_date <= '{today}' and sp.end_date >= '{today}'""",
        as_dict=1
    )

    print("*"*150)
    if len(d) > 0:
        print("Sales Type 1")
        print(d)
        d = sorted(d, key = lambda x : x["discount_percentage"], reverse=1)
        for x in d:
            if x["quantity_bought"] > qty: continue
            print(x)
            break
    else:
        print("Sales Type 5")
    
    print("*"*150)
    return d

def fetch_promo_type_5(i, sales_order, customer_type, settings):
    today = datetime.date.today()
    discount = 1

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]
    
    so_filter = list(filter(lambda x: x["warehouse"] in warehouse and x["item_code"] == i["item"], sales_order))
    print("so filter", so_filter)
    qty = sum(x['qty'] for x in so_filter)
    
    d = frappe.db.sql(
        f"""select pt.for_every_quantity_that_is_bought as b_qty, pt.discount as discount
        from `tabPromo Type 5` as pt
            join `tabSales Promos` as sp on (sp.name = pt.parent)
        where pt.bought_item = '{i["item"]}' and sp.start_date <= '{today}' and sp.end_date >= '{today}'
        order by pt.for_every_quantity_that_is_bought DESC""",
        as_dict=1
    )
    print(d)
    for x in d:
        print(qty)
        print(x)
        if qty >= x["b_qty"]:
            discount = (100 - int(x["discount"])) / 100
            print((100 - int(x["discount"])) / 100)
            break

    print("*-/"*25)
    print("discount", discount)
    # frappe.msgprint(f"discount percentage {discount} {qty} {d} {i['item']}")
    return discount

def fetch_promo_type_1(i, sales_order, customer_type, settings):
    today = datetime.date.today()
    discount = 1

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]
    
    so_filter = list(filter(lambda x: x["warehouse"] in warehouse and x["promo_type"] == "Amount based discount" and x["item_code"] == i["item"], sales_order))
    qty = int(so_filter[0]["qty"])

    d = frappe.db.sql(
        f"""select pt.quantity_bought as b_qty, pt.discount_percentage as discount
        from `tabPromo Type 1` as pt
            join `tabSales Promos` as sp on (pt.parent = sp.name)
        where pt.bought_item = '{i["item"]}' and sp.start_date <= '{today}' and sp.end_date >= '{today}'
        order by pt.quantity_bought DESC""",
        as_dict=1
    )   

    for x in d:
        if qty >= x["b_qty"]:
            discount = (100 - int(x["discount"])) / 100
            break
    print(discount)
    return discount

def customer_rate_contract(customer):
    rc = frappe.db.sql(
        f"""select name from `tabRate Contract` where customer = '{customer}'""",
        as_dict=1
    )

    if len(rc) > 0: return dict(valid = True, name = rc[0]["name"])
    else : return dict(valid = False, name = None)

def update_average_price(item_list, sales_order, customer_type, settings, customer):
    new_average_price = {}
    discount = 1

    for item in item_list:
        if item["warehouse"] == settings["free_warehouse"]: continue
        qty, batch = ppli_qty_and_batch(item)
        if qty == 0: continue

        rate_contract = customer_rate_contract(customer)
        if not rate_contract["valid"]:
            if item.get("promo_type") == "Buy x get same and discount for ineligible qty":
                discount = fetch_promo_type_5(item, sales_order, customer_type, settings)
            elif item.get("promo_type") == "Amount based discount":
                discount = fetch_promo_type_1(item, sales_order, customer_type, settings)
            else:
                discount = 1

        if batch:
            rate = fetch_batch_price(batch, item["item"], rate_contract["name"])
            print("NEW PRICE", fetch_batch_price(batch, item["item"], rate_contract["name"]))
        else:
            rate = fetch_batchless_price(item["item"], rate_contract["name"])
            # fetch_batchless_price
            print("NEW PRICE Batchless", fetch_batchless_price(item["item"], rate_contract["name"]))

        rate["price"] = rate["price"] * discount

        if item["item"] not in new_average_price:
            new_average_price[item["item"]] = {
                "qty": [qty],
                "price": [rate["price"]]
            }
            new_average_price[item["item"]] = {
                "normal": {
                    "qty": [],
                    "price": []
                },
                "promo": {
                    "qty": [],
                    "price": []
                }
            }
            if 0 < discount < 1:
                new_average_price[item["item"]]["promo"]["qty"].append(qty)
                new_average_price[item["item"]]["promo"]["price"].append(rate["price"])
            else:
                new_average_price[item["item"]]["normal"]["qty"].append(qty)
                new_average_price[item["item"]]["normal"]["price"].append(rate["price"])
        else:
            if qty is None: continue
            if 0 < discount < 1:
                new_average_price[item["item"]]["promo"]["qty"].append(qty)
                new_average_price[item["item"]]["promo"]["price"].append(rate["price"])
            else:
                new_average_price[item["item"]]["normal"]["qty"].append(qty)
                new_average_price[item["item"]]["normal"]["price"].append(rate["price"])
        
        try:
            new_average_price[item["item"]]["promo"]["average"] = sum([new_average_price[item["item"]]["promo"]["qty"][i] * new_average_price[item["item"]]["promo"]["price"][i] for i in range(len(new_average_price[item["item"]]["promo"]["qty"]))]) / sum(new_average_price[item["item"]]["promo"]["qty"])
        except:
            pass
        
        try:
            new_average_price[item["item"]]["normal"]["average"] = sum([new_average_price[item["item"]]["normal"]["qty"][i] * new_average_price[item["item"]]["normal"]["price"][i] for i in range(len(new_average_price[item["item"]]["normal"]["qty"]))]) / sum(new_average_price[item["item"]]["normal"]["qty"])
        except:
            pass

    return new_average_price 

def update_sales_order(sales_doc, average_price, free_warehouse):
    print(free_warehouse)
    print("update sales order", average_price)
    for child in sales_doc.get_all_children():
            if child.doctype != "Sales Order Item": continue
            sales_item_doc = frappe.get_doc(child.doctype, child.name)
            print(sales_item_doc.warehouse)
            print(free_warehouse)
            print(sales_item_doc.promo_type)
            print(sales_item_doc.warehouse == free_warehouse)
            print(sales_item_doc.promo_type == "None" or sales_item_doc.promo_type is None)
            if sales_item_doc.warehouse == free_warehouse:
                print("free price", sales_item_doc.rate)
                sales_item_doc.rate = 0
                print("free price", sales_item_doc.rate)
            elif sales_item_doc.promo_type == "None" or sales_item_doc.promo_type is None:
                sales_item_doc.rate = average_price[sales_item_doc.item_code]["normal"]["average"]
            else:
                try:
                    sales_item_doc.rate = average_price[sales_item_doc.item_code]["promo"]["average"]
                except:
                    sales_item_doc.rate = average_price[sales_item_doc.item_code]["normal"]["average"]
            sales_item_doc.save()

def update_sales_order_for_invoice(sales_doc, customer, customer_type, so_name, sales_order, item_list, settings):
    sales_doc.items = []
    discount = 1
    for item in item_list:
        
        qty, batch = ppli_qty_and_batch(item)
        if qty == 0: continue

        rate_contract = customer_rate_contract(customer) 
        if not rate_contract["valid"]:
            if item.get("promo_type") == "Buy x get same and discount for ineligible qty":
                discount = fetch_promo_type_5(item, sales_order, customer_type, settings)
            elif item.get("promo_type") == "Amount based discount":
                discount = fetch_promo_type_1(item, sales_order, customer_type, settings)
            else:
                discount = 1

        if item["warehouse"] == settings["free_warehouse"]:
            rate = {"price": 0}
        else:
            if batch:
                rate = fetch_batch_price(batch, item["item"], rate_contract["name"])
            else:
                rate = fetch_batchless_price(item["item"], rate_contract["name"])
        
        rate["price"] = rate["price"] * discount

        if qty <= 0: continue
        sales_doc.append('items', {
            'item_code': item['item'],
            'pch_batch_no': batch,
            'qty': qty,
            'rate': rate['price'],
            'warehouse': item['warehouse']
        })


def get_stock_balance(item_code, batch, warehouse):
    s = frappe.db.sql(
        f"""select sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabBatch`.batch_id = '{batch}' and `tabStock Ledger Entry`.warehouse = '{warehouse}' and `tabStock Ledger Entry`.item_code = '{item_code}'""",
        as_dict=1
    )

    print("stock balance", s)

    if len(s) > 0 and s[0]["actual_qty"] is None:
        s[0]["actual_qty"] = 0
        return s[0]
    else:
        return s[0]  

def get_stock_balance_batchless(item_code, warehouse):
    s = frappe.db.sql(
        f"""select sum(actual_qty) as actual_qty
        from `tabStock Ledger Entry`
        where warehouse = '{warehouse}' and item_code = '{item_code}' and (batch_no = '' or batch_no is null)""",
        as_dict=1
    )

    print("stock balance", s)

    if len(s) > 0 and s[0]["actual_qty"] is None:
        s[0]["actual_qty"] = 0
        return s[0]
    else:
        return s[0] 

def get_ppli_balance(item_code, batch, warehouse, so_name):
    s = frappe.db.sql(
        f"""select ppli.quantity_to_be_picked as pick_quantity
        from `tabPick Put List Items` as ppli
            join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
        where ppli.batch = '{batch}' and ppl.sales_order != '{so_name}' and ppli.item = '{item_code}' and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse = '{warehouse}'""",
        as_dict=1
    )
    print()
    print("-"*100)
    for i in s:
        print(i)
    print("-"*100)
    print()
    if len(s) > 0: return s[0]
    else: return None

def generate_material_receipt(item_list):
    name = None
    print("receipt", item_list)
    if len(item_list) > 0:
        outerJson = {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "items": []
        }
        for i in item_list:
            if not i.get("wbs_storage_location") == '':
                storage_id = i["wbs_storage_location"]
                storage_location = fetch_storage_location_from_id(storage_id)
                print(storage_id, storage_location)

                innerJson = {
                    "doctype": "Stock Entry Detail",
                    "item_code": i["item_code"],
                    "batch_no": i["batch"],
                    "t_warehouse": i["warehouse"],
                    "target_warehouse_storage_location": storage_location["name"],
                    "target_storage_location_id": storage_id,
                    "qty": i["qty"]
                }
                outerJson["items"].append(innerJson)
            else:
                innerJson = {
                    "doctype": "Stock Entry Detail",
                    "item_code": i["item_code"],
                    "batch_no": i["batch"],
                    "t_warehouse": i["warehouse"],
                    "qty": i["qty"]
                }
                outerJson["items"].append(innerJson)

        doc = frappe.new_doc("Stock Entry")
        doc.update(outerJson)
        doc.save()
        doc.submit()
        name = doc.name

        return name
    
def generate_material_issue(item_list):
    name = None
    print("issue", item_list)
    if len(item_list) > 0:
        outerJson = {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Issue",
            "items": []
        }
        for i in item_list:
            if not i.get("wbs_storage_location") == '':
                storage_id = i["wbs_storage_location"]
                storage_location = fetch_storage_location_from_id(storage_id)
                print(storage_id, storage_location)

                innerJson = {
                    "doctype": "Stock Entry Detail",
                    "item_code": i["item_code"],
                    "batch_no": i["batch"],
                    "s_warehouse": i["warehouse"],
                    "source_warehouse_storage_location": storage_location["name"],
                    "source_storage_location_id": storage_id,
                    "qty": i["qty"]
                }
                outerJson["items"].append(innerJson)
            else:
                innerJson = {
                    "doctype": "Stock Entry Detail",
                    "item_code": i["item_code"],
                    "batch_no": i["batch"],
                    "s_warehouse": i["warehouse"],
                    "qty": i["qty"]
                }
                outerJson["items"].append(innerJson)

        doc = frappe.new_doc("Stock Entry")
        doc.update(outerJson)
        doc.save()
        doc.submit()
        name = doc.name

        return name

def stock_correction(customer, so_name, company, item_list, settings):
    print("*"*150)
    m_receipt = []
    m_issue = []
    for i in item_list:
        if i["correction"] == 0 or i.get("quantity_picked") is None: continue
        if i.get("batch") == '':
            stock_balance = get_stock_balance_batchless(i["item"], i["warehouse"])
            ppli_balance = get_ppli_balance(i["item"], '', i["warehouse"], so_name)

            if ppli_balance:
                stock_balance["actual_qty"] -= ppli_balance["pick_quantity"] 

            print("stock balance", stock_balance)

            try:
                i["quantity_picked"] = int(i["quantity_picked"])
            except:
                continue
            if stock_balance["actual_qty"] < i["quantity_picked"]:
                print("material receip needed for", i)
                m_receipt.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = '', qty = i["quantity_picked"] - stock_balance["actual_qty"]))
            print("DIFFERENCE", stock_balance["actual_qty"] - int(i["quantity_picked"]))
            try:
                if int(i["quantity_picked"]) < i["quantity_to_be_picked"]:
                    print("material issue needed for:", i)
                    m_issue.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = '', qty = i["quantity_to_be_picked"] - int(i["quantity_picked"])))
            except:
                pass
        else:
            if i.get("batch_picked") is None: continue 
            stock_balance = get_stock_balance(i["item"], i["batch_picked"], i["warehouse"])
            ppli_balance = get_ppli_balance(i["item"], i["batch_picked"], i["warehouse"], so_name)
            if ppli_balance:
                stock_balance["actual_qty"] -= ppli_balance["pick_quantity"] 
            print(stock_balance)
            try:
                i["quantity_picked"] = int(i["quantity_picked"])
            except:
                continue
            if stock_balance["actual_qty"] < i["quantity_picked"]:
                print("material receip needed for", i)
                m_receipt.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = i["batch_picked"], qty = i["quantity_picked"] - stock_balance["actual_qty"]))
            try:
                if int(i["quantity_picked"]) < i["quantity_to_be_picked"]:
                    print("material issue needed for:", i)
                    m_issue.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = i["batch_picked"], qty = i["quantity_to_be_picked"] - int(i["quantity_picked"])))
            except:
                pass
            
    mi_name = generate_material_issue(m_issue)
    mr_name = generate_material_receipt(m_receipt)
    
    print("*"*150)
    return dict(mi_name = mi_name, mr_name = mr_name)

@frappe.whitelist()
def pick_status(item_list, so_name, company, stage_index, stage_list):
    names = None
    item_list = json.loads(item_list)
    stage_list = json.loads(stage_list)
    stage_index = json.loads(stage_index)
    next_stage = stage_list[stage_index + 1]
    settings = fetch_fulfillment_settings(company)
    sales_order = fetch_item_list(so_name)

    customer = get_customer(so_name)
    customer_type = fetch_customer_type(so_name)

    average_price = update_average_price(item_list, sales_order, customer_type, settings, customer)
    print("average price", average_price)

    if next_stage == "Invoiced":
        sales_doc = frappe.get_doc("Sales Order", so_name)
        sales_doc.pch_picking_status = next_stage
        update_sales_order_for_invoice(sales_doc, customer, customer_type, so_name, sales_order, item_list, settings)
        sales_doc.save()
        sales_doc.submit()

        names = stock_correction(customer, so_name, company, item_list, settings)

        outerJson_salesinvoice = generate_sales_invoice_json(customer, customer_type, so_name, sales_order, company, item_list, settings)
        sales_invoice_doc = frappe.new_doc("Sales Invoice")
        sales_invoice_doc.update(outerJson_salesinvoice)
        sales_invoice_doc.save()

        return dict(next_stage = next_stage, sales_invoice_name = sales_invoice_doc.name, names = names)

    else:
        sales_doc = frappe.get_doc("Sales Order", so_name)
        print(sales_doc.pch_picking_status)
        print("changing sales.pch_picking_status")
        sales_doc.pch_picking_status = next_stage
        sales_doc.save()
        print(sales_doc.pch_picking_status)
        update_sales_order(sales_doc, average_price, settings["free_warehouse"])
        return dict(next_stage = next_stage, average_price = average_price)