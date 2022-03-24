import json
import frappe
import datetime 

def fetch_order_booking_details(customer_type, fulfillment_settings) -> dict:
    # fetch data according to the fulfillment_settings
    # check the customer_type to search the according warehouse
    if "retail" in customer_type.lower():
        items = frappe.db.sql(
            f"""SELECT  t_warehouse, item_code, stock_uom, batch_no, qty
            FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{fulfillment_settings["retail_primary_warehouse"]}' or t_warehouse = '{fulfillment_settings["retail_bulk_warehouse"]}'""",
            as_dict=True
        )
    elif "hospital" in customer_type.lower():
        items = frappe.db.sql(
            f"""SELECT  t_warehouse, item_code, stock_uom, batch_no, qty
            FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{fulfillment_settings["hospital_warehouse"]}'""",
            as_dict=True
        )
    elif "institutional" in customer_type.lower():
        items = frappe.db.sql(
            f"""SELECT  t_warehouse, item_code, stock_uom, batch_no, qty
            FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{fulfillment_settings["institutional_warehouse"]}'""",
            as_dict=True
        )
    # add batch/price details for each batch
    if items:
        for i in range(len(items)):
            batch_details = frappe.db.sql(
                f"""SELECT manufacturing_date, expiry_date
                FROM `tabBatch`
                WHERE batch_id = '{items[i]["batch_no"]}'""",
                as_dict=True
            )
            price_details = frappe.db.sql(
                f"""SELECT price_list_rate
                FROM `tabItem Price`
                WHERE batch_no = '{items[i]["batch_no"]}'""",
                as_dict=True
            )
            if batch_details[0] and price_details[0]:
                items[i].update(batch_details[0])
                items[i].update(price_details[0])
            else: return []
        return items
    else: return []

def handle_fetched_order_booking_details(sum_data) -> dict:
    structure_data = dict()
    quantity_available = dict()
    # collect quantity available/etc.. 
    for data in sum_data:
        quantity_available[data["item_code"]] = quantity_available.get(data["item_code"], 0) + data["qty"]
        # restructuring fetched data by items
        if data["item_code"] not in structure_data:
            structure_data[data["item_code"]] = dict()
            structure_data[data["item_code"]]["item_code"] = data["item_code"]
            structure_data[data["item_code"]]["stock_uom"] = data["stock_uom"]
            structure_data[data["item_code"]]["batches"] = list()
            batch_data = dict()
            batch_data["t_warehouse"] = data["t_warehouse"]
            batch_data["batch_no"] = data["batch_no"]
            batch_data["expiry_date"] = data["expiry_date"]
            batch_data["manufacturing_date"] = data["manufacturing_date"]
            batch_data["qty"] = data["qty"]
            batch_data["price_list_rate"] = data["price_list_rate"]
            structure_data[data["item_code"]]["batches"].append(batch_data)
        else:
            batch_data = dict()
            batch_data["t_warehouse"] = data["t_warehouse"]
            batch_data["batch_no"] = data["batch_no"]
            batch_data["expiry_date"] = data["expiry_date"]
            batch_data["manufacturing_date"] = data["manufacturing_date"]
            batch_data["qty"] = data["qty"]
            batch_data["price_list_rate"] = data["price_list_rate"]
            structure_data[data["item_code"]]["batches"].append(batch_data)
    # add collected data to return (available quantity, etc ...)
    for key, val in structure_data.items():
        structure_data[key]["quantity_available"] = quantity_available[key]
        warehouse_quantity = dict()
        for batch in structure_data[key]["batches"]:
            warehouse_quantity[batch["t_warehouse"]] = warehouse_quantity.get(batch["t_warehouse"], 0) + batch["qty"]
        structure_data[key].update(warehouse_quantity)
        # also sort batches by expiry date (earliest to furthest)
        structure_data[key]["batches"] = sorted(structure_data[key]["batches"], key = lambda i: (i["expiry_date"]))
    return structure_data

def fetch_company_fulfillment_settings(company) -> dict:
    fs_name = frappe.db.sql(
        f"""SELECT name FROM `tabFulfillment Settings V1` WHERE company = '{company}'""",
        as_dict=True
    )
    if fs_name:
        settings = frappe.db.sql(
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )
    else:
        settings = []
    return settings

