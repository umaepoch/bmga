frappe.listview_settings['Sales Order'].onload = function(listview) {
    // add button to menu
    listview.page.add_action_item(__("Process Order"), function() {
    	$.each(listview.get_checked_items(), function(key, value) {
            if(!value.pch_pick_put_list && value.docstatus == 0) {
                console.log(value)
                let name = value.name;
                let company = value.company;
                frappe.call({
                    method: "bmga.global_api.pick_put_list_container",
                    args: {
                        so_name: name,
                        company: company
                    }
                }).done(r => {
                    console.log(r)
                    frappe.model.set_value("Sales Order", name, "pch_pick_put_list", r.message.ppl_name);
                })
            }
        })
    });
};