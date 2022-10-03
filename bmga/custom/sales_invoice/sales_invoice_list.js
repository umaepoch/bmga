frappe.listview_settings['Sales Invoice'].onload = function(listview) {
    // add button to menu
    listview.page.add_action_item(__("Make Delivery Trip"), function() {
        var promise_list = []

    	$.each(listview.get_checked_items(), function(key, value) {
            if(value.docstatus < 2) {
                const p = new Promise((resolve, reject) => {
                    frappe.call({
                        method: 'bmga.global_api.generate_delivery_note',
                        args: {
                            sales_invoice: value.name
                        }
                    }).done(r => {
                        resolve(r.message)
                    })
                });
                promise_list.push(p)
            }
        })

        if(promise_list.length > 0) {
            Promise.all(promise_list).then(v => {
                frappe.call({
                    method: 'bmga.global_api.generate_delivery_trip',
                    args: {
                        delivery_notes: v
                    }
                }).done(r => {
                    frappe.msgprint(`Delivery Trip Generated at ${r.message}`)
                })

            })
        }
    });
};