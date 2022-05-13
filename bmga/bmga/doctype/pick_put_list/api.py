import json
import frappe
import datetime

def fetch_item_list(so_name):
    item_list = frappe.db.sql(
        f"""SELECT item_code, qty, warehouse FROM `tabSales Order Item` WHERE parent = '{so_name}'""",
        as_dict=True
    )
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
    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"], settings["free_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"], settings["free_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"], settings["free_warehouse"]]

    if len(items) > 1:
        if len(warehouse) > 1:
            pick_put_list_stock = frappe.db.sql(
                f"""select ppli.item as item_code, ppli.batch, ppli.batch_picked, ppli.warehouse, ppli.quantity_to_be_picked, ppli.quantity_picked, ppli.warehouse
                from `tabPick Put List Items` as ppli
                    join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
                where ppli.item in {tuple(items)} and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse in {tuple(warehouse)}""",
                as_dict=1
            )
        else:
            pick_put_list_stock = frappe.db.sql(
                f"""select ppli.item as item_code, ppli.batch, ppli.batch_picked, ppli.warehouse, ppli.quantity_to_be_picked, ppli.quantity_picked, ppli.warehouse
                from `tabPick Put List Items` as ppli
                    join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
                where ppli.item in {tuple(items)} and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse in '{warehouse[0]}'""",
                as_dict=1
            )
    else:
        if len(warehouse) > 1:
            pick_put_list_stock = frappe.db.sql(
                f"""select ppli.item as item_code, ppli.batch, ppli.batch_picked, ppli.warehouse, ppli.quantity_to_be_picked, ppli.quantity_picked, ppli.warehouse
                from `tabPick Put List Items` as ppli
                    join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
                where ppli.item = '{items[0]}' and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse in {tuple(warehouse)}""",
                as_dict=1
            )
        else:
            pick_put_list_stock = frappe.db.sql(
                f"""select ppli.item as item_code, ppli.batch, ppli.batch_picked, ppli.warehouse, ppli.quantity_to_be_picked, ppli.quantity_picked, ppli.warehouse
                from `tabPick Put List Items` as ppli
                    join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
                where ppli.item = '{items[0]}' and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse in '{warehouse[0]}'""",
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
    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]
    
    if settings["retail_primary_warehouse"] >= settings["retail_bulk_warehouse"] :
        warehouse_order = "DESC"
    else:
        warehouse_order = "ASC"

    if len(items) > 1:
        if len(warehouse) > 1:
            stock_data_batch = frappe.db.sql(f"""
                select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code in {tuple(items)} AND warehouse in {tuple(warehouse)}
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by warehouse {warehouse_order}, expiry_date ASC
            """, as_dict=True)

            stock_data_batchless = frappe.db.sql(
                f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
                where item_code in {tuple(items)} and warehouse in {tuple(warehouse)} and (batch_no is null or batch_no = '')
                group by item_code, warehouse
                order by warehouse {warehouse_order}""",
                as_dict=True
            )
        else:
            stock_data_batch = frappe.db.sql(f"""
                select batch_id, `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code in {tuple(items)} and warehouse = '{warehouse[0]}'
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by warehouse {warehouse_order}, expiry_date ASC
            """, as_dict=True)

            stock_data_batchless = frappe.db.sql(
                f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as acutal_qty from `tabStock Ledger Entry`
                where item_code in {tuple(items)} and warehouse = '{warehouse[0]}' and (batch_no is null or batch_no = '')
                group by item_code, warehouse
                order by warehouse {warehouse_order}""",
                as_dict=True
            )
    else:
        if len(warehouse) > 1:
            stock_data_batch = frappe.db.sql(f"""
                select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code = '{items[0]}' AND warehouse in {tuple(warehouse)}
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by warehouse {warehouse_order}, expiry_date ASC
            """, as_dict=True)

            stock_data_batchless = frappe.db.sql(
                f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
                where item_code = '{items[0]}' and warehouse in {tuple(warehouse)} and (batch_no is null or batch_no = '')
                group by item_code, warehouse
                order by warehouse {warehouse_order}""",
                as_dict=True
            )
        else:
            stock_data_batch = frappe.db.sql(f"""
                select batch_id, `tabBatch`.stock_uom, item as item_code, expiry_date,`tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
                from `tabBatch`
                    join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                        on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
                where `tabStock Ledger Entry`.item_code = '{items[0]}' and warehouse = '{warehouse[0]}'
                    and `tabStock Ledger Entry`.is_cancelled = 0
                group by batch_id, warehouse
                order by warehouse {warehouse_order}, expiry_date ASC
            """, as_dict=True)

            stock_data_batchless = frappe.db.sql(
                f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as acutal_qty from `tabStock Ledger Entry`
                where item_code = '{items[0]}' and warehouse = '{warehouse[0]}' and (batch_no is null or batch_no = '')
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
    # print(wbs_structured)
    return wbs_structured

def sales_order_handle(sales_list, stock_data, free_data, wbs_details, expiry_date, free_warehouse):
    today = datetime.date.today()
    pick_up_list = []
    free_pick_list = []

    for sales in sales_list:
        to_pickup = sales["qty"]
        print(sales)
        if sales["warehouse"] != free_warehouse:
            print("Normal Data")
            if stock_data.get(sales["item_code"]) is None: continue
            for stock in stock_data[sales["item_code"]]:
                if stock["actual_qty"] == 0: continue
                try:
                    date_delta = stock["expiry_date"] - today
                    if date_delta.days < expiry_date: continue
                except:
                    pass
                pick_up = {}
                pick_up["item_code"] = sales["item_code"]
                pick_up["stock_uom"] = stock["stock_uom"]
                pick_up["warehouse"] = stock["warehouse"]
                try:
                    pick_up["wbs_storage_location_id"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location_id"]
                    pick_up["wbs_storage_location"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location"]
                except:
                    pick_up["wbs_storage_location_id"] = ''
                    pick_up["wbs_storage_location"] = ''
                if stock["actual_qty"] >= to_pickup:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = to_pickup
                    to_pickup = 0
                else:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = stock["actual_qty"]
                    to_pickup -= stock["actual_qty"]
                pick_up_list.append(pick_up)
                if to_pickup == 0: break
        else:
            print("Free Data")
            if free_data.get(sales["item_code"]) is None: continue
            for stock in free_data[sales["item_code"]]:
                if stock["actual_qty"] == 0: continue
                try:
                    date_delta = stock["expiry_date"] - today
                    if date_delta.days < expiry_date: continue
                except:
                    pass
                pick_up = {}
                pick_up["item_code"] = sales["item_code"]
                pick_up["stock_uom"] = stock["stock_uom"]
                pick_up["warehouse"] = stock["warehouse"]
                try:
                    pick_up["wbs_storage_location_id"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location_id"]
                    pick_up["wbs_storage_location"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location"]
                except:
                    pick_up["wbs_storage_location_id"] = ''
                    pick_up["wbs_storage_location"] = ''
                if stock["actual_qty"] >= to_pickup:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = to_pickup
                    to_pickup = 0
                else:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = stock["actual_qty"]
                    to_pickup -= stock["actual_qty"]
                free_pick_list.append(pick_up)
                if to_pickup == 0: break
        
    return pick_up_list + free_pick_list

def fetch_free_stock_detail(free_list, free_warehouse):
    print("Free warehouse fetch!")
    items = [data["item_code"] for data in free_list]
    if len(items) > 1:
        stock_data_batch = frappe.db.sql(f"""
            select batch_id, `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code in {tuple(items)} and warehouse = '{free_warehouse}'
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC
        """, as_dict=True)

        stock_data_batchless = frappe.db.sql(
            f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
            where item_code in {tuple(items)} and warehouse = '{free_warehouse}' and (batch_no is null or batch_no = '')
            group by item_code, warehouse
            """,
            as_dict=True
        )
    else:
        stock_data_batch = frappe.db.sql(f"""
            select batch_id, `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code = '{items[0]}' and warehouse = '{free_warehouse}'
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC
        """, as_dict=True)

        stock_data_batchless = frappe.db.sql(
            f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
            where item_code = '{items[0]}' and warehouse = '{free_warehouse}' and (batch_no is null or batch_no = '')
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
    wbs_details = fetch_wbs_location(customer_type, order_list, fulfillment_settings)
    pick_put_list = sales_order_handle(sales_list, handled_data, handled_free, wbs_details, fulfillment_settings["expiry_date_limit"], fulfillment_settings["free_warehouse"])
    return dict(free_data = free_data, order_list = order_list, free_list = free_list, p_stock = p_stock, wbs_details = wbs_details, pick_put_list = pick_put_list ,sales_list = sales_list, customer_type = customer_type, settings = fulfillment_settings, stock_data = handled_data)

def get_customer(so_name):
    customer = frappe.db.sql(
        f"""select customer from `tabSales Order` where name = '{so_name}'""", as_dict=1
    )
    return customer[0].customer

def fetch_batch_price(batch, item_code):
    price = frappe.db.sql(
        f"""select price_list_rate as price from `tabItem Price` where batch_no = '{batch}' and  item_code = '{item_code}'""",
        as_dict=1
    )
    if len(price) > 0 and price[0].get("price") is not None: return price[0]
    else: return fetch_batchless_price(item_code)

def fetch_batchless_price(item_code):
    price = frappe.db.sql(
        f"""select price_list_rate as price from `tabItem Price` where (batch_no is null or batch_no = '') and item_code = '{item_code}'""",
        as_dict=1
    )
    if len(price) > 0 and price[0].get("price") is not None: return price[0]
    else: return dict(price = 0)

def fetch_storage_location_from_id(id):
    location = frappe.db.sql(
        f"""select name from `tabWBS Storage Location` where name_of_attribute_id = '{id}'""",
        as_dict=1
    )

    return location[0]

def get_so_detail(so_name, item_code, warehouse):
    so_detail = frappe.db.sql(
        f"""select name from `tabSales Order Item` where parent = '{so_name}' and item_code = '{item_code}' and warehouse = '{warehouse}'""",
        as_dict=1
    )
    
    return so_detail[0]

def generate_sales_invoice_json(customer, customer_type, so_name, company, item_list, settings):
    due_date = datetime.datetime.today()
    # due_date = due_date + datetime.timedelta(2)
    if customer_type == "Retail":
        warehouse = settings["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        warehouse = settings["hospital_warehouse"]
    elif customer_type == "Institutional":
        warehouse = settings["institutional_warehouse"]

    outerJson = {
        "doctype": "Sales Invoice",
        "naming_series": "SINV-DL-",
        "company": company,
        "customer": customer,
        "due_date": due_date,
        "update_stock": 1,
        "items": []
    }

    for item in item_list:
        if item.get("quantity_picked") is None:
            if item.get("quantity_to_be_picked") is None: continue
            qty = item.get("quantity_to_be_picked")
        else:
            try:
                qty = int(item["quantity_picked"])
            except:
                qty = item.get("quantity_to_be_picked") 
        if item.get("batch_picked") is None:
            batch = item.get("batch")
        else:
            batch = item.get("batch_picked")
        
        if batch:
            rate = fetch_batch_price(batch, item["item"])
        else:
            rate = fetch_batchless_price(item["item"])
        
        print("qty", qty)
        print(type(qty))
        print("batch", batch)
        print("rate", rate)
        print("*"*100)
        if qty <= 0: continue
        if item["warehouse"] != settings["free_warehouse"]:
            so_detail = get_so_detail(so_name, item["item"], warehouse)
            print("so_detail", so_detail)
            if item.get("wbs_storage_location") != '':
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
                    "so_detail": so_detail["name"],
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
                    "so_detail": so_detail["name"],
                    "delivered_qty": qty,
                }
        else:
            so_detail = get_so_detail(so_name, item["item"], settings["free_warehouse"])
            print("so_detail", so_detail)

            innerJson = {
                    "doctype": "Sales Invoice Item",
                    "item_code": item["item"],
                    "qty": qty,
                    "price_list_rate": 0,
                    "rate": 0,
                    "warehouse": item["warehouse"],
                    "batch_no": batch,
                    "sales_order": so_name,
                    "so_detail": so_detail["name"],
                    "delivered_qty": qty,
                }
        outerJson["items"].append(innerJson)
    for d in outerJson["items"]:
        print(d["item_code"], d["sales_order"], d["warehouse"], d["so_detail"], d["delivered_qty"], d["rate"])
    return outerJson

def update_average_price(item_list, free_warehouse):
    new_average_price = {}

    for item in item_list:
        if item["warehouse"] == free_warehouse: continue
        if item.get("quantity_picked") is None:
            qty = item.get("quantity_to_be_picked")
        else:
            try:
                qty = int(item["quantity_picked"])
            except:
                qty = item.get("quantity_to_be_picked") 
        if item.get("batch_picked") is None:
            batch = item.get("batch")
        else:
            batch = item.get("batch_picked")
        
        if batch:
            rate = fetch_batch_price(batch, item["item"])
        else:
            rate = fetch_batchless_price(item["item"])
        
        if item["item"] not in new_average_price:
            new_average_price[item["item"]] = {
                "qty": [qty],
                "price": [rate["price"]]
            }
        else:
            if qty is None: continue  
            new_average_price[item["item"]]["qty"].append(qty)
            new_average_price[item["item"]]["price"].append(rate["price"])
        new_average_price[item["item"]]["average"] = sum([new_average_price[item["item"]]["qty"][i] * new_average_price[item["item"]]["price"][i] for i in range(len(new_average_price[item["item"]]["qty"]))]) / sum(new_average_price[item["item"]]["qty"])
    
    return new_average_price 

def update_sales_order_json(sales_doc, average_price, free_warehouse):
    for child in sales_doc.get_all_children():
            if child.doctype != "Sales Order Item": continue
            sales_item_doc = frappe.get_doc(child.doctype, child.name)
            if sales_item_doc.warehouse == free_warehouse:
                sales_item_doc.rate = 0
            else:
                sales_item_doc.rate = average_price[sales_item_doc.item_code]["average"]
            sales_item_doc.save()

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

        doc = frappe.new_doc("Stock Entry")
        doc.update(outerJson)
        doc.save()

        return doc.name
    
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

        doc = frappe.new_doc("Stock Entry")
        doc.update(outerJson)
        doc.save()

        return doc.name

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
            if ppli_balance:
                stock_balance["actual_qty"] -= ppli_balance["pick_quantity"] 
            print(stock_balance)
            try:
                i["quantity_picked"] = int(i["quantity_picked"])
            except:
                continue
            if stock_balance["actual_qty"] < i["quantity_picked"]:
                print("material receip needed for", i)
                m_receipt.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = '', qty = i["quantity_picked"] - stock_balance["actual_qty"]))
            try:
                if int(i["quantity_picked"]) < i["quantity_to_be_picked"]:
                    print("material issue needed for:", i)
                    m_issue.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = '', qty = i["quantity_to_be_picked"] - i["quantity_picked"]))
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
                    m_issue.append(dict(item_code = i["item"], warehouse = i["warehouse"], wbs_storage_location = i["wbs_storage_location"], batch = i["batch_picked"], qty = i["quantity_to_be_picked"] - i["quantity_picked"]))
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

    average_price = update_average_price(item_list, settings["free_warehouse"])
    print(average_price)

    customer = get_customer(so_name)
    customer_type = fetch_customer_type(so_name)

    if next_stage == "QC Area":
        names = stock_correction(customer, so_name, company, item_list, settings)

    if next_stage == "Invoiced":
        sales_doc = frappe.get_doc("Sales Order", so_name)
        sales_doc.pch_picking_status = next_stage
        sales_doc.save()
        sales_doc.reload()
        sales_doc.submit()

        outerJson_salesinvoice = generate_sales_invoice_json(customer, customer_type, so_name, company, item_list, settings)
        sales_invoice_doc = frappe.new_doc("Sales Invoice")
        sales_invoice_doc.update(outerJson_salesinvoice)
        sales_invoice_doc.save()
        return dict(next_stage = next_stage, sales_invoice_name = sales_invoice_doc.name)

    else:
        sales_doc = frappe.get_doc("Sales Order", so_name)
        print(sales_doc.pch_picking_status)
        print("changing sales.pch_picking_status")
        sales_doc.pch_picking_status = next_stage
        sales_doc.save()
        print(sales_doc.pch_picking_status)
        update_sales_order_json(sales_doc, average_price, settings["free_warehouse"])
        sales_doc.reload()
        sales_doc.save()

    return dict(next_stage = next_stage, average_price = average_price, names = names)