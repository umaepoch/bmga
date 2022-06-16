// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pre_Stock Transfer', {
	refresh: function(frm) {
		frm.add_custom_button("Stock Transfer", function() {
			let items = frm.doc.items
			frappe.call({
				method: "bmga.bmga.doctype.pre_stock_transfer.api.manage_stock_transfer",
				args: {
					details: items
				}
			}).done(r => {
				console.log(r)
			})
		})
	}
});
