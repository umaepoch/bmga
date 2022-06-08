// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sun Pharama Claim Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 1,
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 1,
		}
	]
};
