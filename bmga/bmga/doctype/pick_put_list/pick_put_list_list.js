frappe.listview_settings['Pick Put List'] = {
    get_indicator: function (doc) {
        if(doc.pick_list_stage === "Ready for Picking") {
            return [__("Ready for Picking"), "orange", "status,=,Ready for Picking"];
        } else if (doc.pick_list_stage === "QC Area") {
            return [__("QC Area"), "orange", "status,=,QC Area"];
        } else if (doc.pick_list_stage === "Packing Area") {
            return [__("Packing Area"), "orange", "status,=,Packing Area"];
        } else if (doc.pick_list_stage === "Dispatch Area") {
            return [__("Dispatch Area"), "orange", "status,=,Dispatch Area"];
        } else if (doc.pick_list_stage === "Invoiced") {
            return [__("Invoiced"), "green", "status,=,Invoiced"];
        }
    },
    
    onload(listview) {
        let stage_list = ["Ready for Picking", "QC Area", "Packing Area", "Dispatch Area", "Invoiced"]

        listview.page.add_action_item(__("Pick Complete"), function() {
            console.log('picking')
            $.each(listview.get_checked_items(), function(key, value) {
                console.log(value)
                if(value.pick_list_stage == "Ready for Picking") {
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
                            console.log(value);
    
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
                                console.log('finished index ', key)
                                frappe.call({
                                    method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_stages",
                                    args: {
                                        doc_name: value.name,
                                        next_stage: response.message.next_stage
                                    }
                                })
                            })
                        }
                    })
                }
            })
        });

        listview.page.add_action_item(__("QC Complete"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.pick_list_stage == "QC Area") {
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
                            console.log(value);
    
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
                                console.log('finished index ', key)
                                frappe.call({
                                    method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_stages",
                                    args: {
                                        doc_name: value.name,
                                        next_stage: response.message.next_stage
                                    }
                                })
                            })
                        }
                    })
                }
            })
        });

        listview.page.add_action_item(__("Packing Complete"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.pick_list_stage == "Packing Area") {
                    let item_list = value.item_list;
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
                            console.log(value);
    
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
                                console.log('finished index ', key)
                                frappe.call({
                                    method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_stages",
                                    args: {
                                        doc_name: value.name,
                                        next_stage: response.message.next_stage
                                    }
                                })
                            })
                        }
                    })
                }
            })
        });

        listview.page.add_action_item(__("Invoice Picklist"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.pick_list_stage == "Dispatch Area") {
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
                            console.log(value);
    
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
                                frappe.call({
                                    method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_stages",
                                    args: {
                                        doc_name: value.name,
                                        next_stage: response.message.next_stage
                                    }
                                })
    
                                if(response.message.next_stage == "Invoiced") {
                                    frappe.call({
                                        method: "bmga.bmga.doctype.pick_put_list.api.update_pick_put_list_material_names",
                                        args: {
                                            doc_name: value.name,
                                            names: response.message.names,
                                            sales_invoice: response.message.sales_invoice_name 
                                        }
                                    })
                                }
                            })
                        }
                    })
                }
            })
        });
    }
};