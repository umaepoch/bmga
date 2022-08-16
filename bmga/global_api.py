import json
import frappe
import datetime

# Print Format
@frappe.whitelist()
def check_promo(item_code, invoice):
	today = datetime.date.today()
	qty = frappe.db.sql(
		f"""select sum(qty) as total from `tabSales Invoice Item` where name = '{invoice[0].name}'""", as_dict=1
	)
	print('qty', qty)

	# promo_1 = frappe.db.sql(
	# 	f"""select p1.discount_percentage as discount
	# 	from `tabPromo Type 1` as p1
	# 		join `tabSales Promos` as p on (p.name = p1.parent)
	# 	where p1.bought_item = '{item_code}' and p1.quantity_bought <= '{qty[0]['total']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
	# 	order by p1.quantity_bought DESC""", as_dict=1
	# )

	# if len(promo_1) > 0: return promo_1[0]['discount']
	# else:
	promo_5 = frappe.db.sql(
		f"""select p5.discount
		from `tabPromo Type 5` as p5
			join `tabSales Promos` as p on (p.name = p5.parent)
		where p5.bought_item = '{item_code}' and p5.for_every_quantity_that_is_bought <= '{qty[0]['total']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
		order by p5.for_every_quantity_that_is_bought DESC""", as_dict=1
	)
	print('type 5', promo_5)
	if len(promo_5) > 0: return promo_5[0]['discount']
	return 0

@frappe.whitelist()
def get_dl_no(customer):
	dl = frappe.db.get_list('Customer', filters={'name': customer}, fields=['drug_license'])
	try:
		s = ", ".join(x['drug_license'] for x in dl)
	except:
		s = ""
	return s

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
	print("*"*100)
	print("updating batchless item")
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
	print("-"*100)
	print("update price")
	items = json.loads(items)
	items = list(filter(lambda x: x.get('pch_fields') == 1, items))
	for i in items:
		if i.get('pch_mrp') == 0 or i.get('pch_ptr') == 0 or i.get('pch_pts') == 0: continue
		if i.get('batch_no') == "" or i.get('batch_no') is None: update_batchless_price(i)
		else: update_batch_price(i)
	return dict(items = items)

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
		innerJson = {
			"doctype": "Pre_Stock Transfer Items",
			"item_code": i.get('item_code'),
			"item_name": i.get('item_name'),
			"batch": i.get('batch_no'),
			"quantity": i.get('qty'),
			"rate": i.get('rate'),
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

@frappe.whitelist()
def check_customer_state_test():
    l = []

    address = frappe.db.get_list('Address')
    for a in address:
        doc = frappe.get_doc('Address', a['name']).as_dict()
        l.append(doc)
    
    return l