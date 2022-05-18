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
			let customer_type = frm.doc.customer_type;
			var free_promos = frm.doc.promos;
			var promo_dis = frm.doc.promos_discount;
			
			if(free_promos == undefined || free_promos == null) {
				free_promos = []
			}
			if(promo_dis == undefined || promo_dis == null) {
				promo_dis = []
			}
			
			console.log("dis...", promo_dis)
			console.log("free_items", free_promos)
			console.log(customer_type, company)
			console.log(order_list)
			if(order_list) {
				frappe.call({
					method: "bmga.bmga.doctype.order_booking_v2.api.sales_order_container",
					args: {
						customer: customer,
						order_list: order_list,
						company: company,
						customer_type: customer_type,
						free_promos: free_promos,
						promo_dis: promo_dis
					}
				}).done((response) => {
					console.log(response)
					frm.set_value("order_booking_so", response.message.so_name);
					refresh_field("order_booking_so");
					frm.set_value("hunting_quotation", response.message.qo_name);
					refresh_field("hunting_quotation");
					frm.save();
					if(response.message.so_name != "" || response.message.qo_name != "") {
						frappe.msgprint("Order Booked!");
					} else {
						frappe.msgprint("No Order has been Placed")
					}
				})
			} else {
				frappe.msgprint("Select Customer First");
			}
		})
		frm.add_custom_button("Apply Promo", function(){
			let item_code_list = frm.doc.order_booking_items_v2.map(function(d) {
				return {item_code: d.item_code, quantity_booked: d.quantity_booked, average_price:d.average_price, amount:d.amount}
			})
			
			frm.doc.promos = [];
			refresh_field("promos");

			frm.doc.promos_discount = [];
			refresh_field("promos_discount");

			let company = frm.doc.company;
			if (item_code_list) {
				frappe.call({
					method : "bmga.bmga.doctype.order_booking_v2.api.sales_promos",
					args :{
						item_code: 	JSON.stringify(item_code_list),
						customer_type: customer_type,
						company : company,
					}
				}).done((respose) =>{
					console.log("Hai",respose)
					$.each(respose.message.sales_promos_items, function(_i, e) {
						let entry = frm.add_child("promos");
						entry.bought_item = e.bought_item;
						entry.free_items = e.promo_item;
						entry.price = e.rate;
						entry.quantity = e.qty;
						entry.warehouse_quantity = e.w_qty;
						entry.promo_type = e.promo_type;
					}),
					refresh_field("promos"),
					$.each(respose.message.sales_promo_discounted_amount, function(_i, e){
						let entry = frm.add_child("promos_discount");
						entry.bought_item = e.bought_item;
						entry.free_item = e.promo_item;
						entry.quantity = e.dic_qty;
						entry.discount = e.dic;
						entry.promo_type = e.promo_type;
						entry.amount= e.amount;
					})
					refresh_field("promos_discount")
					frappe.msgprint("Promos Applied")
				})
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

