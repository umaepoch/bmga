// Copyright (c) 2022, karthik raman and contributors
// For license information, please see license.txt

// cache memory: items, fulfillment settings, warehouse details (batches, prices, etc ...)
var data = null;
var fulfillment_settings = null;
var customer_type = null;
var sales_sum_data = {};
var customer = null;

// verifing variable to see if data has properly been fetched
var details_fetched = false;
var settings_fetched = false;

frappe.ui.form.on('Order Booking', {
	setup: function(frm) {
		frm.check_duplicate=function(frm) {
			var item_code_list = frm.doc.order_booking_items.map(function(d) {
				return d.item_code
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
		// fetch the warehouse details for the customer taking into count the company's settings
		let company = frm.doc.company
		customer = frm.doc.customer
		if(customer) {
			frappe.call({
				method: "bmga.bmga.doctype.order_booking.order_booking_api.customer_type_container",
				args: {
					customer: customer,
				}
			}).done((response) => {
				customer_type = response.message.pch_customer_type;
				frm.set_value("customer_type", customer_type);
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
					frappe.msgprint("Error Company/Customer or Customer Type/Fulfillment Settings for the mentioned company not set!");
					//setTimeout(window.location.reload(), 5000);
				}
			})
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
			if(customer){
				let data = [];
				let keys = Object.keys(sales_sum_data)
				for(var i=0; i<keys.length; i++) {
					data.push(...sales_sum_data[keys[i]])
				}
				console.log(data)
				frappe.call({
					method: "bmga.bmga.doctype.order_booking.order_booking_api.add_sales_order",
					args: {
						sales_data: data,
						customer: customer
					}
				}).done(response => {
					let so_name = response.message.so_name
					frm.doc.order_booking_so = so_name
					frappe.msgprint("You Order has been Placed")
					refresh_field("order_booking_so");
				})
			}
		})
	},
});

frappe.ui.form.on('Order Booking Items', {
	// once item is selected display the needed information (available qty, etc ...)
	item_code: function(frm, cdt, cdn) {
		if(details_fetched) {
			let item_code = frappe.get_doc(cdt, cdn).item_code
			if(item_code) {
				if(frm.check_duplicate(frm)) {
					frappe.msgprint("Can not re-select chosen item!")
					frappe.model.set_value(cdt, cdn, "item_code", null);
					frappe.model.set_value(cdt, cdn, "quantity_available", null);
					frappe.model.set_value(cdt, cdn, "quantity_booked", null);
					frappe.model.set_value(cdt, cdn, "average_price", null);
					frappe.model.set_value(cdt, cdn, "amount", null);
					frappe.model.set_value(cdt, cdn, "amount_after_gst", null);
					refresh_field("order_booking_items");
				} else {
					frappe.model.set_value(cdt, cdn, "quantity_available", data[item_code]["quantity_available"]);
					refresh_field("order_booking_items");
				}
			}
		}
	},
	quantity_booked: function(frm, cdt, cdn) {
		let details = frappe.get_doc(cdt, cdn);
		// check if item is selected
		let item_code = frappe.get_doc(cdt, cdn).item_code
		if(details_fetched) {
			if(!item_code) {
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
						let sales_data = response.message.sales_data
						let new_data = response.message.new_data
						sales_sum_data[item_code] = sales_data
						console.log("new data", new_data)
						console.log("sales data", sales_data)
						console.log("sales sum data", sales_sum_data)
						if(new_data.hunt) {
							frappe.msgprint(`Need to Hunt ${new_data.hunt_quantity} ${new_data.updated_item_detail.item_code}`)
						} else {
							frappe.model.set_value(cdt, cdn, "average_price", new_data.average_price);
							frappe.model.set_value(cdt, cdn, "amount", new_data.amount);
							frappe.model.set_value(cdt, cdn, "amount_after_gst", new_data.amount_after_gst);
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
