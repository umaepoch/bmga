# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

from frappe import _
import frappe


def execute(filters=None):

	data = fetch_bmga_purchase_order(filters)
	columns = get_columns()
	return columns, data


def get_columns():
	columns = [
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 120},
		{"label": _("BMGA PO Number"), "fieldname": "bmga_po_number", "fieldtype": "Link", "options": "BMGA Purchase Order", "width": 120},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 120},
		{"label": _("Division"), "fieldname": "division", "fieldtype": "Link", "options": "Division", "width": 120},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 120},
		{"label": _("BMGA PO Qty"), "fieldname": "qty_ordered", "fieldtype": "Int", "width": 120},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Int", "width": 120},
		{"label": _("Purchase Promo"), "fieldname": "purchase_promo", "fieldtype": "Data", "width": 120},
		{"label": _("Sales Promo"), "fieldname": "sales_promo", "fieldtype": "Data", "width": 120}
	]

	return columns


def fetch_item_detail(item_code):
	detail = frappe.db.get_value("Item", {'item_code': item_code}, ['brand', 'pch_division as division'], as_dict=1)
	print(detail)
	return detail


def fetch_purchase_order_details(order):
	data = []

	po = frappe.get_doc("BMGA Purchase Order", order.get('name'))
	for child in po.get_all_children():
		if child.doctype != "BMGA Purchase Items": continue

		to_add = {
			'bmga_po_number': order.get('name'),
			'supplier': order.get('supplier'),
			'received_qty': child.qty_ordered - child.pending_qty
		}

		item_detail = fetch_item_detail(child.as_dict().get('item_code'))
		to_add.update(item_detail)
		print(child.as_dict())
		to_add.update(child.as_dict())
		data.append(to_add)
	
	return data
	
	


def fetch_bmga_purchase_order(filters):
	data = []

	orders = frappe.db.get_list("BMGA Purchase Order", filters=filters, fields=['name', 'supplier', ''])
	for o in orders:
		details = fetch_purchase_order_details(o)
		data.extend(details)
	
	return data