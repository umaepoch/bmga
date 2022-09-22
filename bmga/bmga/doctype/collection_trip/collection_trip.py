# Copyright (c) 2022, Karthik Raman and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json
import datetime

class CollectionTrip(Document):
	pass


def sales_invoice_details(name):
	company = frappe.db.get_value('Sales Invoice', name, 'company', as_dict=1)
	return company.get('company', '')

def get_cash_account(company):
	a = frappe.db.get_value('Company', company, 'default_cash_account', as_dict=1)
	return a.get('default_cash_account', '')

def get_bank_account(company, user):
	a = frappe.db.get_value(user, company, 'default_bank_account', as_dict=1)
	return a.get('default_bank_account', '')

def fetch_company_address(company):
    address_list = frappe.db.get_list('Address', 'name')
    for x in address_list:
        a = frappe.get_doc('Address', x.get('name')).as_dict()
        if a.get('links'):
            if len(a['links']) > 0:
                for l in a['links']:
                    if l.get('link_name') == company: return dict(valid = True, name = x.get('name'))
    frappe.throw("Error No address for given Company")
    return dict(valid = False)

def generate_outerJson(company, x, paid_type):
	today = datetime.date.today()

	if paid_type == 'Cash':
		account = get_cash_account(company)
	else:
		account = get_bank_account(company, 'Company')

	customer_account = get_bank_account(x.get('customer'), 'Customer')
	company_account = get_bank_account(company, 'Company')
	company_address = fetch_company_address(company)

	outerJson = {
		'doctype': 'Payment Entry',
		'company': company,
		'payment_type': 'Receive',
		'mode_of_payment': paid_type,
		'posting_date': today,
		'party_type': 'Customer',
		'party': x.get('customer'),
		'bank_account': company_account,
		'party_bank_account': customer_account,
		'paid_amount': x.get('cash_amount'),
		'received_amount': x.get('cash_amount'),
		'paid_to': account,
		'references': [
			{
				'doctype': 'Payment Entry Reference',
				'reference_doctype': 'Sales Invoice',
				'reference_name': x.get('invoice_no')
			}
		],
		'company_address': company_address.get('name', '')
	}

	if paid_type != 'Cash':
		outerJson['reference_no'] = x.get('reference_no')
		outerJson['reference_date'] = x.get('reference_date')

	print('*'*150, outerJson)

	doc = frappe.new_doc('Payment Entry')
	doc.update(outerJson)
	doc.save()

	return doc.name


@frappe.whitelist()
def make_payment(details):
	details = json.loads(details)

	payment_entries = []

	for x in details:
		company = sales_invoice_details(x.get('invoice_no'))

		if x.get('cash_amount', 0) > 0:
			payment_entries.append(generate_outerJson(company, x, 'Cash'))
		if x.get('cheque_amount', 0) > 0:
			payment_entries.append(generate_outerJson(company, x, 'Cheque'))
		if x.get('wire_amount', 0) > 0:
			payment_entries.append(generate_outerJson(company, x, 'Wire Transfer'))

	return payment_entries