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
    
    print("primary", settings["retail_primary_warehouse"])
    print("secondary", settings["retail_bulk_warehouse"])
    
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
                group by item_code, warehouse""",
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
                group by item_code, warehouse""",
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
                group by item_code, warehouse""",
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
                group by item_code, warehouse""",
                as_dict=True
            )

    for data in stock_data_batchless:
        if data["actual_qty"] == None: continue
        stock_data_batch.append(data)
    
    print("STOCK FETCH DATA")
    for data in stock_data_batch:
        print(data)

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
            f"""select item_code, `tabWBS Storage Location`.name_of_attribute_id, `tabWBS Storage Location`.rarb_warehouse
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
                f"""select item_code, `tabWBS Storage Location`.name_of_attribute_id, `tabWBS Storage Location`.rarb_warehouse 
                from `tabStock Entry Detail`
                    join `tabWBS Storage Location`
                        on (target_warehouse_storage_location = `tabWBS Storage Location`.name)
                where item_code = '{item}' and target_warehouse_storage_location is not null and `tabStock Entry Detail`.docstatus = 1""",
                as_dict=True
            )
            if len(wbs_location_anyitem) > 0:
                wbs_location_list.append(wbs_location_anyitem[0])
            

    wbs_structured = {}
    for data in wbs_location_list:
        # print(data)
        if data["rarb_warehouse"] not in wbs_structured:
            wbs_structured[data["rarb_warehouse"]] = {}
        wbs_structured[data["rarb_warehouse"]][data["item_code"]] = data["name_of_attribute_id"]
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
                pick_up["wbs_storage_location"] = wbs_details[stock["warehouse"]][sales["item_code"]]
            except:
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

def generate_json_transfer(payload, destination):
    to_pick = 0
    picked_up = 0
    outerJson = {
        "doctype": "Stock Entry",
        "naming_series": "MAT-DL-",
        "stock_entry_type": "Material Transfer",
        "from_warehouse": payload[0]["warehouse"],
        "to_warehouse": destination,
        "items": []
    }
    for data in payload:
        to_pick += data["quantity_to_be_picked"]
        
        if data.get("quantity_picked") is None:
            qty = data["quantity_to_be_picked"]
            picked_up += data["quantity_to_be_picked"]
            batch = data["batch"]
        elif data["quantity_picked"] > 0:
            qty = data["quantity_picked"]
            picked_up += data["quantity_picked"]
            if data.get("batch_picked") is None:
                batch = data["batch"]
            else:
                batch = data["batch_picked"]
        else: continue
        innerJson = {
            "doctype": "Stock Entry Detail",
            "item_code": data["item"],
            "qty": qty,
            "batch_no": batch
        }
        outerJson["items"].append(innerJson)

    print("to pick", to_pick)
    print("picked up", picked_up)
    
    return dict(outerJson = outerJson, complete_pick = to_pick - picked_up == 0)

@frappe.whitelist()
def material_transfer_container(item_list, so_name, company):
    item_list = json.loads(item_list)
    customer_type = fetch_customer_type(so_name)
    settings = fetch_fulfillment_settings(company)
    # print(settings)
    name = []
    bulk_json = {}
    hospital_json = {}
    retail_json = {}

    if customer_type == "Retail":
        retail_transfer = list(filter(lambda x: x["warehouse"] == settings["retail_primary_warehouse"], item_list))
        bulk_transfer = list(filter(lambda x: x["warehouse"] == settings["retail_bulk_warehouse"], item_list))
        if len(retail_transfer) > 0:
            retail_json = generate_json_transfer(retail_transfer, settings["qc_and_dispatch"])
        else:
            retail_json = {}
        if len(bulk_transfer) > 0:
            bulk_json = generate_json_transfer(bulk_transfer, settings["qc_and_dispatch"])
            print(bulk_json["outerJson"])
            if len(bulk_json["outerJson"]["items"]) > 0:
                doc_bulk = frappe.new_doc("Stock Entry")
                doc_bulk.update(bulk_json["outerJson"])
                doc_bulk.save()
                name.append(doc_bulk.name)

    elif customer_type == "Hospital":
        hospital_transfer = list(filter(lambda x: x["warehouse"] == settings["hospital_warehouse"], item_list))
        if len(hospital_transfer) > 0:
            hospital_json = generate_json_transfer(hospital_transfer, settings["qc_and_dispatch"])
            if len(hospital_json["outerJson"]["items"]) > 0:
                doc_hospital = frappe.new_doc("Stock Entry")
                doc_hospital.update(hospital_json["outerJson"])
                doc_hospital.save()
                name.append(doc_hospital.name)
    
    elif customer_type == "Institutional":
        institutional_transfer = list(filter(lambda x: x["warehouse"] == settings["institutional_warehouse"], item_list))
        if len(institutional_transfer) > 0:
            institutional_json = generate_json_transfer(institutional_transfer, settings["qc_and_dispatch"])
            if len(hospital_json["outerJson"]["items"]) > 0:
                doc_institutional = frappe.new_doc("Stock Entry")
                doc_institutional.update(institutional_json["outerJson"])
                doc_institutional.save()
                name.append(doc_institutional.name)

    return dict(retail = retail_json, bulk = bulk_json, transfer_name = name)