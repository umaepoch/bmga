# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import json
from datetime import date, timedelta

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

def get_t_warehouse(company):
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
	stock = fetch_stock_details(filters['warehouse'], filters['from_date'], filters['to_date'])

	return stock

def check_expiry(batch):
	t = date.today()
	e = frappe.db.get_value('Batch', {'name': batch}, 'expiry_date', as_dict=1)
	if e:
		if e.get('expiry_date') is None: return
		return e.get('expiry_date', t) < t
	return True

def get_expiry_date(batch):
	today = date.today() + timedelta(days=1)

	expiry_date = frappe.db.get_value('Batch', {'name': batch}, 'expiry_date')
	frappe.db.set_value('Batch', {'name': batch}, 'expiry_date', today)
	frappe.db.set_value('Batch', {'name': batch}, 'pch_expiry_date', expiry_date)

	return expiry_date

def update_expiry_date(batch, expiry_date):
	frappe.db.set_value('Batch', {'name': batch}, 'expiry_date', expiry_date)

@frappe.whitelist()
def generate_material_transfer(company, f_warehouse, data):
	data = json.loads(data)
	t_warehouse = get_t_warehouse(company)

	if t_warehouse:
		outerJson = {
			'doctype': 'Stock Entry',
			'naming_series': 'MT-BX-DL-',
			'stock_entry_type': 'Material Transfer',
			'from_warehouse': f_warehouse,
			'to_warehouse': t_warehouse,
			'items': []
		}

		expired_batch = []

		for x in data:
			if not x.get('qty', 0) > 0: continue
			if check_expiry(x.get('batch')):
				expiry_date = get_expiry_date(x.get('batch'))
				expired_batch.append({'batch': x.get('batch'), 'expiry_date': expiry_date})

			innerJson = {
				'doctype': 'Stock Entry Detail',
				'item_code': x.get('item_code'),
				'batch_no': x.get('batch'),
				'qty': x.get('qty')
			}

			outerJson['items'].append(innerJson)
		
		if len(outerJson['items']) == 0:
			frappe.throw('No valid items')
			return
	
		doc = frappe.new_doc('Stock Entry')
		doc.update(outerJson)
		doc.save()
		doc.submit()

		for x in expired_batch:
			update_expiry_date(x.get('batch'), x.get('expiry_date'))

		return dict(name = doc.name)
	frappe.throw('Target warehouse not found')
	return
