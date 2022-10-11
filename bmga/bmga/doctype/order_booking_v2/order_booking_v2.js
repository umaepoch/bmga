// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt
var credit_days = false;

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
		let company = frm.doc.company;
		if(customer && company) {
			frm.set_value("order_booking_items_v2", [])
			frm.set_value("order_booking_so", null)
			frm.set_value("hunting_quotation", null)
			frm.set_value("credit_limit", null)
			frm.set_value("unpaid_amount", null)
			frm.set_value("pending_reason", null)
			
			frappe.call({
				method: "bmga.bmga.doctype.order_booking_v2.api.customer_type_container",
				args: {
					customer: customer,
					company: company
				}
			}).done((response) => {
				frm.set_value("customer_type", response.message.customer_type.pch_customer_type);
				frm.set_value("unpaid_amount", response.message.unpaid_amount);
				frm.set_value("credit_limit", response.message.credit_limit);
				refresh_field("customer_type");
				refresh_field("unpaid_amount");
				refresh_field("credit_limit");

				console.log(response.message)

				if(response.message.credit_days) {
					frm.set_value('pending_reason', 'Credit days exceeded');
					refresh_field('pending_reason');
					credit_days = true;
				}
			})
		}
	},

	validate: function(frm) {
		console.log(frm.doc.order_booking_items_v2[0])
		var order_list = frm.doc.order_booking_items_v2.map(function(d) {
			return {item_code: d.item_code, quantity_booked: d.quantity_booked, average_price:d.average_price, mrp:d.amount_after_gst,
				amount:d.amount, quantity_available:d.quantity_available, rate_contract:d.rate_contract_check};
		})
		var customer = frm.doc.customer
		let item_code_list = frm.doc.order_booking_items_v2.map(function(d) {
			return {item_code: d.item_code, quantity_booked: d.quantity_booked, average_price:d.average_price, amount:d.amount, quantity_available:d.quantity_available}
		})

		let customer_type = frm.doc.customer_type;

		frm.doc.promos = [];
		refresh_field("promos");

		frm.doc.promos_discount = [];
		refresh_field("promos_discount");

		frm.doc.sales_order_preview = [];
		refresh_field("sales_order_preview");

		let company = frm.doc.company;

		if(!customer_type) {
			customer_type = frm.doc.customer_type;
		}

		if (item_code_list) {
			frappe.call({
				method : "bmga.bmga.doctype.order_booking_v2.api.sales_promos",
				args :{
					company : company,
					customer: customer,
					order_list: order_list,
				}
			}).done((respose) =>{
				console.log(respose.message)
				let total_amount = 0;

				$.each(respose.message.sales_preview, function(_i, e) {
					let entry = frm.add_child("sales_order_preview");
					entry.item_code = e.item_code;
					entry.quantity_available = e.qty_available;
					entry.quantity = e.qty;
					entry.average = e.average_price;
					entry.promo_type = e.promo_type;
					entry.warehouse = e.warehouse;
					total_amount = total_amount + (e.qty * e.average_price);
				});

				refresh_field("sales_order_preview")

				frm.set_value('total_amount', total_amount);
				refresh_field("total_amount")

				if(total_amount + frm.doc.unpaid_amount > frm.doc.credit_limit) {
					frm.set_value('pending_reason', 'Credit limit exceeded');
					refresh_field('pending_reason');
				}	
				
				if(credit_days) {
					frm.set_value('pending_reason', 'Credit days exceeded');
					refresh_field('pending_reason');
				}

				$.each(respose.message.free_preview, function(_i, e) {
					let entry = frm.add_child("promos");
					entry.bought_item = e.bought_item;
					entry.free_items = e.free_item;
					entry.price = e.rate;
					entry.quantity = e.qty;
					entry.warehouse_quantity = e.warehouse_quantity;
					entry.promo_type = e.promo_type;
				});
				refresh_field("promos")

				$.each(respose.message.discount_preview, function(_i, e){
					let entry = frm.add_child("promos_discount");
					entry.bought_item = e.bought_item;
					entry.free_item = e.free_item;
					entry.quantity = e.dic_qty;
					entry.discount = e.dic;
					entry.promo_type = e.promo_type;
					entry.amount= e.amount;
				})

				refresh_field("promos_discount");
			})
		}	
	},

	before_submit: function(frm) {
		if(!frm.doc.pending_reason) {
			if(!frm.doc.order_booking_so) {
				let order_list = frm.doc.order_booking_items_v2;
				let customer = frm.doc.customer;
				let company = frm.doc.company;
				var free_promos = frm.doc.promos;
				var promo_dis = frm.doc.promos_discount;
				var sales_order = frm.doc.sales_order_preview;
				let customer_type = frm.doc.customer_type;
	
				if(free_promos == undefined || free_promos == null) {
					free_promos = []
				}
				if(promo_dis == undefined || promo_dis == null) {
					promo_dis = []
				}
				console.log('order list', order_list)
				if(order_list) {
					console.log('sales order container')
					frappe.call({
						method: "bmga.bmga.doctype.order_booking_v2.api.sales_order_container",
						args: {
							customer: customer,
							order_list: order_list,
							company: company,
							customer_type: customer_type,
							free_promos: free_promos,
							promo_dis: promo_dis,
							sales_order: sales_order,
						}
					}).done((response) => {
						frm.set_value("order_booking_so", response.message.so_name);
						frm.set_value("hunting_quotation", response.message.qo_name);
						frm.set_value("pch_status", "Approved");

						refresh_field("order_booking_so");
						refresh_field("hunting_quotation");
						refresh_field("pch_status");

						if(response.message.so_name != "" || response.message.qo_name != "") {
							frappe.msgprint("Order Booked!");
						} else {
							frappe.msgprint("No Order has been Placed")
						}
					})
				} else {
					frappe.msgprint("Select Customer First");
				}
			}
		} else {
			frm.set_value("pch_status", "Pending");
			refresh_field("pch_status");
		}
	},

	refresh: function(frm) {
		if(frm.doc.docstatus == 1 && frm.doc.pending_reason) {
			frm.add_custom_button(__('Approve'), function(){
				if(frm.doc.docstatus == 1 && !frm.doc.order_booking_so) {
					let order_list = frm.doc.order_booking_items_v2;
					let customer = frm.doc.customer;
					let customer_type = frm.doc.customer_type
					let company = frm.doc.company;
					var free_promos = frm.doc.promos;
					var promo_dis = frm.doc.promos_discount;
					var sales_order = frm.doc.sales_order_preview
		
					if(free_promos == undefined || free_promos == null) {
						free_promos = []
					}
					if(promo_dis == undefined || promo_dis == null) {
						promo_dis = []
					}
		
					if(order_list) {
						frappe.call({
							method: "bmga.bmga.doctype.order_booking_v2.api.sales_order_container",
							args: {
								customer: customer,
								order_list: order_list,
								company: company,
								customer_type: customer_type,
								free_promos: free_promos,
								promo_dis: promo_dis,
								sales_order: sales_order,
							}
						}).done((response) => {

							frm.set_value("order_booking_so", response.message.so_name);
							frm.set_value("hunting_quotation", response.message.qo_name);
							frm.set_value("pch_status", "Approved");

							refresh_field("order_booking_so");
							refresh_field("hunting_quotation");
							refresh_field("pch_status");

							frm.save('Update');

							if(response.message.so_name != "" || response.message.qo_name != "") {
								frappe.msgprint("Order Booked!");
							} else {
								frappe.msgprint("No Order has been Placed")
							}
						})
					} else {
						frappe.msgprint("Select Customer First");
					}
				}
			}, __("Actions"));
	
			frm.add_custom_button(__('Reject'), function(){
				frm.set_value("pch_status", "Rejected");
				refresh_field("pch_status");
			}, __("Actions"));
		}
	}
});


