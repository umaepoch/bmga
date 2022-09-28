// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('Collection Trip', {
	before_submit(frm) {
		if(frm.doc.details) {
			frappe.call({
				method: "bmga.bmga.doctype.collection_trip.collection_trip.make_payment",
				args: {
					name: frm.doc.name,
					details: frm.doc.details
				}
			}).done(r => {
				if(!r.message || r.message.length ==0) {
					frappe.throw('Error please enter a valid Sum')
				}
				frm.doc.payment_entry = [];
				refresh_field("payment_entry");

				$.each(r.message, function(_i, e) {
					console.log('adding', e)
					let entry = frm.add_child("payment_entry");
					entry.payment_entry = e;
				})

				refresh_field("payment_entry")
				frappe.msgprint(`${r.message.length} Payment Entry Created`);
			})
		}
	},

	collection_person(frm) {
		if(frm.doc.collection_person) {
			frappe.call({
				method: "bmga.bmga.doctype.collection_trip.collection_trip.get_employee_name",
				args: {
					name: frm.doc.collection_person
				}
			}).done(r => {
				frm.set_value('collection_person_name', r.message);
				refresh_field('collection_person_name');
			})
		}
	}
});


frappe.ui.form.on('Collection Trip Item', {
	total_amount: function(frm, cdt, cdn) {
		if(locals[cdt][cdn].total_amount > 0) {
			frappe.meta.get_docfield('Collection Trip', 'collection_person', frm.doc.name).reqd = 1;
			cur_frm.refresh_fields();
		} else {
			frappe.meta.get_docfield('Collection Trip', 'collection_person', frm.doc.name).reqd = 0;
			cur_frm.refresh_fields();
		}
	},

	cash_amount: function(frm, cdt, cdn) {
		update_total_amount(cdt, cdn);
	},

	cheque_amount: function(frm, cdt, cdn) {
		update_total_amount(cdt, cdn);

		if(locals[cdt][cdn].cheque_amount > 0) {
			frappe.meta.get_docfield(cdt, 'cheque_reference', cdn).reqd = 1;
			frappe.meta.get_docfield(cdt, 'cheque_date', cdn).reqd = 1;
			cur_frm.refresh_fields();
		} else {
			frappe.meta.get_docfield(cdt, 'cheque_reference', cdn).reqd = 0;
			frappe.meta.get_docfield(cdt, 'cheque_date', cdn).reqd = 0;
			cur_frm.refresh_fields();
		}
	},

	wire_amount: function(frm, cdt, cdn) {
		update_total_amount(cdt, cdn);

		if(locals[cdt][cdn].wire_amount > 0) {
			frappe.meta.get_docfield(cdt, 'wire_reference', cdn).reqd = 1;
			frappe.meta.get_docfield(cdt, 'wire_date', cdn).reqd = 1;
			cur_frm.refresh_fields();
		} else {
			frappe.meta.get_docfield(cdt, 'wire_reference', cdn).reqd = 0;
			frappe.meta.get_docfield(cdt, 'wire_date', cdn).reqd = 0;
			cur_frm.refresh_fields();
		}
	},

});

var update_total_amount = function(cdt, cdn) {
	let doc = locals[cdt][cdn]

	frappe.model.set_value(cdt, cdn, 'total_amount', doc.cash_amount + doc.cheque_amount + doc.wire_amount);
	refresh_field("order_booking_items_v2");
}