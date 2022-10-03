// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Return Invoice to Customer"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
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
		report.page.add_inner_button(__("Create Return Invoice "), function() {
			let company = report.filters[0].value;
			let data = report.data

			if(company && data) {
				frappe.call({
					method: "bmga.bmga.report.return_invoice_to_customer.return_invoice_to_customer.create_return_invoice",
					args: {
						company: company,
						data: data
					}
				}).done(r => {
					if(r.message.length > 0) {
						let names = r.message.toString();
						frappe.msgprint(`Generated Purchase Invoice at ${names}`);
					}
				})
			}
		});
	}
};