import frappe

# BMGA customize button call for order process
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