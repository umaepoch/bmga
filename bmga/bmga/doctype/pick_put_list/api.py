import json
import frappe
import datetime

def fetch_item_list(so_name):
    item_list = frappe.db.sql(
        f"""SELECT item_code, qty FROM `tabSales Order Item` WHERE parent = '{so_name}'""",
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
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse, qc_and_dispatch
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )
        settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
    else:
        settings = [None]
    return settings[0]

def fetch_stock_details(customer_type, sales_list, settings):
    items = [data["item_code"] for data in sales_list]
    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]
    
    """ print("primary", settings["retail_primary_warehouse"])
    print("secondary", settings["retail_bulk_warehouse"]) """
    
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
        if data["actual_qty"] == None: continue
        stock_data_batch.append(data)
    
    """ print("STOCK FETCH DATA")
    for data in stock_data_batch:
        print(data) """

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

def sales_order_handle(sales_list, stock_data, wbs_details, expiry_date):
    today = datetime.date.today()
    pick_up_list = []

    """ for key, val in stock_data.items():
        print()
        for batch in stock_data[key]:
            print(batch) """

    for sales in sales_list:
        to_pickup = sales["qty"]
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
            
    return pick_up_list


@frappe.whitelist()
def item_list_container(so_name, company):
    sales_list = fetch_item_list(so_name)
    customer_type = fetch_customer_type(so_name)
    fulfillment_settings = fetch_fulfillment_settings(company)
    stock_data = fetch_stock_details(customer_type, sales_list, fulfillment_settings)
    handled_data = handle_stock_data(stock_data)
    wbs_details = fetch_wbs_location(customer_type, sales_list, fulfillment_settings)
    pick_put_list = sales_order_handle(sales_list, handled_data, wbs_details, fulfillment_settings["expiry_date_limit"])
    return dict(wbs_details = wbs_details, pick_put_list = pick_put_list ,sales_list = sales_list, customer_type = customer_type, settings = fulfillment_settings, stock_data = handled_data)

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
    if price: return price[0]
    else: return dict(price = 0)

def fetch_batchless_price(item_code):
    price = frappe.db.sql(
        f"""select price_list_rate as price from `tabItem Price` where (batch_no is null or batch_no = '') and item_code = '{item_code}'""",
        as_dict=1
    )
    if price: return price[0]
    else: return dict(price = 0)

def fetch_storage_location_from_id(id):
    location = frappe.db.sql(
        f"""select name from `tabWBS Storage Location` where name_of_attribute_id = '{id}'""",
        as_dict=1
    )

    return location[0]

def get_so_detail(so_name, item_code):
    so_detail = frappe.db.sql(
        f"""select name from `tabSales Order Item` where parent = '{so_name}' and item_code = '{item_code}'""",
        as_dict=1
    )
    
    return so_detail[0]

def generate_sales_invoice_json(customer, so_name, item_list):
    due_date = datetime.datetime.today()
    # due_date = due_date + datetime.timedelta(2)

    outerJson = {
        "doctype": "Sales Invoice",
        "naming_series": "SINV-DL-",
        "customer": customer,
        "due_date": due_date,
        "update_stock": 1,
        "items": []
    }

    for item in item_list:
        so_detail = get_so_detail(so_name, item["item"])
        print("so_detail", so_detail)

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
        
        print("qty", qty)
        print(type(qty))
        print("batch", batch)
        print("rate", rate)
        print(item)

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
                "batch_no": item["batch"],
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
                "batch_no": item["batch"],
                "sales_order": so_name,
                "so_detail": so_detail["name"],
                "delivered_qty": qty,
            }
        outerJson["items"].append(innerJson)
    print(outerJson)
    return outerJson

@frappe.whitelist()
def pick_status(item_list, so_name, company, stage_index, stage_list):
    item_list = json.loads(item_list)
    stage_list = json.loads(stage_list)
    stage_index = json.loads(stage_index)
    next_stage = stage_list[stage_index + 1]
    if next_stage == "Invoiced":
        sales_doc = frappe.get_doc("Sales Order", so_name)
        sales_doc.pch_picking_status = next_stage
        sales_doc.save()
        sales_doc.submit()
        sales_doc.reload()

        customer = get_customer(so_name)
        outerJson = generate_sales_invoice_json(customer, so_name, item_list)
        sales_invoice_doc = frappe.new_doc("Sales Invoice")
        sales_invoice_doc.update(outerJson)
        sales_invoice_doc.save()
        return dict(next_stage = next_stage, sales_invoice_name = sales_invoice_doc.name)

    else:
        sales_doc = frappe.get_doc("Sales Order", so_name)
        sales_doc.pch_picking_status = next_stage
        sales_doc.save()
        sales_doc.reload()

    return dict(next_stage = next_stage)