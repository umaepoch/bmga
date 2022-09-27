# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.data import today
from frappe.utils import add_months

class BreakageAndExpiry(Document):
	pass


def fetch_last_3_months_invoices(customer):
	date = add_months(today(), -3)
	sales_amount = frappe.db.sql(
		f"""select coalesce(sum(outstanding_amount), 0) as total
		from `tabSales Invoice`
		where customer = '{customer}' and docstatus < 2 and outstanding_amount > 0 and is_return != 1""", as_dict=1
	)
	
	sales_return = frappe.db.sql(
		f"""select coalesce(sum(outstanding_amount), 0) as total
		from `tabSales Invoice`
		where customer = '{customer}' and docstatus < 2 and outstanding_amount > 0 and is_return = 1""", as_dict=1
	)

	sales_return = sales_return[0]
	sales_amount = sales_amount[0]

	return sales_amount.get('total', 0), sales_return.get('total', 0)
	

@frappe.whitelist()
def get_permissible_expiry_limit(customer):
	r = frappe.db.get_value('Customer', {'name': customer}, 'pch_replacement', as_dict=1)

	if not r: r = {}

	invoice_amount, invoice_return = fetch_last_3_months_invoices(customer)
	print(r.get('pch_replacement', 0), invoice_amount, invoice_return)

	return dict(limit = r.get('pch_replacement', 0)/100 * (invoice_amount - invoice_return), remainder = invoice_return)

@frappe.whitelist()
def get_item_details(item_code):
	d = frappe.db.sql(
		f"""select brand, pch_division, stock_uom, has_batch_no, item_name
		from `tabItem`
		where name = '{item_code}'""", as_dict=1
	)

	p = None

	if d[0]['has_batch_no'] == 0:
		p = frappe.db.sql(
			f"""select ri.mrp, ri.pts, ri.selling_price_for_customer as ptr
			from `tabRate Contract Item` as ri
				join `tabRate Contract` as r on (ri.parent = r.name)
			where ri.item = '{item_code}' and r.selling_price = 1""", as_dict=1
		)

		p = p[0]

	return dict(details = d[0], price = p)

@frappe.whitelist()
def get_batch_details(batch):
	p = frappe.db.sql(
		f"""select pch_mrp as mrp, pch_ptr as ptr, pch_pts as pts, expiry_date
		from `tabBatch` 
		where name = '{batch}'""", as_dict=1
	)

	return dict(price = p[0])