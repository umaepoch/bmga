// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt

frappe.ui.form.on('BMGA Purchase Order', {
	setup: function(frm) {
		frm.set_query('division', function() {
            let brand = frm.doc.brand;
            return {
                filters: [
                        ['brand', '=', brand]
                    ]
            };
        });  
	},

	
	division: function(frm) {
		let division = frm.doc.division;
		let brand = frm.doc.brand;
		frm.doc.items = [];

		if(brand && division.length > 0) {
			frappe.call({
				method: 'bmga.bmga.doctype.bmga_purchase_order.api.fetch_items_container',
				args: {
					brand: brand,
					division: division,
				}
			}).done(r => {
				console.log(r.message);
				$.each(r.message.items, function(_i, e) {
					let entry = frm.add_child('items');
					entry.item_name = e.item_name;
					entry.uom = e.uom;
					entry.last_30_days_sales = e.last30_qty;
					entry.stock_in_hand = e.stock_in_hand;
					entry.pending_qty = e.pending_qty;
					entry.start_date = e.start_date;
					entry.end_date = e.end_date;
					entry.purchase_promo = e.purchase_promo;
					entry.sales_promo = e.sales_promo;
					entry.item_code = e.item_code;
				});

				refresh_field('items');
			});
		}
	},

	refresh: function(frm) {
		let items = frm.doc.items;
		let supplier = frm.doc.supplier;
		console.log(frm.doc);

		if(items && supplier) {
			if(items.length > 0) {
				frm.add_custom_button('Make Purchase Receipt', function() {
					frappe.call({
						method: 'bmga.bmga.doctype.bmga_purchase_order.api.generate_purchase_receipt',
						args: {
							supplier: supplier,
							data: items
						}
					}).done(r => {
						console.log(r.message);
						if(r.message.name) {
							let entry = frm.add_child('purchase_receipt');
							entry.purchase_receipt = r.message.name;
							refresh_field('purchase_receipt');
							frappe.msgprint('Purchase Receipt Added');
							frm.save()
						} else {
							frappe.msgprint('Place QTY for Order')
						}
					})
				});
			}
		}

		let purchase_receipt = frm.doc.purchase_receipt;
		if(purchase_receipt.length > 0) {
			frappe.call({
				method: 'bmga.bmga.doctype.bmga_purchase_order.api.update_pending_qty',
				args: {
					purchase_receipt: purchase_receipt
				}
			}).done(r => {
				console.log(r.message)
			})
		}
	}
});


frappe.ui.form.on('BMGA Purchase Items', {
	qty_ordered: function(frm, cdt, cdn) {
		let qty = locals[cdt][cdn].qty_ordered;
		if(qty) {
			frappe.model.set_value(cdt, cdn, "pending_qty", qty);
			refresh_field('items');
		}
	}
})
