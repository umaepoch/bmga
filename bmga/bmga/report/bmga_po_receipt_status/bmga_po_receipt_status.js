// Copyright (c) 2022, Karthik Raman and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["BMGA PO Receipt Status"] = {
	"filters": [
		{
			"label": __("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier"
		},
		{
			"label": __("Brand"),
			"fieldname": "brand",
			"fieldtype": "Link",
			"options": "Brand"
		}
	]
};
