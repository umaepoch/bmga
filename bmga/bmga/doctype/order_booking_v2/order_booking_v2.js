// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt
var customer_type = null;

frappe.ui.form.on('Order Booking V2', {
	setup: function(frm) {
		frm.check_duplicate = function(frm) {
			var item_code_list = frm.doc.order_booking_items_v2.map(function(d) {
				return d.item_code;
			})
			for(let i=0; i<item_code_list.length; i++) {
				if(item_code_list.indexOf(item_code_list[i]) != i) {
					return true;
				}
			}
			return false;
		}
	},

	customer: function(frm) {
		let customer = frm.doc.customer;
		if(customer) {
			frm.set_value("order_booking_items_v2", [])
			frm.set_value("order_booking_so", null)
			frm.set_value("hunting_quotation", null)
			frappe.call({
				method: "bmga.bmga.doctype.order_booking_v2.api.customer_type_container",
				args: {
					customer: customer
				}
			}).done((response) => {
				console.log(response)
				customer_type = response.message.pch_customer_type;
				frm.set_value("customer_type", customer_type);
				refresh_field("customer_type");
			})
		}
	},

	refresh: function(frm) {
		frm.add_custom_button("Book Order", function() {
			let order_list = frm.doc.order_booking_items_v2;
			let customer = frm.doc.customer;
			let company = frm.doc.company;
			let customer_type = frm.doc.customer_type
			console.log(customer_type, company)
			if(order_list) {
				frappe.call({
					method: "bmga.bmga.doctype.order_booking_v2.api.sales_order_container",
					args: {
						customer: customer,
						order_list: order_list,
						company: company,
						customer_type: customer_type,
					}
				}).done((response) => {
					console.log(response)
					frm.set_value("order_booking_so", response.message.so_name);
					refresh_field("order_booking_so");
					frm.set_value("hunting_quotation", response.message.qo_name);
					refresh_field("hunting_quotation");
					if(response.message.so_name != "NA") {
						frappe.msgprint("Order Booked!");
					} else {
						frappe.msgprint("No Order has been Placed");
					}
				})
			} else {
				frappe.msgprint("Select Customer First");
			}
		})
	}
});

frappe.ui.form.on('Order Booking Items V2', {
	item_code: function(frm, cdt, cdn) {
		let item_code = frappe.get_doc(cdt, cdn).item_code;
		let company = frm.doc.company
		if(item_code) {
			if(frm.check_duplicate(frm)) {
				frappe.msgprint("Can not re-select chosen item!");
				frappe.model.set_value(cdt, cdn, "item_code", null);
				frappe.model.set_value(cdt, cdn, "quantity_available", null);
				frappe.model.set_value(cdt, cdn, "quantity_booked", null);
				frappe.model.set_value(cdt, cdn, "average_price", null);
				frappe.model.set_value(cdt, cdn, "amount", null);
				frappe.model.set_value(cdt, cdn, "amount_after_gst", null);
				refresh_field("order_booking_items_v2");
			} else {
				frappe.call({
					method: "bmga.bmga.doctype.order_booking_v2.api.item_qty_container",
					args: {
						company: company,
						item_code: item_code,
						customer_type: customer_type,
					}
				}).done((response) => {
					console.log(response)
					frappe.model.set_value(cdt, cdn, "quantity_available", response.message.available_qty);
					frappe.model.set_value(cdt, cdn, "average_price", response.message.average_price);
					refresh_field("order_booking_items_v2");
				})
			}
		}
	},
	quantity_booked: function(frm, cdt, cdn) {
		let item_code = frappe.get_doc(cdt, cdn).item_code;
		if(item_code) {
			let quantity_booked = frappe.get_doc(cdt, cdn).quantity_booked;
			let average_price = frappe.get_doc(cdt, cdn).average_price;
			var gst = parseFloat(frappe.get_doc(cdt, cdn).gst_rate);
			gst = (gst + 100)/100
			if(quantity_booked) {
				let amount = average_price * quantity_booked;
				frappe.model.set_value(cdt, cdn, "amount", amount);
				frappe.model.set_value(cdt, cdn, "amount_after_gst", amount * gst);
				refresh_field("order_booking_items_v2");
			}
		} else {
			frappe.model.set_value(cdt, cdn, "quantity_booked", null);
			refresh_field("order_booking_items_v2");
			frappe.msgprint("Select Item First");
		}
	}
});
