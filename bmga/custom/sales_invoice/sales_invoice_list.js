frappe.listview_settings['Sales Invoice'].onload = function(listview) {
    // add button to menu
    listview.page.add_action_item(__("Make Delivery Trip"), function() {
        var processed_delivery_notes = [];

    	$.each(listview.get_checked_items(), function(key, value) {
            if(value.docstatus < 2) {
                frappe.call({
                    method: 'bmga.global_api.generate_delivery_note',
                    args: {
                        sales_invoice: value.name
                    }
                }).done(r => {
                    processed_delivery_notes.push(r.message);

                    if(key+1 == listview.get_checked_items().length) {
                        console.log('delivery notes', processed_delivery_notes);
                        frappe.call({
                            method: 'bmga.global_api.generate_delivery_trip',
                            args: {
                                delivery_notes: processed_delivery_notes
                            }
                        }).done(r => {
                            console.log(r.message);
                        })
                    }
                });
            }
        })
    });
};