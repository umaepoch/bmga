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
    else:
        items = frappe.db.sql(
            f"""SELECT  t_warehouse, item_code, stock_uom, batch_no, qty
            FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{fulfillment_settings[f"{customer_type.lower()}_warehouse"]}'""",
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
            try:
                items[i].update(batch_details[0])
                items[i].update(price_details[0])
            except:
                items.pop(i)
        return items
    else: return []

def handle_fetched_order_booking_details(sum_data, sales_data, expiry_limit) -> dict:
    structure_data = dict()
    quantity_available = dict()
    today = datetime.date.today()
    # collect quantity available/etc.. 
    for data in sum_data:
        expiry_date = data["expiry_date"]
        date_delta = expiry_date - today
        if date_delta.days < expiry_limit: continue
        try:
            quantity_available[data["item_code"]] = quantity_available.get(data["item_code"], 0) + data["qty"] - sales_data[data["item_code"]][data["t_warehouse"]][data["batch_no"]]
        except:
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
            # difference between the sales order and stock
            try:
                batch_data["qty"] = data["qty"] - sales_data[data["item_code"]][data["t_warehouse"]][data["batch_no"]]
            except:
                batch_data["qty"] = data["qty"]
            batch_data["price_list_rate"] = data["price_list_rate"]
            structure_data[data["item_code"]]["batches"].append(batch_data)
        else:
            batch_data = dict()
            batch_data["t_warehouse"] = data["t_warehouse"]
            batch_data["batch_no"] = data["batch_no"]
            batch_data["expiry_date"] = data["expiry_date"]
            batch_data["manufacturing_date"] = data["manufacturing_date"]
            # difference between the sales order and stock
            try:
                batch_data["qty"] = data["qty"] - sales_data[data["item_code"]][data["t_warehouse"]][data["batch_no"]]
            except:
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
        f"""SELECT name, expiry_date_limit FROM `tabFulfillment Settings V1` WHERE company = '{company}'""",
        as_dict=True
    )
    if fs_name:
        settings = frappe.db.sql(
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )
        settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
    else:
        settings = []
    print("***********", settings)
    return settings

def handle_booked_quantity(items_data, quantity_booked, fulfillment_settings, customer_type, expiry_limit, gst) -> dict:
    today = datetime.date.today()
    to_pickup = quantity_booked
    average_price_list = list()
    average_price_qty = list()
    # collect all sales order details
    sales_sum_data = list()
    # check if the order can be fulfilled in the primary warehouse itself
    # take into count the customer type
    if "retail" in customer_type.lower():
        # see if its possible to pick from the retail first
        for batches in items_data["batches"]:
            # collect required data for sales order
            sales_data = dict()
            if batches["t_warehouse"] != fulfillment_settings["retail_primary_warehouse"]: continue
            # verify expiry date
            expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
            date_delta = expiry_date - today
            if date_delta.days < expiry_limit: continue
            average_price_list.append(batches["price_list_rate"])
            # sales order: add warehouse, price, qty, item
            sales_data["item_code"] = items_data["item_code"]
            sales_data["t_warehouse"] = batches["t_warehouse"]
            sales_data["batch_no"] = batches["batch_no"]
            sales_data["price"] = batches["price_list_rate"]
            if batches["qty"] > to_pickup:
                # add price to calculate average price and update batch quantity
                batches["qty"] -= to_pickup
                average_price_qty.append(to_pickup)
                sales_data["qty"] = to_pickup
                to_pickup = 0
                sales_sum_data.append(sales_data)
                break
            else:
                to_pickup -= batches["qty"]
                average_price_qty.append(batches["qty"])
                sales_data["qty"] = batches["qty"]
                batches["qty"] = 0
                sales_sum_data.append(sales_data)
        # if to pick > 0 try to pick from the bulk to fulfill the order
        if to_pickup > 0:
            for batches in items_data["batches"]:
                sales_data = dict()
                # add all sales order details
                if batches["t_warehouse"] == fulfillment_settings["retail_primary_warehouse"]: continue
                # verify expiry date
                expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
                date_delta = expiry_date - today
                if date_delta.days < expiry_limit: continue
                print("fetching bulk")
                average_price_list.append(batches["price_list_rate"])
                sales_data["item_code"] = items_data["item_code"]
                sales_data["t_warehouse"] = batches["t_warehouse"]
                sales_data["batch_no"] = batches["batch_no"]
                sales_data["price"] = batches["price_list_rate"]
                if batches["qty"] > to_pickup:
                    # add price to calculate average price and update batch quantity
                    batches["qty"] -= to_pickup
                    average_price_qty.append(to_pickup)
                    sales_data["qty"] = to_pickup
                    to_pickup = 0
                    sales_sum_data.append(sales_data)
                    break
                else:
                    to_pickup -= batches["qty"]
                    average_price_qty.append(batches["qty"])
                    sales_data["qty"] = batches["qty"]
                    batches["qty"] = 0
                    sales_sum_data.append(sales_data)
    # else fetch from the selected warehouse
    else:
        if items_data[fulfillment_settings[f"{customer_type.lower()}_warehouse"]] > to_pickup:
            for batches in items_data["batches"]:
                sales_data = dict()
                if batches["t_warehouse"] != fulfillment_settings[f"{customer_type.lower()}_warehouse"]: continue
                # verify expiry date
                expiry_date = datetime.date.fromisoformat(batches["expiry_date"])
                date_delta = expiry_date - today
                if date_delta.days < expiry_limit: continue
                average_price_list.append(batches["price_list_rate"])
                sales_data["item_code"] = items_data["item_code"]
                sales_data["t_warehouse"] = batches["t_warehouse"]
                sales_data["batch_no"] = batches["batch_no"]
                sales_data["price"] = batches["price_list_rate"]
                if batches["qty"] > to_pickup:
                    # add price to calculate average price and update batch quantity
                    batches["qty"] -= to_pickup
                    average_price_qty.append(to_pickup)
                    sales_data["qty"] = to_pickup
                    to_pickup = 0
                    sales_sum_data.append(sales_data)
                    break
                else:
                    to_pickup -= batches["qty"]
                    average_price_qty.append(batches["qty"])
                    sales_data["qty"] = batches["qty"]
                    batches["qty"] = 0
                    sales_sum_data.append(sales_data)

    if to_pickup > 0:
        hunt = True
        hunt_quantity = to_pickup
        hunt_price = items_data["batches"][-1]["price_list_rate"]
        average_price_list.append(hunt_price)
        average_price_qty.append(hunt_quantity)
    else:
        hunt = False
        hunt_quantity = 0
        hunt_price = 0
    if len(average_price_list) > 0:
        # calculate average price according to the items picked from specific batches
        average_price = 0
        for i in range(len(average_price_list)):
            average_price += average_price_list[i]*average_price_qty[i]
        average_price /= quantity_booked
    else:
        average_price = 0
    amount = average_price * quantity_booked
    amount_after_gst = amount*gst
    data = dict(
        average_price = average_price,
        amount = amount,
        amount_after_gst = amount_after_gst,
        updated_item_detail = items_data,
        hunt = hunt,
        hunt_quantity = hunt_quantity,
        hunt_price = hunt_price
    )
    sum_data = dict(
        new_data = data,
        sales_data = sales_sum_data
    )
    return sum_data

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

