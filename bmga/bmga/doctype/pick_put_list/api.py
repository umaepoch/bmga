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

@frappe.whitelist()
def item_list_container(so_name):
    item_list = fetch_item_list(so_name)
    customer_type = fetch_customer_type(so_name)
    return dict(item_list = item_list, customer_type = customer_type)