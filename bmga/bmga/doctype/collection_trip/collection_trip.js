// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Collection Trip', {
	before_submit(frm) {
		if(frm.doc.details) {
			frappe.call({
				method: "bmga.bmga.doctype.collection_trip.collection_trip.make_payment",
				args: {
					details: frm.doc.details
				}
			}).done(r => {
				frappe.msgprint(`${r.message.length} Payment Entry Created`);
			})
		}
	}
});


frappe.ui.form.on('Collection Trip Item', {
	cash_amount: function(frm, cdt, cdn) {
		update_total_amount(cdt, cdn);
	},

	cheque_amount: function(frm, cdt, cdn) {
		update_total_amount(cdt, cdn);
	},

	wire_amount: function(frm, cdt, cdn) {
		update_total_amount(cdt, cdn);
	},

});

var update_total_amount = function(cdt, cdn) {
	let doc = locals[cdt][cdn]

	frappe.model.set_value(cdt, cdn, 'total_amount', doc.cash_amount + doc.cheque_amount + doc.wire_amount);
	refresh_field("order_booking_items_v2");
}