def fetch_sales_order_details():
    sales_data = frappe.db.sql(
        """SELECT item_code, qty, pch_batch_no, warehouse, delivered_qty
        FROM `tabSales Order Item` WHERE docstatus = '1'""",
        as_dict=True
    )
    structure_data = dict()
    for data in sales_data:
        if data["item_code"] not in structure_data:
            structure_data[data["item_code"]] = dict()
        if data["warehouse"] not in structure_data[data["item_code"]]:
            structure_data[data["item_code"]][data["warehouse"]] = dict() 
        structure_data[data["item_code"]][data["warehouse"]][data["pch_batch_no"]] = structure_data[data["item_code"]][data["warehouse"]].get(data["pch_batch_no"], 0) + data["qty"] - data["delivered_qty"]
    return structure_data

# api to fetch customer type
@frappe.whitelist()
def customer_type_container(customer):
    customer_type = fetch_customer_type(customer)
    return customer_type

# api to calculate batches to pickup and final amount
@frappe.whitelist()
def order_booked_container(items_data, quantity_booked, fulfillment_settings, customer_type):
    gst = 1.2
    
    items_data = json.loads(items_data)
    fulfillment_settings = json.loads(fulfillment_settings)
    quantity_booked = json.loads(quantity_booked)
    
    expiry_limit = fulfillment_settings[0]["expiry_date_limit"]

    data = handle_booked_quantity(items_data, quantity_booked, fulfillment_settings[0], customer_type, expiry_limit, gst)
    return data

# api to return item details (warehouse, batches, prices, etc ...)
@frappe.whitelist()
def order_booking_container(fulfillment_settings, customer_type):
    fulfillment_settings = json.loads(fulfillment_settings)
    data = fetch_order_booking_details(customer_type, fulfillment_settings[0])

    expiry_limit = fulfillment_settings[0]["expiry_date_limit"]

    sales_order_details = fetch_sales_order_details()
    if data == []: return []
    else: items = handle_fetched_order_booking_details(data, sales_order_details, expiry_limit)
    return items

# api to return fulfillment settings
@frappe.whitelist()
def fulfillment_settings_container(company):
    settings = fetch_company_fulfillment_settings(company)
    return settings

# api to place sales orders
@frappe.whitelist()
def add_sales_order(sales_data, qo_data, customer):
    sales_data = json.loads(sales_data)
    qo_data = json.loads(qo_data)
    delivery_date = datetime.datetime.today()
    delivery_date = delivery_date + datetime.timedelta(2)
    outerJson_so = {
        "doctype": "Sales Order",
        "naming_series": "SO-DL-",
        "customer": customer,
        "delivery_date": delivery_date,
        "pch_sales_order_purpose": "Delivery",
        "items": [],
    }
    for data in sales_data:
        if data["qty"] == 0: continue
        innerJson = {
            "doctype": "Sales Order Item",
            "item_code": data["item_code"],
            "qty": data["qty"],
            "rate": data["price"],
            "warehouse": data["t_warehouse"],
            "pch_batch_no": data["batch_no"],
        }
        outerJson_so["items"].append(innerJson)
    if len(outerJson_so["items"]) == 0:
        so_name = "NA"
    else:
        doc_so = frappe.new_doc("Sales Order")
        doc_so.update(outerJson_so)
        doc_so.save()
        doc_so.submit()
        so_name = doc_so.name
        
    if qo_data[0]:
        outerJson_qo = {
            "doctype": "Quotation",
            "naming_series": "QTN-DL-",
            "party_name": customer,
            "items": [],
        }
        for data in qo_data:
            if data["qty"] == 0: continue
            innerJson = {
                "doctype": "Quotation Item",
                "item_code": data["item_code"],
                "qty": data["qty"],
                "rate": data["price"],
            }
            outerJson_qo["items"].append(innerJson)
        print(outerJson_qo)
        if len(outerJson_qo["items"]) == 0:
            qo_name = "NA"
        else:
            doc_qo = frappe.new_doc("Quotation")
            doc_qo.update(outerJson_qo)
            doc_qo.save()
            qo_name = doc_qo.name
    else:
        qo_name = "NA"

    print(so_name, qo_name)
    return dict(so_name = so_name, qo_name = qo_name)