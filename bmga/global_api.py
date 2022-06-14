from dataclasses import asdict
import json
import frappe
import datetime

# Custom button sales order -> process order
@frappe.whitelist()
def pick_put_list_container(so_name):
	outerJson_ppl = {
		"doctype": "Pick Put List",
		"type": "Pick",
		"pick_list_stage": "Ready for Picking",
		"sales_order": so_name
	}

	doc_ppl = frappe.new_doc("Pick Put List")
	doc_ppl.update(outerJson_ppl)
	doc_ppl.save()

	return dict(so_name = so_name, ppl_name = doc_ppl.name)

def update_batch_price(item):
	print(item.get('batch_no'))

	batch_name = frappe.db.sql(
		f"""select name from `tabBatch` where batch_id = '{item.get('batch_no')}' and item = '{item.get('item_code')}'""",
		as_dict=1
	)
	if len(batch_name) > 0:
		batch = frappe.get_doc('Batch', batch_name[0])
		print(batch.as_dict())
		batch.pch_mrp = item.get('pch_mrp')
		batch.pch_ptr = item.get('pch_ptr')
		batch.pch_pts = item.get('pch_pts')

		batch.save()

def create_batchless_price(item):
	p = frappe.db.sql(
		f"""select name from `tabRate Contract` where selling_price = 1""", as_dict=1
	)

	if len(p) > 0:
		selling = frappe.get_doc("Rate Contract", p[0]["name"])
		selling.append("item", {
			"item": item.get('item_code'),
			"batched_item": "No",
			"selling_price_for_customer": item.get('pch_ptr'),
			"mrp": item.get('pch_mrp'),
			"pts": item.get('pch_pts'),
			"discount_percentage_for_customer_from_mrp": 0
		})
		
		selling.save()

def update_batchless_price(item):
	rc = frappe.db.sql(
		f"""select rci.name, rci.parent
		from `tabRate Contract Item` as rci
			join `tabRate Contract` as rc on (rci.parent = rc.name)
		where rci.item = '{item.get('item_code')}' and rc.selling_price = 1""",
		as_dict=1
	)

	if len(rc) > 0:
		print("updating batchless price")
		selling = frappe.get_doc("Rate Contract Item", rc[0]["name"])
		selling.selling_price_for_customer = item.get('pch_ptr')
		selling.mrp = item.get('pch_mrp')
		selling.pts = item.get('pch_pts')

		selling.save()
	else :
		create_batchless_price(item)

# Purchase receipt
@frappe.whitelist()
def update_price_list_batch(items):
	items = json.loads(items)
	items = list(filter(lambda x: x.get('pch_fields') == 1, items))
	for i in items:
		if i.get('pch_mrp') == 0 or i.get('pch_ptr') == 0 or i.get('pch_pts') == 0: continue
		if i.get('batch_no') == "": update_batchless_price(i)
		else: update_batch_price(i)
	return dict(items = items)

def get_batched_latest_rate(i):
	p = frappe.db.get_value("Batch", {"name": i.get('batch_no')}, "pch_ptr", as_dict=1)
	if p:
		return p.get('pch_ptr')
	else:
		return 0

def get_batchless_latest_rate(i):
	n = frappe.db.get_value("Rate Contract", {"selling_price": 1}, "name", as_dict=1)
	if n:
		p = frappe.db.get_value("Rate Contract Item", {"parent": n.get('name'), "item": i.get('item_code')}, "selling_price_for_customer", as_dict=1)
		if p: return p.get('selling_price_for_customer')
		else: return 0
	else: return 0

def get_rate(i):
	if i.get('pch_fields') == 1 and i.get('pch_mrp') > 0 and i.get('pch_ptr') > 0 and i.get('pch_pts') > 0:
		return i.get('pch_ptr')
	elif i.get('batch_no') != '':
		return get_batched_latest_rate(i)
	else:
		return get_batchless_latest_rate(i)

def create_prestock_transfer(items, name):
	today = datetime.date.today()
	doc_name = ""
	outerJson = {
		"doctype": "Pre_Stock Transfer",
		"date": today,
		"purchase_receipt_no": name,
		"items": []
	}

	for i in items:
		rate = get_rate(i)
		innerJson = {
			"doctype": "Pre_Stock Transfer Items",
			"item_code": i.get('item_code'),
			"item_name": i.get('item_name'),
			"batch": i.get('batch_no'),
			"quantity": i.get('qty'),
			"rate": rate,
			"source_warehouse": i.get('warehouse')
		}
		outerJson['items'].append(innerJson)
	
	if len(outerJson['items']) > 0:
		doc = frappe.new_doc("Pre_Stock Transfer")
		doc.update(outerJson)
		doc.save()
		doc_name = doc.name
	
	return dict(name = doc_name)

@frappe.whitelist()
def generate_prestock_transfer(items, name):
	items = json.loads(items)
	n = create_prestock_transfer(items, name)
	return n