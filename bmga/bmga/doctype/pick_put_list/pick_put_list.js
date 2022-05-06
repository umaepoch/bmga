// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pick Put List', {
	setup: function(frm) {
		frm.set_query("batch_picked", "item_list", function(doc, cdt, cdn) {
			let item = locals[cdt][cdn].item;
			return {
				filters: [
					["item", "=", item]
				]
			};
		});
	},

	refresh: function(frm) {
		frm.add_custom_button("Pick Complete", function() {
			let item_list = frm.doc.item_list;
			console.log("item", item_list)
			let so_name = frm.doc.sales_order;
			let company = frm.doc.company;
			if(item_list) {
				frappe.call({
					method: "bmga.bmga.doctype.pick_put_list.api.material_transfer_container",
					args: {
						item_list: item_list,
						so_name: so_name,
						company: company
					}
				}).done((response) => {
					console.log(response.message)
					if(response.message.transfer_name.length > 0) {
						frappe.msgprint(`Material Transfer Placed: ${response.message.transfer_name}`)
					}
				})
			}
		})

		let so_name = frm.doc.sales_order;
		let company = frm.doc.company;
		let pick_stage = frm.doc.pick_list_stage;
		if(so_name && pick_stage == 'Ready for Picking') {
			frappe.call({
				method: "bmga.bmga.doctype.pick_put_list.api.item_list_container",
				args: {
					so_name: so_name,
					company: company,
				}
			}).done((response) => {
				console.log(response.message)
				frm.doc.item_list = []
				console.log("hai...",response.message.pick_put_list)
				$.each(response.message.pick_put_list, function(_i, e) {
					let entry = frm.add_child("item_list");
					entry.item = e.item_code;
					entry.uom = e.stock_uom;
					entry.batch = e.batch_no;
					entry.wbs_storage_location = e.wbs_storage_location;
					entry.warehouse = e.warehouse;
					entry.quantity_to_be_picked = e.qty;
				})
				refresh_field("item_list")
			})
		}
	}
});