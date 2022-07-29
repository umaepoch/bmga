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

		frm.add_child_pos = function(data, table_name) {
			var child = frm.add_child(table_name);
			child.item = data.item;
			child.uom = data.stock_uom;
			child.wbs_storage_location = data.wbs_storage_location;
			child.warehouse = data.warehouse;
			child.correction = 1;
			child.promo_type = data.promo_type;
			child.so_detail = data.so_detail;
		};
	},

	refresh: function(frm) {
		if(frm.doc.type == 'Pick' && frm.doc.sales_order) {
			let stage_list = ["Ready for Picking", "QC Area", "Packing Area", "Dispatch Area", "Invoiced"]
			let button_name = {"Ready for Picking": "Pick Complete", "QC Area": "QC Complete", "Packing Area": "Packing Complete", "Dispatch Area": "Invoice Picklist"}
			if(frm.doc.pick_list_stage != "Invoiced") {
				frm.add_custom_button(button_name[frm.doc.pick_list_stage], function() {
					let item_list = frm.doc.item_list;
					let so_name = frm.doc.sales_order;
					let company = frm.doc.company;
					let pick_stage = frm.doc.pick_list_stage;

					if(item_list && pick_stage) {
						frappe.call({
							method: "bmga.bmga.doctype.pick_put_list.api.pick_status",
							args: {
								item_list: item_list,
								so_name: so_name,
								company: company,
								stage_index: stage_list.indexOf(pick_stage),
								stage_list: stage_list
							}
						}).done((response) => {
							console.log(response);
							if(response.message.names) {
								let names = response.message.names

								if(names.mr_name) {
									frm.set_value('material_receipt', names.mr_name);
								}

								if(names.mi_name) {
									frm.set_value('material_issue', names.mi_name);
								}
							}

							frm.set_value('pick_list_stage', response.message.next_stage);
							refresh_field('pick_list_stage');

							if(response.message.next_stage == "Invoiced") {
								frm.set_value('sales_invoice', response.message.sales_invoice_name);
								refresh_field('sales_invoice');
							}

							frm.save();
						})
					} else {
						frappe.msgprint("No items or Already Picked!")
					}
				})
			}

			let pick_stage = frm.doc.pick_list_stage;

			if (pick_stage == "Ready for Picking") {
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
						$.each(response.message.pick_put_list, function(_i, e) {
							let entry = frm.add_child("item_list");
							entry.item = e.item_code;
							entry.uom = e.stock_uom;
							entry.batch = e.batch_no;
							entry.wbs_storage_location = e.wbs_storage_location_id;
							entry.warehouse = e.warehouse;
							entry.quantity_to_be_picked = e.qty;
							entry.promo_type = e.promo_type;
							entry.so_detail = e.so_detail;
						})
						refresh_field("item_list")
					})
				}
			}
		}
	}
});


frappe.ui.form.on('Pick Put List Items', {
	correction: function(frm, cdt, cdn) {
		let doc = locals[cdt][cdn];
		console.log(doc);

		if(doc.correction) {
			frm.add_child_pos(doc, "item_list");
			cur_frm.refresh_field("item_list");
		}
	},
});