# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document
from frappe.utils.data import today
from frappe.utils import add_months

class BreakageAndExpiry(Document):
	pass


def fetch_last_3_months_invoices(customer):
	date = add_months(today(), -3)
	sales_amount = frappe.db.sql(
		f"""select coalesce(sum(rounded_total), 0) as total
		from `tabSales Invoice`
		where customer = '{customer}' and docstatus < 2 and rounded_total > 0 and is_return != 1 and due_date >= '{date}'""", as_dict=1
	)
	
	sales_return = frappe.db.sql(
		f"""select coalesce(sum(rounded_total), 0) as total
		from `tabSales Invoice`
		where customer = '{customer}' and docstatus < 2 and and is_return = 1 and due_date >= '{date}'""", as_dict=1
	)

	sales_return = sales_return[0]
	sales_amount = sales_amount[0]

	return sales_amount.get('total', 0), sales_return.get('total', 0)

def fetch_beakage_and_expiry_warehouse(company):
	warehouse = frappe.db.sql(
		f"""select fsd.breakage_and_expiry_warehouse as warehouse
		from `tabFulfillment Settings Details V1` as fsd
			join `tabFulfillment Settings V1` as fs on (fs.name = fsd.parent)
		where fs.company = '{company}'""", as_dict=1
	)

	return warehouse[0].get('warehouse', '')

def fetch_gst_detail(company):
    d = frappe.db.sql(
        f"""select fsd.gst_out_state, fsd.gst_in_state
        from `tabFulfillment Settings Details V1` as fsd
            join `tabFulfillment Settings V1` as fs on (fs.name = fsd.parent)
        where fs.company = '{company}'""",
        as_dict=1
    )

    if len(d) > 0: return d[0]
    else: frappe.throw('ADD GST detail to Fulfillement Settings!!!')

def check_customer_state(customer, company):
    company_code = -1
    customer_code = -2

    address = frappe.db.get_list('Address', fields=['name'])
    for a in address:
        doc = frappe.get_doc('Address', a['name']).as_dict()
        try:
            if doc.address_type == 'Shipping': continue
            if doc.get('links')[0].get('link_name') == customer: customer_code = doc.gst_state_number
            if doc.get('links')[0].get('link_name') == company: company_code = doc.gst_state_number
        except:
            continue

    print(customer_code, company_code)
    
    return dict(valid = company_code == customer_code, customer_code = customer_code, company_code = company_code)

def fetch_tax_detail(name):
    d = frappe.db.sql(
        f"""select charge_type, account_head, rate, description
        from `tabSales Taxes and Charges` where parent = '{name}'
        order by modified DESC""",
        as_dict=1
    )

    h = {}
    list(map(lambda x: h.update({x['account_head']: x['rate']}), d))

    if len(d) > 0:
        return dict(detail = d, tax = h)
    else:
        frappe.throw(f'Sales Taxes and Charges detail not found for {name}')

def fetch_company_abbr(company):
    a = frappe.db.get_value('Company', {'name': company}, 'abbr', as_dict=1)
    return a.get('abbr')

@frappe.whitelist()
def generate_sales_invoice(company, customer, items):
	items = json.loads(items)
	warehouse = fetch_beakage_and_expiry_warehouse(company)
	t = today()
	
	abbr = fetch_company_abbr(company)
	gst_detail = fetch_gst_detail(company)
	customer_in_state = check_customer_state(customer, company)
	if customer_in_state.get('valid'):
		tax_detail = fetch_tax_detail(gst_detail['gst_in_state'])
	else:
		tax_detail = fetch_tax_detail(gst_detail['gst_out_state'])
	
	outerJson = {
		"doctype": "Sales Invoice",
		"naming_series": "SINV-DL-CN-",
		"is_return": 1,
		"company": company,
        "customer": customer,
        "due_date": t,
		"update_stock": 1,
		"items": [],
		"taxes": []
	}

	for x in items:
		print('*'*150, x)
		print(x.get('pch_mrp'))
		print(type(x.get('pch_mrp')))
		innerJson = {
            "doctype": "Sales Invoice Item",
            "item_code": x.get("item"),
            "qty": x.get("qty")*(-1),
            "rate": x.get("pch_mrp"),
            "warehouse": warehouse,
            "batch_no": x.get('batch'),
        }

		outerJson['items'].append(innerJson)
	
	innerJson_tax_list = []
	if customer_in_state.get('valid'):
		for x in tax_detail['detail']:
			if x.get('account_head') == f'Output Tax SGST - {abbr}':
				print('SGST', x.get('description'))
				innerJson_tax_list.append({
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": x["charge_type"],
                    "account_head": x["account_head"],
                    "description": x["description"],
                })
			else:
				innerJson_tax_list.append({
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": x["charge_type"],
                    "account_head": x["account_head"],
                    "description": x["description"],
                })
	else:
		innerJson_tax_list.append({
            "doctype": "Sales Taxes and Charges",
            "charge_type": tax_detail['detail'][0]["charge_type"],
            "account_head": tax_detail['detail'][0]["account_head"],
            "description": tax_detail['detail'][0]["description"],
        })
	
	outerJson['taxes'].extend(innerJson_tax_list)

	print(outerJson)

	doc = frappe.new_doc('Sales Invoice')
	doc.update(outerJson)
	doc.save()

	return dict(name = doc.name)	

@frappe.whitelist()
def get_permissible_expiry_limit(customer):
	r = frappe.db.get_value('Customer', {'name': customer}, 'pch_replacement', as_dict=1)

	if not r: r = {}

	invoice_amount, invoice_return = fetch_last_3_months_invoices(customer)
	print(r.get('pch_replacement', 0), invoice_amount, invoice_return)

	return dict(limit = r.get('pch_replacement', 0)/100 * (invoice_amount - invoice_return), remainder = r.get('pch_replacement', 0)/100 * (invoice_amount - invoice_return) - invoice_return, invoice_amount = invoice_amount, invoice_return = invoice_return, replacement = r.get('pch_replacement', 0))

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