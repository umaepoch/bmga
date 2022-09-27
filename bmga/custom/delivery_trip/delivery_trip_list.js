frappe.listview_settings['Delivery Trip'] = {
    onload(listview) {
        listview.page.add_action_item(__("Make Collection Trip"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.docstatus == 1) {
                    frappe.call({
                        method: 'bmga.global_api.generate_collection_trip',
                        args: {
                            name: value.name
                        }
                    }).done(r => {
                        frappe.msgprint(`Generate Collection Trip ${r.message.name}`)
                    })
                }
            })
        })
    },
}