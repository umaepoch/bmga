import json
import frappe

def validate_user_input(data):
    for i in data:
        if i.get('quantity') != i.get('retail') + i.get('bulk') + i.get('free') + i.get('hospital') + i.get('institutional'):
            return False
    return True

def fetch_fulfillment_settings():
    f = frappe.db.sql(
        """select retail_primary_warehouse as retail, retail_bulk_warehouse as bulk, hospital_warehouse as hospital, institutional_warehouse as institutional, free_warehouse as free
        from `tabFulfillment Settings Details V1`""",
        as_dict=1
    )

    if len(f) > 0:
        return f[0]

def validate_qty(qty):
    return qty > 0

def append_item_to_transfer(i, warehouse, settings, doc):
    if validate_qty(i.get(warehouse)):
        if warehouse != 'free':
            doc.append("items", {
                "s_warehouse": i.get('source_warehouse'),
                "t_warehouse": settings[warehouse],
                "item_code": i.get('item_code'),
                "qty": i.get(warehouse),
                "basic_rate": i.get('rate'),
                "batch_no": i.get('batch')
            })
        else:
            doc.append("items", {
                "s_warehouse": i.get('source_warehouse'),
                "t_warehouse": settings[warehouse],
                "item_code": i.get('item_code'),
                "qty": i.get(warehouse),
                "basic_rate": 0,
                "batch_no": i.get('batch')
            })

def generate_material_transfer(data, settings):
    if not validate_user_input(data):
        frappe.msgprint('Please make sure the distrabution is equal to the incoming QTY')
        return ""
    doc = frappe.new_doc("Stock Entry")
    doc.get
    doc.stock_entry_type = "Material Transfer"
    doc.items = []
    for i in data:
        append_item_to_transfer(i, 'retail', settings, doc)
        append_item_to_transfer(i, 'bulk', settings, doc)
        append_item_to_transfer(i, 'hospital', settings, doc)
        append_item_to_transfer(i, 'institutional', settings, doc)
        append_item_to_transfer(i, 'free', settings, doc)
    if len(doc.items) > 0:
        doc.save()
        frappe.msgprint("Stock Entry in Draft mode")
        return doc.name
    else: return ""


@frappe.whitelist()
def manage_stock_transfer(details):
    details = json.loads(details)
    settings = fetch_fulfillment_settings()
    generate_material_transfer(details, settings)
    return details