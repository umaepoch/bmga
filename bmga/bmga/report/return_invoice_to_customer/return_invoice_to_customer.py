# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from datetime import date
import json

def execute(filters=None):
	columns = get_columns()
	data = get_stock_details(filters)
	return columns, data

def get_columns():
	columns = [
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 150},
		{"label": _("Division"), "fieldname": "division", "fieldtype": "Link", "options": "Division", "width": 150},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 150},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch", "width": 150},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Int", "width": 150},
		{"label": _("PTS"), "fieldname": "pts", "fieldtype": "Currency", "width": 150},
		{"label": _("MRP"), "fieldname": "mrp", "fieldtype": "Currency", "width": 150},
	]

	return columns

def fetch_stock_details(warehouse, from_date, to_date):
    stock_data_batch = frappe.db.sql(
		f"""select `tabStock Ledger Entry`.item_code, batch_id as batch, brand, pch_division as division, `tabBatch`.stock_uom as uom, pch_mrp as mrp, pch_pts as pts, sum(`tabStock Ledger Entry`.actual_qty) as qty
		from `tabBatch`
			join `tabStock Ledger Entry` ignore index (item_code, warehouse)
				on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
			join `tabItem` on `tabItem`.name = `tabStock Ledger Entry`.item_code
		where warehouse = '{warehouse}'
			and `tabStock Ledger Entry`.is_cancelled = 0
		group by item_code, batch_id
		order by `tabBatch`.creation ASC""", as_dict=1)

    return stock_data_batch

def get_s_warehouse(company):
	warehouse = frappe.db.sql(
		f"""select fsd.breakage_and_expiry_warehouse as warehouse
		from `tabFulfillment Settings Details V1` as fsd
			join `tabFulfillment Settings V1` as fs on fs.name = fsd.parent
		where fs.company = '{company}'""", as_dict=1
	)

	if warehouse:
		if len(warehouse) > 0: return warehouse[0].get('warehouse')
		return
	return

def get_stock_details(filters):
	stock = []
	warehouse = get_s_warehouse(filters['company'])
	stock = fetch_stock_details(warehouse, filters['from_date'], filters['to_date'])

	return stock

@frappe.whitelist()
def create_return_invoice(company, data):
	t = date.today()
	data = json.loads(data)
	warehouse = get_s_warehouse(company)

	outerJson = {
		'doctype': 'Purchase Invoice',
		'naming_series': 'PI-RC-DL-',
		'posting_date': t,
		'update_stock': 1,
		'supplier': 'The Good Guy',
		'items': []
	}

	for x in data:
		if not x.get('qty', 0) > 0: continue

		innerJson = {
			'doctype': 'Purchase Invoice Item',
			'item_code': x.get('item_code'),
			'uom': x.get('uom'),
			'qty': x.get('qty'),
			'rate': x.get('mrp'),
			'warehouse': warehouse
		}

		outerJson['items'].append(innerJson)
	
	if len(outerJson['items']) > 0:
		doc = frappe.new_doc('Purchase Invoice')
		doc.update(outerJson)
		doc.save()

		return dict(name = doc.name)
	return