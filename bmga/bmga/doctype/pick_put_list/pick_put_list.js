// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pick Put List', {
	onload: function(frm) {
		let so_name = frm.doc.sales_order
		if(so_name) {
			frappe.call({
				method: "bmga.bmga.doctype.pick_put_list.api.item_list_container",
				args: {
					so_name: so_name,
				}
			}).done((response) => {
				console.log(response.message)
			})
		}
	},

	refresh: function(frm) {

	}
});
