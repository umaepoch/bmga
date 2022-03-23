// Copyright (c) 2022, karthik raman and contributors
// For license information, please see license.txt

// cache memory: items, fulfillment settings, warehouse details (batches, prices, etc ...)
var data = null;
var item_code = null;
var fulfillment_settings = null;
var customer_type = null;

// verifing variable to see if data has properly been fetched
var details_fetched = false;
var settings_fetched = false;

frappe.ui.form.on('Order Booking', {
	customer: function(frm) {
		// fetch the warehouse details for the customer taking into count the company's settings
		customer_type = frm.doc.customer_type
		let company = frm.doc.company
		if(customer_type && company && settings_fetched) {
			frappe.call({
				method: "bmga.bmga.doctype.order_booking.order_booking_api.order_booking_container",
				args: {
					fulfillment_settings: fulfillment_settings,
					customer_type: customer_type
				}
			}).done((response) => {
				data = response.message;
				console.log(data)
				details_fetched = true;
				if(data.length == 0) {
					frm.doc.order_booking_items = []
					frappe.msgprint("Error Item/Batch/Item Price not present in Stock!");
					details_fetched = false;
				}
				frm.doc.order_booking_items = []
				refresh_field("order_booking_items");
			})
		} else {
			frappe.msgprint("Error Company/Customer/Fulfillment Settings for the mentioned company not set!");
			//setTimeout(window.location.reload(), 5000);
		}
	},
	company: function(frm) {
		// fetch the company's fulfillment settings
		let company = frm.doc.company
		if(company) {
			frappe.call({
				method: "bmga.bmga.doctype.order_booking.order_booking_api.fulfillment_settings_container",
				args: {
					company: company
				}
			}).done((response) => {
				fulfillment_settings = response.message;
				if(fulfillment_settings.length > 0) {
					settings_fetched = true;
				}
			})
		}	
	},
	refresh: function(frm) {
		// add a botton to place the order
		frm.add_custom_button("Book Order", function() {
			frappe.msgprint("Order Placed")
		})
	},
});

frappe.ui.form.on('Order Booking Items', {
	// once item is selected display the needed information (available qty, etc ...)
	item_code: function(frm, cdt, cdn) {
		if(details_fetched) {
			item_code = frappe.get_doc(cdt, cdn).item_code
			if(item_code) {
				frappe.model.set_value(cdt, cdn, "quantity_available", data[item_code]["quantity_available"]);
				refresh_field("order_booking_items");
			}
		}
	},
	quantity_booked: function(frm, cdt, cdn) {
		let details = frappe.get_doc(cdt, cdn);
		// check if item is selected
		if(details_fetched) {
			if(!frappe.get_doc(cdt, cdn).item_code) {
				frappe.model.set_value(cdt, cdn, "quantity_booked", null);
				refresh_field("order_booking_items");
				frappe.msgprint("Chose an Item First!");
			}
			// check if order placed fits in the given available amount
			if(details && item_code) {
				if(details.quantity_booked < 0) {
					frappe.model.set_value(cdt, cdn, "quantity_booked", null);
					refresh_field("order_booking_items");
					frappe.msgprint("Booking Quantity Should be greater then Zero!");
				} else if (details.quantity_booked <= details.quantity_available) {
					frappe.call({
						method:"bmga.bmga.doctype.order_booking.order_booking_api.order_booked_container",
						args: {
							items_data: data[item_code],
							quantity_booked: details.quantity_booked,
							fulfillment_settings: fulfillment_settings,
							customer_type: customer_type
						}
					// provide the amount details
					}).done((response) => {
						//new_data[response.message.updated_item_detail.item_code] = response.message.updated_item_detail;
						console.log("data", data);
						if(response.message.hunt) {
							frappe.msgprint(`Need to Hunt ${response.message.hunt_quantity} ${response.message.updated_item_detail.item_code}`)
						} else {
							frappe.model.set_value(cdt, cdn, "average_price", response.message.average_price);
							frappe.model.set_value(cdt, cdn, "amount", response.message.amount);
							frappe.model.set_value(cdt, cdn, "amount_after_gst", response.message.amount_after_gst);
							refresh_field("order_booking_items");
						}
					})
				// add item to the Hunting list
				} else {
					frappe.msgprint("The Hunting is On");
				}
			}
		}
	},
	refresh(frm) {
		// your code here
	}
})
