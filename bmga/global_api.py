import json
import frappe

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

# Purchase receipt
@frappe.whitelist()
def update_price_list_batch(items):
	items = json.loads(items)
	items = list(filter(lambda x: x.get('pch_fields') == 1, items))
	for i in items:
		if i.get('pch_mrp') == 0 or i.get('batch_no') == None: continue
		update_batch_price(i)
	return dict(items = items)