frappe.ui.form.on('Order Booking Items V2', {
	item_code: function(frm, cdt, cdn) {
		let item_code = frappe.get_doc(cdt, cdn).item_code;
		let company = frm.doc.company;
		let customer = frm.doc.customer;
		let customer_type = frm.doc.customer_type;

		if(item_code) {
			if(frm.check_duplicate(frm)) {
				frappe.msgprint("Can not re-select chosen item!");
				frappe.model.set_value(cdt, cdn, "item_code", null);
				frappe.model.set_value(cdt, cdn, "brand_name", null);
				frappe.model.set_value(cdt, cdn, "quantity_available", null);
				frappe.model.set_value(cdt, cdn, "quantity_booked", null);
				frappe.model.set_value(cdt, cdn, "average_price", null);
				frappe.model.set_value(cdt, cdn, "amount", null);
				frappe.model.set_value(cdt, cdn, "amount_after_gst", null);
				frappe.model.set_value(cdt, cdn, "rate_contract_check", 0)
				frappe.model.set_value(cdt, cdn, "sales_promo", 0)
				refresh_field("order_booking_items_v2");
			} else {
				frappe.call({
					method: "bmga.bmga.doctype.order_booking_v2.api.item_qty_container",
					args: {
						company: company,
						item_code: item_code,
						customer_type: customer_type,
						customer: customer
					}
				}).done((response) => {
					if(response.message.available_qty > 0) {
						frappe.model.set_value(cdt, cdn, "quantity_available", response.message.available_qty);
					} else {
						frappe.model.set_value(cdt, cdn, "quantity_available", 0);
					}
					frappe.model.set_value(cdt, cdn, "average_price", response.message.price_details.price);
					frappe.model.set_value(cdt, cdn, "rate_contract_check", response.message.price_details.rate_contract_check);
					frappe.model.set_value(cdt, cdn, "amount_after_gst", response.message.price_details.mrp);
					frappe.model.set_value(cdt, cdn, "brand_name", response.message.brand_name.brand_name);
					frappe.model.set_value(cdt, cdn, "sales_promo", response.message.promo_check);
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
			
			if(quantity_booked) {
				let amount = average_price * quantity_booked;
				frappe.model.set_value(cdt, cdn, "amount", amount);
				
				refresh_field("order_booking_items_v2");
			}
		} else {
			frappe.model.set_value(cdt, cdn, "quantity_booked", null);
			refresh_field("order_booking_items_v2");
			frappe.msgprint("Select Item First");
		}
	}
});