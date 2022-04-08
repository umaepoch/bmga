import json
import frappe
import datetime

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
    stock_data = frappe.db.sql(
        f"""SELECT warehouse, batch_no, actual_qty FROM `tabStock Ledger Entry` WHERE item_code = '{item_code}' AND docstatus = 1 AND is_cancelled = 0""",
        as_dict=True
    )
    if customer_type == "Retail":
        filter_data = [data for data in stock_data if settings["retail_primary_warehouse"] == data["warehouse"] or settings["retail_bulk_warehouse"] == data["warehouse"]]
    elif customer_type == "Hospital":
        filter_data = [data for data in stock_data if settings["hospital_warehouse"] == data["warehouse"]]
    elif customer_type == "Institutional":
        filter_data = [data for data in stock_data if settings["institutional_warehouse"] == data["warehouse"]]
    return filter_data

def fetch_item_details(item_code, customer_type, settings):
    stock_detail = fetch_stock_details(item_code, customer_type, settings)
    return stock_detail

def handle_stock_details(stock_data):
    available_qty = sum(data["actual_qty"] for data in stock_data)
    return dict(available_qty = available_qty, stock_data = stock_data)

def fetch_average_price(stock_data, item_code):
    average_price_list = []
    average_qty_list = []
    average_price = 0
    stock_count = 0
    for data in stock_data:
        try:
            average_qty_list.append(data["actual_qty"])
        except:
            pass
        if data["batch_no"] is None:
            print("None")
            price_list = frappe.db.sql(
                f"""SELECT price_list_rate FROM `tabItem Price` WHERE batch_no IS NULL AND item_code = '{item_code}'""",
                as_dict=True
            )
            try:
                average_price += price_list[0]["price_list_rate"] * data["actual_qty"]
                average_price_list.append(price_list[0]["price_list_rate"])
                stock_count += data["actual_qty"]
            except:
                pass
        else:
            price_list = frappe.db.sql(
                f"""SELECT price_list_rate FROM `tabItem Price` WHERE batch_no = '{data["batch_no"]}' AND item_code = '{item_code}'""",
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

    print(sum(data["actual_qty"] for data in stock_data))
    print(stock_count)
    print(average_price)
    if stock_count > 0:
        return dict(average_price = average_price/stock_count, price_list = average_price_list, qty_list = average_qty_list)
    else:
        return dict(average_price = average_price, price_list = average_price_list, qty_list = average_qty_list)

def fetch_fulfillment_settings(company):
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
        settings = [None]
    return settings

@frappe.whitelist()
def fulfillment_settings_container(company):
    fulfillment_settings = fetch_fulfillment_settings(company)
    return fulfillment_settings[0]

@frappe.whitelist()
def customer_type_container(customer):
    customer_type = fetch_customer_type(customer)
    return customer_type

@frappe.whitelist()
def item_qty_container(company, item_code, customer_type):
    fulfillment_settings = fetch_fulfillment_settings(company)
    stock_detail = fetch_item_details(item_code, customer_type, fulfillment_settings[0])
    handled_stock = handle_stock_details(stock_detail)
    price_details = fetch_average_price(stock_detail, item_code)
    return dict(available_qty = handled_stock["available_qty"], average_price = price_details["average_price"], price_details = price_details, stock_data = handled_stock["stock_data"]) 

@frappe.whitelist()
def sales_order_container(customer, order_list, company, customer_type):
    fulfillment_settings = fetch_fulfillment_settings(company)
    if customer_type == "Retail":
        delivery_warehouse = fulfillment_settings[0]["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        delivery_warehouse = fulfillment_settings[0]["hospital_warehouse"]
    elif customer == "Institutional":
        delivery_warehouse = fulfillment_settings[0]["institutional_warehouse"]

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
    print(outerJson_qo)
    so_name = "NA"
    qo_name = "NA"
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

    return dict(so_name = so_name, qo_name = qo_name)