frappe.ui.form.on('Item', {
	setup(frm) {
		frm.set_query('pch_division', function() {
            let brand = frm.doc.brand;
            return {
                filters: [
                        ['brand', '=', brand]
                    ]
            };
        });
	}
})