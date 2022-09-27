// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Breakage And Expiry', {
	setup(frm) {
		frm.set_query("batch", "items", function(doc, cdt, cdn) {
			let item = locals[cdt][cdn].item;
			return {
				filters: [
					["item", "=", item]
				]
			};
		});
	},

	validate(frm) {
		let items = frm.doc.items;
		let total = 0

		if(items.length > 0) {
			$.each(items, function(_i, v) {
				total = total + v.pch_mrp_total;
			})

			frm.set_value('total', total);
		}
	},

	customer(frm) {
		if(frm.doc.customer) {
			frappe.call({
				method: "bmga.bmga.doctype.breakage_and_expiry.breakage_and_expiry.get_permissible_expiry_limit",
				args: {
					customer: frm.doc.customer
				}
			}).done(r => {			
				console.log(r.message);
				frm.set_value('expiry_permissible_limit', r.message.limit);
				frm.set_value('remainder_of_permissible_limit', r.message.remainder);

				cur_frm.refresh_fields();
			})
		}
	},
});

frappe.ui.form.on('Breakage And Expiry Item', {
	item(frm, cdt, cdn) {
		let doc = locals[cdt][cdn];

		if(doc.item) {
			frappe.call({
				method: "bmga.bmga.doctype.breakage_and_expiry.breakage_and_expiry.get_item_details",
				args: {
					item_code: doc.item
				}
			}).done(r => {
				console.log(r.message);
				frappe.model.set_value(cdt, cdn, "brand", r.message.details.brand);
				frappe.model.set_value(cdt, cdn, "uom", r.message.details.stock_uom);
				frappe.model.set_value(cdt, cdn, "item_name", r.message.details.item_name);
				frappe.model.set_value(cdt, cdn, "batch", null);
				frappe.model.set_value(cdt, cdn, "pch_pts", 0);
				frappe.model.set_value(cdt, cdn, "pch_ptr", 0);
				frappe.model.set_value(cdt, cdn, "pch_mrp", 0);
				frappe.model.set_value(cdt, cdn, "qty", 0);
				frappe.model.set_value(cdt, cdn, "pch_mrp_total", 0);
				
				if(r.message.price) {
					frappe.model.set_value(cdt, cdn, "pch_pts", r.message.price.pts);
					frappe.model.set_value(cdt, cdn, "pch_ptr", r.message.price.ptr);
					frappe.model.set_value(cdt, cdn, "pch_mrp", r.message.price.mrp);

					frappe.meta.get_docfield(cdt, 'pch_pts', cdn).read_only = 1;
					frappe.meta.get_docfield(cdt, 'pch_ptr', cdn).read_only = 1;
					frappe.meta.get_docfield(cdt, 'pch_mrp', cdn).read_only = 1;
					frappe.meta.get_docfield(cdt, 'batch', cdn).read_only = 1;
				} else {
					frappe.meta.get_docfield(cdt, 'batch', cdn).read_only = 0;
				}

				cur_frm.refresh_fields();
			})
		}
	},

	qty(frm, cdt, cdn) {
		let doc = locals[cdt][cdn];

		if(doc.qty && doc.pch_mrp) {
			frappe.model.set_value(cdt, cdn, "pch_mrp_total", doc.qty*doc.pch_mrp);
			cur_frm.refresh_fields();
		}
	},

	pch_mrp(frm, cdt, cdn) {
		let doc = locals[cdt][cdn];

		if(doc.qty && doc.pch_mrp) {
			frappe.model.set_value(cdt, cdn, "pch_mrp_total", doc.qty*doc.pch_mrp);
			cur_frm.refresh_fields();
		}
	},

	batch(frm, cdt, cdn) {
		let doc = locals[cdt][cdn];

		if(doc.batch) {
			frappe.call({
				method: "bmga.bmga.doctype.breakage_and_expiry.breakage_and_expiry.get_batch_details",
				args: {
					batch: doc.batch
				}
			}).done(r => {
				if(r.message.price) {
					frappe.model.set_value(cdt, cdn, "pch_pts", r.message.price.pts);
					frappe.model.set_value(cdt, cdn, "pch_ptr", r.message.price.ptr);
					frappe.model.set_value(cdt, cdn, "pch_mrp", r.message.price.mrp);
					frappe.model.set_value(cdt, cdn, "expiry_date", r.message.price.expiry_date);

					frappe.meta.get_docfield(cdt, 'pch_pts', cdn).read_only = 1;
					frappe.meta.get_docfield(cdt, 'pch_ptr', cdn).read_only = 1;
					frappe.meta.get_docfield(cdt, 'pch_mrp', cdn).read_only = 1;
					frappe.meta.get_docfield(cdt, 'expiry_date', cdn).read_only = 1;
				} else {
					frappe.meta.get_docfield(cdt, 'pch_pts', cdn).read_only = 0;
					frappe.meta.get_docfield(cdt, 'pch_ptr', cdn).read_only = 0;
					frappe.meta.get_docfield(cdt, 'pch_mrp', cdn).read_only = 0;
					frappe.meta.get_docfield(cdt, 'expiry_date', cdn).read_only = 0;
				}

				cur_frm.refresh_fields();
			})
		}
	}
});