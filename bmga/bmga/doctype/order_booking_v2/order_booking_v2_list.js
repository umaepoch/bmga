frappe.listview_settings['Order Booking V2'] = {
    get_indicator: function (doc) {
        if(doc.pch_status === "Draft") {
            return [__("Draft"), "gray", "doc.pch_status,=,Draft"];
        } else if (doc.pch_status === "Pending") {
            return [__("Pending"), "orange", "doc.pch_status,=,Pending"];
        } else if (doc.pch_status === "Approved") {
            return [__("Approved"), "green", "doc.pch_status,=,Approved"];
        } else if (doc.pch_status === "Rejected") {
            return [__("Rejected"), "red", "doc.pch_status,=,Rejected"];
        }
    },

    onload(listview) {
        listview.page.add_action_item(__("Bulk Submit"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.pch_status == "Draft") {
                    if(value.pending_reason) {
                        console.log('pending order');
                        frappe.call({
                            method: "bmga.bmga.doctype.order_booking_v2.api.pending_order",
                            args: {
                                name: value.name
                            }
                        })
                    } else {
                        console.log('approve order');
                        approve_order(value);
                        frappe.call({
                            method: "bmga.bmga.doctype.order_booking_v2.api.submit_order",
                            args: {
                                name: value.name
                            }
                        })
                    }
                }
            });
        });

        listview.page.add_action_item(__("Approve"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.pch_status == "Pending") {
                    approve_order(value);
                }
            });
        });

        listview.page.add_action_item(__("Reject"), function() {
            $.each(listview.get_checked_items(), function(key, value) {
                if(value.pch_status == "Pending") {
                    frappe.call({
                        method: "bmga.bmga.doctype.order_booking_v2.api.reject_order",
                        args: {
                            name: value.name
                        }
                    });
                }
            });
        });
    },
};

const approve_order = function (value) {
    frappe.call({
        method: "bmga.bmga.doctype.order_booking_v2.api.fetch_order_items",
        args: {
            name: value.name
        }
    }).done(r => {
        let customer = value.customer;
        let company = value.company;
        let customer_type = value.customer_type;

        let order_list = r.message.order_booking_items_v2;
        let free_promos = r.message.promos;
        let promo_dis = r.message.promos_discount;
        let sales_order = r.message.sales_order_preview

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
                    name: value.name,
                    customer: customer,
                    order_list: order_list,
                    company: company,
                    customer_type: customer_type,
                    free_promos: free_promos,
                    promo_dis: promo_dis,
                    sales_order: sales_order,
                }
            }).done((response) => {
                frappe.call({
                    method: "bmga.bmga.doctype.order_booking_v2.api.approve_order",
                    args: {
                        name: value.name,
                        so_name: response.message.so_name,
                        qo_name: response.message.qo_name
                    }
                });
            })
        }
    })
};