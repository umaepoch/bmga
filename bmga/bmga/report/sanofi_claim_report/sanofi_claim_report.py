# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

import datetime
from frappe import _
import frappe

def execute(filters=None):

	columns = get_columns()
	data = get_sales_invoice(filters)
	data = handle_claim(data)

	return columns, data

def handle_claim(data):
	hd = []
	to_add = {}

	for d in data:
		if d.get('invoice_rate') is not None and d.get('invoice_rate') > 0:
			to_add = d

			# to_add["division"] = "-"
			to_add["approval_status"] = ""
			to_add["reason"] = ""
			to_add["pharmacy_name"] = d["customer_name"]
			to_add["free_qty"] = 0
			to_add["landed_price"] = d["invoice_rate"] * d["qty"]/(d["qty"] + d["free_qty"])

			try:
				to_add["supply_rate"] = to_add["invoice_rate"]
			except:
				to_add["supply_rate"] = 0

			try:
				to_add["diff_amount"] = to_add["landed_price"] - to_add.get("pts", 0)
			except:
				to_add["diff_amount"] = 0

			to_add["supply_margin"] = (1 - to_add.get("pts", 0)/to_add("ptr", 1))*100

			try:
				to_add["supplier_margin"] = to_add["landed_price"] * (to_add["supply_margin"])/100
			except:
				to_add["supplier_margin"] = 0

			to_add["total_reimbursement"] = (-to_add['diff_amount'] + to_add['supplier_margin']) * (d["qty"] + d["free_qty"]) # + (to_add['supply_rate'] * (d["qty"] + d["free_qty"]))

			if to_add['total_reimbursement'] < 0:
				to_add['total_reimbursement'] = 0
				to_add["claim_amount"] = 0
			else:
				to_add["claim_amount"] = to_add['total_reimbursement'] / (d["qty"] + d["free_qty"])

			hd.append(to_add)
	
	return hd

def fetch_purchase_batch(i):
	p = frappe.db.sql(
		f"""select pri.parent, pri.pch_mrp, pri.pch_ptr, pri.pch_pts, pr.posting_date as purchase_date, pri.item_name
		from `tabPurchase Receipt Item` as pri
			join `tabPurchase Receipt` as pr on (pri.parent = pr.name)
		where pri.item_code = '{i["item_code"]}' and batch_no = '{i["batch_no"]}' and pr.posting_date <= '{i["invoice_date"]}' and pri.docstatus < 2
		order by pr.posting_date DESC""",
		as_dict=1
	)
	print(p)
	print("*"*100)
	if len(p) > 0:
		for x in p:
			try:
				if x["pch_mrp"] > 0 and x["pch_pts"] > 0:
					i["purchase_no"] = x["parent"]
					i["purchase_date"] = x["purchase_date"]
					i["mrp"] = x["pch_mrp"]
					i["pts"] = x["pch_pts"]
					i["ptr"] = x["pch_ptr"]
					break
			except:
				pass
	
	return i

def fetch_rate_contract_for_item(i):
	rc = frappe.db.sql(
		f"""select rci.selling_price_for_customer as rc_discount, rci.margin_supply_rate as supply_margin
		from `tabRate Contract Item` as rci
			join `tabRate Contract` as rc on (rc.name = rci.parent)
		where rc.customer_name = '{i["customer_name"]}' and rci.start_date <= '{i["invoice_date"]}' and rci.end_date >= '{i["invoice_date"]}' and item = '{i["item_code"]}' and rc.docstatus < 2
		group by rci.item
		order by rci.end_date ASC""",
		as_dict=1
	)
	if len(rc) > 0:
		for x in rc:
			try:
				if x.get('rc_discount') > 0 and x.get('supply_margin') > 0:
					i["rc_discount"] = x["rc_discount"]
					i["supply_margin"] = x["supply_margin"]
			except:
				pass
	return i

