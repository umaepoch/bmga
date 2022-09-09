frappe.listview_settings['Pick Put List'] = {
    get_indicator: function (doc) {
        if(doc.pick_list_stage === "Ready for Picking") {
            return [__("Ready for Picking"), "orange", "doc.pick_list_stage,=,Ready for Picking"];
        } else if (doc.pick_list_stage === "QC Area") {
            return [__("QC Area"), "orange", "doc.pick_list_stage,=,QC Area"];
        } else if (doc.pick_list_stage === "Packing Area") {
            return [__("Packing Area"), "orange", "doc.pick_list_stage,=,Packing Area"];
        } else if (doc.pick_list_stage === "Dispatch Area") {
            return [__("Dispatch Area"), "orange", "doc.pick_list_stage,=,Dispatch Area"];
        } else if (doc.pick_list_stage === "Invoiced") {
            return [__("Invoiced"), "green", "doc.pick_list_stage,=,Invoiced"];
        }
    },
    
    onload(listview) {
        let stage_list = ["Ready for Picking", "QC Area", "Packing Area", "Dispatch Area", "Invoiced"]

        listview.page.add_action_item(__("Pick Complete"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                pick_flow(value, "Ready for Picking", "Picking Complete", stage_list);
            })
        });

        listview.page.add_action_item(__("QC Complete"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                pick_flow(value, "QC Area", "QC Complete", stage_list);
            })
        });

        listview.page.add_action_item(__("Packing Complete"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                pick_flow(value, "Packing Area", "Packing Complete", stage_list);
            })
        });

        listview.page.add_action_item(__("Invoice Picklist"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                pick_flow(value, "Dispatch Area", "Invoice Picklist", stage_list);
                
            })
        });
    }
};

const pick_flow = function(value, stage, print_msg, stage_list) {
    if(value.pick_list_stage == stage) {
        let so_name = value.sales_order;
        let company = value.company;
        let pick_stage = value.pick_list_stage;

        frappe.call({
            method: "bmga.global_api.fetch_pick_put_list_items",
            args: {
                name: value.name,
            }
        }).done(r => {
            let item_list = r.message;

            if(item_list.length > 0 && pick_stage) {
                frappe.call({
                    method: "bmga.bmga.doctype.pick_put_list.api.pick_status",
                    args: {
                        item_list: item_list,
                        so_name: so_name,
                        company: company,
                        stage_index: stage_list.indexOf(pick_stage),
                        stage_list: stage_list
                    }
                }).done((response) => {
                    if(response.message.next_stage == "Invoiced") {
                        frappe.call({
                            method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_material_names",
                            args: {
                                doc_name: value.name,
                                names: response.message.names,
                                sales_invoice: response.message.sales_invoice_name 
                            }
                        }).done(r => {
                            frappe.call({
                                method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_stages",
                                args: {
                                    doc_name: value.name,
                                    next_stage: response.message.next_stage
                                }
                            }).done(r => {
                                frappe.msgprint(print_msg)
                            })
                        })
                    } else {
                        frappe.call({
                            method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_stages",
                            args: {
                                doc_name: value.name,
                                next_stage: response.message.next_stage
                            }
                        }).done(r => {
                            frappe.msgprint(print_msg)
                        })
                    }
                })
            }
        })
    }
}