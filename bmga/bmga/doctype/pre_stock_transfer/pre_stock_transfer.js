// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pre_Stock Transfer', {
	setup: function(frm) {
		frm.set_query('wbs_storage_location', 'wbs_locations', function(doc, cdt, cdn) {
			return {
				filters: [
					['storage_location_can_store', '=', 'Any Items']
				]
			}
		});

		frm.revert_validation = function(frm) {
			if(frm.doc.validate_transfer) {
				frm.doc.validate_transfer = null;
				refresh_field('validate_transfer');
			}
		}
	},


	refresh: function(frm) {
		frm.toggle_display('wbs_locations', frm.doc.wbs_locations.length > 0);
		
		frm.add_custom_button('Validate Transfer', function() {
			let items = frm.doc.items;
			if(items) {
				frappe.call({
					method: "bmga.bmga.doctype.pre_stock_transfer.api.valided_stock_transfer",
					args: {
						details: items
					}
				}).done(r => {
					console.log(r);
					frm.toggle_display('wbs_locations', r.message.show);
					frm.doc.wbs_locations = []
					if(r.message.valid) {
						if(r.message.wbs_loc_list) {
							$.each(r.message.wbs_loc_list, function(_i, e) {
								let entry = frm.add_child('wbs_locations');
								entry.item_code = e.item_code;
								entry.warehouse = e.warehouse;
							});

							refresh_field('wbs_locations');
						}
						frm.doc.validate_transfer = "Done";
						refresh_field('validate_transfer');
					}
				});
			}
		});

		frm.add_custom_button('Stock Transfer', function() {
			if(frm.doc.validate_transfer == "Done") {
				console.log('we can do a transfer!');
				let name = frm.doc.purchase_receipt_no;
				let wbs_list = frm.doc.wbs_locations;

				if(name) {
					frappe.call({
						method: "bmga.bmga.doctype.pre_stock_transfer.api.generate_stock_transfer",
						args: {
							details: frm.doc.items,
							wbs_locations: wbs_list,
							purchase_no: name
						}
					}).done(r => {
						console.log(r)
						frm.doc.material_issue = r.message.names.issue_name;
						frm.doc.material_receipt = r.message.names.receipt_name;
						refresh_field('material_issue');
						refresh_field('material_receipt');
						frappe.msgprint('Stock Transfers Done');
						frm.save();
					})
				}
			} else {
				frappe.msgprint('First Validate the Transfer');
			}
		});
	}
});


frappe.ui.form.on('Pre_Stock Transfer Items', {
	retail: function(frm) {
		frm.revert_validation(frm);
	}
})