def fetch_purchase_detail(invoices):
	for i in invoices:
		if i.get('batch_no') is None or i.get('batch') == "": print("BATCHLESS")
		else: i = fetch_purchase_batch(i)
		i = fetch_rate_contract_for_item(i)

	return invoices

def get_sales_invoice(filters):
	brand = "Sanofi"
	to_date = datetime.date.fromisoformat(filters["to_date"])
	from_date = datetime.date.fromisoformat(filters["from_date"])

	invoices = frappe.db.sql(
		f"""select i.brand, i.pch_division as division, i.pch_item_code as pch_item_code, si.customer_name, sii.rate as invoice_rate, sii.item_name, sii.item_code, sum(sii.qty) as qty, sii.parent as invoice_no, si.due_date as invoice_date, sii.batch_no
		from `tabSales Invoice Item` as sii
			join `tabSales Invoice` as si on (si.name = sii.parent)
			join `tabItem` as i on (sii.item_name = i.item_name)
		where si.due_date <= '{to_date}' and si.due_date >= '{from_date}' and si.docstatus < 2 and i.brand = '{brand}'
		group by sii.parent, sii.item_name, sii.batch_no
		order by sii.parent DESC""", as_dict=1
	)
	
	invoices = fetch_purchase_detail(invoices)
	return invoices

def get_columns():
	"""return columns"""

	columns = [
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 100},
		{"label": _("Suppliers' Product Code"), "fieldname": "pch_item_code", "fieldtype": "Data", "width": 100},
		{"label": _("Quantity"), "fieldname": "qty", "fieldtype": "Int", "width": 100},
		{"label": _("Free Quantity"), "fieldname": "free_qty", "fieldtype": "Int", "width": 100},
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 100},
		{"label": _("Stockist Invoice Number"), "fieldname": "invoice_no", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"label": _("Stockist Invoice Date"), "fieldname": "invoice_date", "fieldtype": "Date", "width": 100},
		{"label": _("SPDL Purchase Receipt No."), "fieldname": "purchase_no", "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},
		{"label": _("Purchase Date"), "fieldname": "purchase_date", "fieldtype": "Date", "width": 100},
		{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 100},
		{"label": _("Division"), "fieldname": "division", "fieldtype": "Link", "options": "Division", "width": 100},
		{"label": _("Supplied to Institution/Hospital"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
		{"label": _("Pharmacy Name"), "fieldname": "pharmacy_name", "fieldtype": "Data", "width": 150},
		{"label": _("MRP"), "fieldname": "mrp", "fieldtype": "Currency", "width": 100},
		{"label": _("Rate Contract Disount on MRP"), "fieldname": "rc_discount", "fieldtype": "Currency", "width": 100},
		{"label": _("PTS"), "fieldname": "pts", "fieldtype": "Currency", "width": 100},
		{"label": _("PTR"), "fieldname": "ptr", "fieldtype": "Currency", "width": 100},
		{"label": _("Sold Rate"), "fieldname": "supply_rate", "fieldtype": "Currency", "width": 100},
		{"label": _("INST Landed NDP (Per Unit)"), "fieldname": "landed_price", "fieldtype": "Currency", "width": 100},
		{"label": _("Sold - NDP"), "fieldname": "diff_amount", "fieldtype": "Currency", "width": 100},
		{"label": _("Margin on Supply Rate"), "fieldname": "supply_margin", "fieldtype": "Percent", "width": 100},
		{"label": _("Margin VAL on Supply Rate"), "fieldname": "supplier_margin", "fieldtype": "Currency", "width": 100},
		{"label": _("Claim Amount Per Unit"), "fieldname": "claim_amount", "fieldtype": "Currency", "width": 100},
		{"label": _("Total Reimbursement"), "fieldname": "total_reimbursement", "fieldtype": "Currency", "width": 150},
		{"label": _("Approval Status"), "fieldname": "approval_status", "fieldtype": "Data", "width": 100},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 100},
	]

	return columns