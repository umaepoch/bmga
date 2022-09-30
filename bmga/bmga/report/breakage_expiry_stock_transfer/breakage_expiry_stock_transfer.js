// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Breakage Expiry Stock Transfer"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1,
		},
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"reqd": 1,
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			"reqd": 1,
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1,
		},
	],

	onload(report) {
		report.page.add_inner_button(__("Material Transfer"), function() {
			let company = report.filters[0].value;
			let warehouse = report.filters[1].value;
			let data = report.data;

			if(company && warehouse && data) {
				frappe.call({
					method: "bmga.bmga.report.breakage_expiry_stock_transfer.breakage_expiry_stock_transfer.generate_material_transfer",
					args: {
						company: company,
						f_warehouse: warehouse,
						data: data
					}
				}).done(r => {
					if(r.message.name) {
						frappe.msgprint(`Generated material transfer at ${r.message.name}`)
					}

					if(r.message.error) {
						frappe.msgprint(`${r.message.error}`)
					}
				})
			}
		});
	}
};