def handle_booked_quantity(items_data, quantity_booked, fulfillment_settings, customer_type) -> dict:
    expiry_limit = 115
    today = datetime.date.today()
    to_pickup = quantity_booked
    average_price_list = list()
    average_price_qty = list()
    # check if the order can be fulfilled in the primary warehouse itself
    # take into count the customer type
    if "retail" in customer_type.lower():
        print("instide retail")
        # see if its possible to pick from the retail first
        if items_data[fulfillment_settings["retail_primary_warehouse"]] > to_pickup:
            for batches in items_data["batches"]:
                if batches["t_warehouse"] != fulfillment_settings["retail_primary_warehouse"]: continue
                # verify expiry date
                expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
                date_delta = expiry_date - today
                if date_delta.days < expiry_limit: continue
                average_price_list.append(batches["price_list_rate"])
                if batches["qty"] > to_pickup:
                    # add price to calculate average price and update batch quantity
                    batches["qty"] -= to_pickup
                    average_price_qty.append(to_pickup)
                    to_pickup = 0
                    break
                else:
                    to_pickup -= batches["qty"]
                    average_price_qty.append(batches["qty"])
                    batches["qty"] = 0
        # if not pick try to pick from the bulk to fulfill the order
        else:
            to_pickup = to_pickup - items_data[fulfillment_settings["retail_primary_warehouse"]]
            for batches in items_data["batches"]:
                if batches["t_warehouse"] == fulfillment_settings["retail_primary_warehouse"]: 
                    batches["qty"] = 0
                else:
                    # verify expiry date
                    expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
                    date_delta = expiry_date - today
                    if date_delta.days < expiry_limit: continue
                    average_price_list.append(batches["price_list_rate"])
                    if batches["qty"] > to_pickup:
                        # add price to calculate average price and update batch quantity
                        batches["qty"] -= to_pickup
                        average_price_qty.append(to_pickup)
                        to_pickup = 0
                        break
                    else:
                        to_pickup -= batches["qty"]
                        average_price_qty.append(batches["qty"])
                        batches["qty"] = 0

    elif "hospital" in customer_type.lower():
        if items_data[fulfillment_settings["hospital_warehouse"]] > to_pickup:
            for batches in items_data["batches"]:
                if batches["t_warehouse"] != fulfillment_settings["hospital_warehouse"]: continue
                # verify expiry date
                expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
                date_delta = expiry_date - today
                if date_delta.days < expiry_limit: continue
                average_price_list.append(batches["price_list_rate"])
                if batches["qty"] > to_pickup:
                    # add price to calculate average price and update batch quantity
                    batches["qty"] -= to_pickup
                    average_price_qty.append(to_pickup)
                    to_pickup = 0
                    break
                else:
                    to_pickup -= batches["qty"]
                    average_price_qty.append(batches["qty"])
                    batches["qty"] = 0

    elif "institutional" in customer_type.lower():
        if items_data[fulfillment_settings["hospital_warehouse"]] > to_pickup:
            for batches in items_data["batches"]:
                if batches["t_warehouse"] != fulfillment_settings["hospital_warehouse"]: continue
                # verify expiry date
                expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
                date_delta = expiry_date - today
                if date_delta.days < expiry_limit: continue
                average_price_list.append(batches["price_list_rate"])
                if batches["qty"] > to_pickup:
                    # add price to calculate average price and update batch quantity
                    batches["qty"] -= to_pickup
                    average_price_qty.append(to_pickup)
                    to_pickup = 0
                    break
                else:
                    to_pickup -= batches["qty"]
                    average_price_qty.append(batches["qty"])
                    batches["qty"] = 0
    if to_pickup > 0:
        hunt = True
        hunt_quantity = to_pickup
    else:
        hunt = False
        hunt_quantity = 0
    if len(average_price_list) > 0:
        average_price = 0
        for i in range(len(average_price_list)):
            average_price += average_price_list[i]*average_price_qty[i]
        average_price /= quantity_booked
    else:
        average_price = 0
    amount = average_price * quantity_booked
    amount_after_gst = amount*1.2
    data = dict(
        average_price = average_price,
        amount = amount,
        amount_after_gst = amount_after_gst,
        updated_item_detail = items_data,
        hunt = hunt,
        hunt_quantity = hunt_quantity
    )
    return data

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

# api to fetch customer type
@frappe.whitelist()
def customer_type_container(customer):
    customer_type = fetch_customer_type(customer)
    return customer_type

# api to calculate batches to pickup and final amount
@frappe.whitelist()
def order_booked_container(items_data, quantity_booked, fulfillment_settings, customer_type):
    items_data = json.loads(items_data)
    fulfillment_settings = json.loads(fulfillment_settings)
    quantity_booked = json.loads(quantity_booked)
    data = handle_booked_quantity(items_data, quantity_booked, fulfillment_settings[0], customer_type)
    return data

# api to return fulfillment settings
@frappe.whitelist()
def fulfillment_settings_container(company):
    settings = fetch_company_fulfillment_settings(company)
    return settings

# api to return item details (warehouse, batches, prices, etc ...)
@frappe.whitelist()
def order_booking_container(fulfillment_settings, customer_type):
    fulfillment_settings = json.loads(fulfillment_settings)
    data = fetch_order_booking_details(customer_type, fulfillment_settings[0])
    if data == []: return []
    else: items = handle_fetched_order_booking_details(data)
    return items