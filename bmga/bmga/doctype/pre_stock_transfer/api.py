import json
import frappe

def fetch_fulfillment_settings():
    f = frappe.db.sql(
        """select retail_primary_warehouse as retail, retail_bulk_warehouse as bulk, hospital_warehouse as hospital, institutional_warehouse as institutional, free_warehouse as free
        from `tabFulfillment Settings Details V1`""",
        as_dict=1
    )

    if len(f) > 0:
        return f[0]

@frappe.whitelist()
def manage_stock_transfer(details):
    details = json.loads(details)
    settings = fetch_fulfillment_settings()
    print(settings)
    return details