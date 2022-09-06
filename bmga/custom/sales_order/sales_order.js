frappe.ui.form.on('Sales Order', {
	refresh(frm) {
        console.log(frm.doc)
		// BMGA customize button call for order process
		if (frm.doc.pch_picking_status && !frm.doc.pch_pick_put_list) {
    		frm.add_custom_button("Process Order", function() {
    			let so_name = frm.doc.name;
                let company = frm.doc.company;
    			if(so_name) {
    				frappe.call({
    					method: "bmga.global_api.pick_put_list_container",
    					args: {
    						so_name: so_name,
                            company: company
    					}
    				}).done((response) => {
    				    console.log(response.message)
    					frappe.msgprint(`Pick Put List generated for ${response.message.so_name} at ${response.message.ppl_name}`)
    					frm.set_value('pch_pick_put_list', response.message.ppl_name)
    					refresh_field('pch_pick_put_list')
    					frm.save();
    				})
    			}
    		})
		}
	}
})