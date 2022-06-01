// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Rate Contract', {
	setup: function(frm) {
		frm.check_duplicate = function(frm) {
			var item_code_list = frm.doc.item.map(function(d) {
				return d.item;
			})
			for(let i=0; i<item_code_list.length; i++) {
				if(item_code_list.indexOf(item_code_list[i]) != i) {
					return true;
				}
			}
			return false;
		}
	}
});

frappe.ui.form.on('Rate Contract Item', {
	item: function(frm, cdt, cdn) {
		let item = locals[cdt][cdn].item
		console.log(item)
		if(item) {
			if(frm.check_duplicate(frm)) {
				frappe.msgprint("Can not re-select chosen item!");
				frappe.model.set_value(cdt, cdn, "item", null);
				frappe.model.set_value(cdt, cdn, "stock_uom", null);
				frappe.model.set_value(cdt, cdn, "batched_item", null);
				frappe.model.set_value(cdt, cdn, "selling_price_for_customer", null);
				frappe.model.set_value(cdt, cdn, "discount_percentage_for_customer_from_mrp", null);
				frappe.model.set_value(cdt, cdn, "mrp", null);
				frappe.model.set_value(cdt, cdn, "pts", null);
				frappe.model.set_value(cdt, cdn, "start_date", null);
				frappe.model.set_value(cdt, cdn, "end_date", null);
				refresh_field('rate_contract_item')
			}
		}
	}
});