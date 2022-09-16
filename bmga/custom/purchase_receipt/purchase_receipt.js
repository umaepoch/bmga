frappe.ui.form.on('Purchase Receipt', {
	refresh(frm) {
		// your code here
		// console.log(frm.doc)
		if(frm.doc.docstatus == 1) {
    		frm.add_custom_button("Pre-Stock Transfer", function() {
    		    let items = frm.doc.items
    		    let name = frm.doc.name
    		    if(items) {
    		        frappe.call({
    		            method: "bmga.global_api.generate_prestock_transfer",
    		            args: {
    		                items: items,
    		                name: name
    		            }
    		        }).done(r => {
    		            if(r.message.name) {
    		                frappe.msgprint(`Pre-Stock Transfer Created at ${r.message.name}`)
    		                frm.doc.pch_prestock_transfer = r.message.name;
    		                refresh_field('pch_prestock_transfer')
    		            }
    		        })
    		    }
    		})
		}
	},

    after_save(frm) {
        $.each(frm.doc.items, function(_e, i) {
            console.log(i.pch_ptr, i.pch_pts*1.07)
            if(i.pch_ptr < i.pch_pts*1.07) {
                frappe.msgprint(`${i.item_code} PTR 7% margin not valid`)
            }
        })
    },
	
	on_submit(frm) {
	    let items = frm.doc.items;
	    if(items) {
	        frappe.call({
	            method: "bmga.global_api.update_price_list_batch",
	            args: {
	                items: items 
	            }
	        }).done(r => {
	            console.log(r.message)
	        })
	    }
	}
})