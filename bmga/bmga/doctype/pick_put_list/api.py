import frappe

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
    return settings[0]

def fetch_stock_details(customer_type, settings):
    if customer_type == "Retail":
        stock_details = frappe.db.sql(
            f"""SELECT item_code, t_warehouse, qty, batch_no FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{settings["retail_primary_warehouse"]}' OR t_warehouse = '{settings["retail_bulk_warehouse"]}'"""
        )
    elif customer_type == "Hospital":
        stock_details = frappe.db.sql(
            f"""SELECT item_code, t_warehouse, qty, batch_no FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{settings["hospital_warehouse"]}'"""
        )
    elif customer_type == "Institutional":
        stock_details = frappe.db.sql(
            f"""SELECT item_code, t_warehouse, qty, batch_no FROM `tabStock Entry Detail`
            WHERE t_warehouse = '{settings["institutional_warehouse"]}'"""
        )
    return stock_details

@frappe.whitelist()
def item_list_container(so_name, company):
    sales_list = fetch_item_list(so_name)
    customer_type = fetch_customer_type(so_name)
    fulfillment_settings = fetch_fulfillment_settings(company)
    stock_data = fetch_stock_details(customer_type, fulfillment_settings)
    return dict(item_list = sales_list, customer_type = customer_type, settings = fulfillment_settings, stock_data = stock_data)