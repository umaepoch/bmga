import json
import frappe
import datetime
from erpnext.accounts.utils import get_balance_on
import re
from frappe.utils import flt

# Credit limit
def get_credit_limit(customer, company):
	credit_limit = None

	if customer:
		credit_limit = frappe.db.get_value("Customer Credit Limit",
			{'parent': customer, 'parenttype': 'Customer', 'company': company}, 'credit_limit')

		if not credit_limit:
			customer_group = frappe.get_cached_value("Customer", customer, 'customer_group')
			credit_limit = frappe.db.get_value("Customer Credit Limit",
				{'parent': customer_group, 'parenttype': 'Customer Group', 'company': company}, 'credit_limit')

	if not credit_limit:
		credit_limit = frappe.get_cached_value('Company',  company,  "credit_limit")

	return flt(credit_limit)

def get_customer_outstanding(customer, company, ignore_outstanding_sales_order=False, cost_center=None):
	# Outstanding based on GL Entries

	cond = ""
	if cost_center:
		lft, rgt = frappe.get_cached_value("Cost Center",
			cost_center, ['lft', 'rgt'])

		cond = """ and cost_center in (select name from `tabCost Center` where
			lft >= {0} and rgt <= {1})""".format(lft, rgt)

	outstanding_based_on_gle = frappe.db.sql("""
		select sum(debit) - sum(credit)
		from `tabGL Entry` where party_type = 'Customer'
		and party = %s and company=%s {0}""".format(cond), (customer, company))

	outstanding_based_on_gle = flt(outstanding_based_on_gle[0][0]) if outstanding_based_on_gle else 0

	# Outstanding based on Sales Order
	outstanding_based_on_so = 0

	# if credit limit check is bypassed at sales order level,
	# we should not consider outstanding Sales Orders, when customer credit balance report is run
	if not ignore_outstanding_sales_order:
		outstanding_based_on_so = frappe.db.sql("""
			select sum(base_grand_total*(100 - per_billed)/100)
			from `tabSales Order`
			where customer=%s and docstatus = 1 and company=%s
			and per_billed < 100 and status != 'Closed'""", (customer, company))

		outstanding_based_on_so = flt(outstanding_based_on_so[0][0]) if outstanding_based_on_so else 0

	# Outstanding based on Delivery Note, which are not created against Sales Order
	outstanding_based_on_dn = 0

	unmarked_delivery_note_items = frappe.db.sql("""select
			dn_item.name, dn_item.amount, dn.base_net_total, dn.base_grand_total
		from `tabDelivery Note` dn, `tabDelivery Note Item` dn_item
		where
			dn.name = dn_item.parent
			and dn.customer=%s and dn.company=%s
			and dn.docstatus = 1 and dn.status not in ('Closed', 'Stopped')
			and ifnull(dn_item.against_sales_order, '') = ''
			and ifnull(dn_item.against_sales_invoice, '') = ''
		""", (customer, company), as_dict=True)

	if not unmarked_delivery_note_items:
		return outstanding_based_on_gle + outstanding_based_on_so

	si_amounts = frappe.db.sql("""
		SELECT
			dn_detail, sum(amount) from `tabSales Invoice Item`
		WHERE
			docstatus = 1
			and dn_detail in ({})
		GROUP BY dn_detail""".format(", ".join(
			frappe.db.escape(dn_item.name)
			for dn_item in unmarked_delivery_note_items
		))
	)

	si_amounts = {si_item[0]: si_item[1] for si_item in si_amounts}

	for dn_item in unmarked_delivery_note_items:
		dn_amount = flt(dn_item.amount)
		si_amount = flt(si_amounts.get(dn_item.name))

		if dn_amount > si_amount and dn_item.base_net_total:
			outstanding_based_on_dn += ((dn_amount - si_amount)
				/ dn_item.base_net_total) * dn_item.base_grand_total

	return dict(outstanding_based_on_gle = outstanding_based_on_gle, outstanding_based_on_so = outstanding_based_on_so, outstanding_based_on_dn = outstanding_based_on_dn)

@frappe.whitelist()
def check_credit_limit(customer, company, ignore_outstanding_sales_order=False, extra_amount=0):
	credit_limit = get_credit_limit(customer, company)
	if not credit_limit:
		return

	customer_outstanding = get_customer_outstanding(customer, company, ignore_outstanding_sales_order)
	if extra_amount > 0:
		customer_outstanding += flt(extra_amount)

	# if credit_limit > 0 and flt(customer_outstanding) > credit_limit:
	return customer_outstanding


# Fetch item promos
def fetch_sales_promo_1(item_code):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p1.bought_item, p1.quantity_bought as bought_qty, p1.discount_percentage as discount, p.promo_type
            from `tabPromo Type 1` as p1
                join `tabSales Promos` as p on (p.name = p1.parent)
            where p1.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return p
    return []

def fetch_sales_promo_2(item_code):
    today = datetime.date.today()

    p = frappe.db.sql(
        f"""select p2.bought_item, p2.for_every_quantity_that_is_bought as bought_qty, p2.quantity_of_free_items_thats_given as free_qty, p.promo_type
            from `tabPromo Type 2` as p2
                join `tabSales Promos` as p on (p.name = p2.parent)
            where p2.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return p
    return []

def fetch_sales_promo_3(item_code):
    today = datetime.date.today()
    
    p = frappe.db.sql(
        f"""select p3.bought_item, p3.free_item, p3.for_every_quantity_that_is_bought as bought_qty, p3.quantity_of_free_items_thats_given as free_qty, p.promo_type
            from `tabPromo Type 3` as p3
                join `tabSales Promos` as p on (p.name = p3.parent)
            where p3.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    if len(p) > 0: return p
    return []

def fetch_sales_promo_5(item_code):
    today = datetime.date.today()
    print('fetching ineligable qty')
    p = frappe.db.sql(
        f"""select p5.bought_item, p5.for_every_quantity_that_is_bought as bought_qty, p5.quantity_of_free_items_thats_given as free_qty, p5.discount, p.promo_type
            from `tabPromo Type 5` as p5
                join `tabSales Promos` as p on (p.name = p5.parent)
            where p5.bought_item = '{item_code}' and p.start_date <= '{today}' and p.end_date >= '{today}'""",
            as_dict=1
    )

    print(p)

    if len(p) > 0: return p
    return []

@frappe.whitelist()
def sales_promo_detail_container(item_code):
    p1 = fetch_sales_promo_1(item_code)
    p2 = fetch_sales_promo_2(item_code)
    p3 = fetch_sales_promo_3(item_code)
    p5 = fetch_sales_promo_5(item_code)
    
    promo = {
        'promo_table_for_quantityamount_based_discount': p1,
        'promos_table_of_same_item': p2,
        'promos_table_of_different_items': p3,
        'free_item_for_eligible_quantity': p5
    }

    return promo

# Sales invoice delivery trip
# @frappe.whitelist()
def fetch_customer_address(customer):
    address_list = frappe.db.get_list('Address', 'name')
    print(address_list)
    for x in address_list:
        a = frappe.get_doc('Address', x.get('name')).as_dict()
        if a.get('links'):
            if len(a['links']) > 0:
                for l in a['links']:
                    if l.get('link_name') == customer: return dict(valid = True, name = x.get('name'))
    frappe.throw("Error No address for given customer")
    return dict(valid = False)


def fetch_driver_vehicle_info():
    d = frappe.db.sql(
        """select default_driver, default_vehicle
        from `tabFulfillment Settings Details V1`""", as_dict=1
    )

    print(d)

    return d[0]['default_driver'], d[0]['default_vehicle']


@frappe.whitelist()
def generate_delivery_trip(delivery_notes):
    delivery_notes = json.loads(delivery_notes)

    driver, vehicle = fetch_driver_vehicle_info()

    today = datetime.datetime.now()
    
    outerJson = {
		'doctype': 'Delivery Trip',
		'naming_series': 'DT-DL-',
        'driver': driver,
        'vehicle': vehicle,
        'departure_time': today,
		'delivery_stops': []
	}

    for x in delivery_notes:
        address = fetch_customer_address(x['customer'])
        if address.get('valid'):
            innerJson = {
                'doctype': 'Delivery Stop',
                'customer': x['customer'],
                'address': address.get('name'),
                'delivery_note': x['delivery_note'],
                'invoice_no': x['invoice_no'],
                'grand_total': x['grand_total']
            }

            outerJson['delivery_stops'].append(innerJson)
    
    doc = frappe.new_doc('Delivery Trip')
    doc.update(outerJson)
    doc.save()

    return doc.name

@frappe.whitelist()
def generate_delivery_note(sales_invoice):
    sales_order_name = frappe.get_doc('Sales Invoice', sales_invoice).as_dict()['items'][0]['sales_order']
    sales_order_details = frappe.get_doc('Sales Order', sales_order_name).as_dict()
    sales_invoice_details = frappe.get_doc('Sales Invoice', sales_invoice)
    print('sales item name', sales_invoice_details.items[0].name)
    
    for t in sales_order_details['taxes']:
        t.pop('name')
        t.pop('owner')
        t.pop('creation')
        t.pop('modified')
        t.pop('modified_by')
        t.pop('parent')
        t.pop('parentfield')
        t.pop('parenttype')
        t.pop('idx')
        t.pop('docstatus')
        t.pop('row_id')

    outerJson_delivery_note = {
        'doctype': 'Delivery Note',
		'naming_series': 'DL-DL-',
		'customer': sales_order_details.get('customer'),
        'invoice_no': sales_invoice,
		'items': [],
		'taxes': sales_order_details.get('taxes')
    }
    
    for i, s in enumerate(sales_order_details['items']):
        innerS = {
            'doctype': 'Delivery Note Item',
            'item_code': s.get('item_code'),
            'qty': s.get('qty'),
            'stock_uom': s.get('stock_uom'),
            'rate': s.get('rate'),
            'warehouse': s.get('warehouse'),
            'against_sales_order': s.get('parent'),
            'so_detail': s.get('name'),
            'against_sales_invoice': sales_invoice,
            'si_detail': sales_invoice_details.as_dict()['items'][i]['name'],
            'batch_no': s.get('pch_batch_no')
        }

        if s.get('rate', 0) == 0:
            innerS['is_free_item'] = 1

        outerJson_delivery_note['items'].append(innerS)
    
    if sales_invoice_details.update_stock == 1:
        sales_invoice_details.update_stock = 0
        sales_invoice_details.save()

    doc = frappe.new_doc('Delivery Note')
    doc.update(outerJson_delivery_note)
    doc.save()
    doc.submit()
    
    for i, s in enumerate(sales_invoice_details.items):
        s.delivery_note = doc.name
        s.dn_detail = doc.as_dict()['items'][i]['name']
    sales_invoice_details.save()

    return dict(customer = sales_order_details.get('customer'), delivery_note = doc.name, invoice_no = sales_invoice, grand_total = doc.grand_total)

def fetch_unpaid_sales_invoices(customer):
    l = frappe.db.get_list('Sales Invoice', filters=[{'customer': customer}, {'docstatus': ['<', '2']}, {'outstanding_amount': ['>', '0']}], fields=['name', 'outstanding_amount'])
    return l

@frappe.whitelist()
def get_user_collection_trip():
    user = frappe.session.user

    return user

def fetch_si_collection_trip(customer):
    s = frappe.db.sql(
        f"""select invoice_no
        from `tabCollection Trip Item`
        where customer = '{customer}' and docstatus < 2""", as_dict=1
    )

    if len(s) > 0: return [x['invoice_no'] for x in s]
    return []

@frappe.whitelist()
def generate_collection_trip(name):
    delivery_trip_items = frappe.get_doc('Delivery Trip', name).as_dict().delivery_stops

    outerJson = {
        'doctype': 'Collection Trip',
        'delivery_trip_no': name,
        'details': []
    }

    handled_customer = []

    for x in delivery_trip_items:
        customer_name = frappe.db.get_value('Customer', {'name': x.get('customer')}, 'customer_name')
        if x.get('customer') not in handled_customer:
            handled_customer.append(x.get('customer'))
            sales_invoice_list = fetch_unpaid_sales_invoices(x.get('customer'))
            sales_invoice_collection = fetch_si_collection_trip(x.get('customer'))

            filtered_invoice = [x for x in sales_invoice_list if x.get('name') not in sales_invoice_collection]

            if filtered_invoice:
                for s in filtered_invoice:
                    innerJson = {
                        'doctype': 'Collection Trip Item',
                        'invoice_no': s.get('name'),
                        'customer': x.get('customer'),
                        'customer_name': customer_name,
                        'pending_amount': s.get('outstanding_amount')
                    }

                    outerJson['details'].append(innerJson)
    
    doc = frappe.new_doc('Collection Trip')
    doc.update(outerJson)
    doc.save()

    return dict(data = delivery_trip_items, name = doc.name)

@frappe.whitelist()
def fetch_employee_collection_trips(employee):
    t = frappe.db.sql(
        f"""select cti.name, cti.invoice_no, c.territory as customer_territory, c.customer_name as customer_name, cti.pending_amount, cti.cash_amount, cti.cheque_amount,
        cti.wire_amount, cti.total_amount, cti.cheque_reference, cti.cheque_date, cti.wire_reference, cti.wire_date
            from `tabCollection Trip Item` as cti
                join `tabCollection Trip` as ct on (ct.name = cti.parent)
                join `tabSales Invoice` as si on (si.name = cti.invoice_no)
                join `tabCustomer` as c on (c.name = si.customer)
            where ct.collection_person = '{employee}' and (ct.docstatus = 0 or (ct.docstatus = 1 and cti.pending_amount > cti.total_amount))""", as_dict=1
    )

    if not t: []
    if len(t) > 0: return t
    return []

@frappe.whitelist()
def update_employee_collection_trips(payload):
    payload = json.loads(payload)
    updated_ct = []

    for x in payload:
        doc = frappe.get_doc('Collection Trip Item', x.get('name'))
        doc.cash_amount = x.get('cash_amount', 0)
        doc.cheque_amount = x.get('cheque_amount', 0)
        doc.wire_amount = x.get('wire_amount', 0)
        doc.total_amount = x.get('total_amount', 0)
        doc.cheque_reference = x.get('cheque_reference')
        doc.cheque_date = x.get('cheque_date')
        doc.wire_reference = x.get('wire_reference')
        doc.wire_date = x.get('wire_date')

        doc.save()

        updated_ct.append(doc.name)
    
    return dict(updated_names = updated_ct, updated_len = len(updated_ct))

# Print Format
@frappe.whitelist()
def check_promo(item_code, invoice):
	today = datetime.date.today()
	qty = frappe.db.sql(
		f"""select sum(qty) as total from `tabSales Invoice Item` where name = '{invoice[0].name}'""", as_dict=1
	)
	print('qty', qty)

	promo_5 = frappe.db.sql(
		f"""select p5.discount
		from `tabPromo Type 5` as p5
			join `tabSales Promos` as p on (p.name = p5.parent)
		where p5.bought_item = '{item_code}' and p5.for_every_quantity_that_is_bought <= '{qty[0]['total']}' and p.start_date <= '{today}' and p.end_date >= '{today}'
		order by p5.for_every_quantity_that_is_bought DESC""", as_dict=1
	)
	print('type 5', promo_5)
	if len(promo_5) > 0: return promo_5[0]['discount']
	return 0


@frappe.whitelist()
def get_dl_no(customer):
	dl = frappe.db.get_list('Drug License', filters=[{'parent': customer}], fields=['drug_license_no'])
	try:
		s = ", ".join(x['drug_license_no'] for x in dl)
	except:
		s = ""
	return s

@frappe.whitelist()
def get_unpaid_amount(customer):
	response = get_balance_on(party_type='Customer', party=customer)
	return response

# Custom button sales order -> process order
def fetch_customer_type(so_name):
    customer = frappe.db.sql(
        f"""SELECT customer FROM `tabSales Order` WHERE name = '{so_name}'""",
        as_dict=True
    )
    customer_group = frappe.db.sql(
        f"""SELECT customer_group FROM `tabCustomer` WHERE name = '{customer[0]["customer"]}'""",
        as_dict=True
    )
    customer_type = frappe.db.sql(
        f"""SELECT pch_customer_type FROM `tabCustomer Group` WHERE name = '{customer_group[0]["customer_group"]}'""",
        as_dict=True
    )

    return customer_type[0]["pch_customer_type"]

def fetch_fulfillment_settings(company, customer=""):
    fs_name = frappe.db.sql(
        f"""SELECT name, expiry_date_limit FROM `tabFulfillment Settings V1` WHERE company = '{company}'""",
        as_dict=True
    )

    customer_expiry = frappe.db.get_value('Customer', customer, 'pch_expiry_date_limit', as_dict=1)

    if fs_name:
        settings = frappe.db.sql(
            f"""SELECT retail_primary_warehouse, retail_bulk_warehouse, hospital_warehouse, institutional_warehouse, qc_and_dispatch, free_warehouse
            FROM `tabFulfillment Settings Details V1` WHERE parent = '{fs_name[0]["name"]}'""", as_dict=True
        )
        if customer_expiry:
            if customer_expiry.get('pch_expiry_date_limit', 0) > 0: settings[0]["expiry_date_limit"] = customer_expiry["pch_expiry_date_limit"]
            else: settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
        else: settings[0]["expiry_date_limit"] = fs_name[0]["expiry_date_limit"]
    else:
        settings = [None]
    return settings[0]

def get_customer(so_name):
    customer = frappe.db.sql(
        f"""select customer from `tabSales Order` where name = '{so_name}'""", as_dict=1
    )
    return customer[0].customer

def fetch_item_list(so_name):
    item_list = frappe.db.sql(
        f"""SELECT item_code, qty, warehouse, name as so_detail, promo_type  FROM `tabSales Order Item` WHERE parent = '{so_name}'""",
        as_dict=True
    )

    return item_list

def fetch_stock_details(customer_type, sales_list, settings):
    items = [data["item_code"] for data in sales_list]
    items = re.sub(r',\)$', ')', str(tuple(items)))

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]

    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))
    
    if settings["retail_primary_warehouse"] >= settings["retail_bulk_warehouse"] :
        warehouse_order = "DESC"
    else:
        warehouse_order = "ASC"
    
    print("QUERY", 
    f"""
        select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabStock Ledger Entry`.item_code in {items} AND warehouse in {warehouse}
            and `tabStock Ledger Entry`.is_cancelled = 0
        group by batch_id, warehouse
        order by warehouse {warehouse_order}, expiry_date ASC
    """)

    stock_data_batch = frappe.db.sql(f"""
        select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabStock Ledger Entry`.item_code in {items} AND warehouse in {warehouse}
            and `tabStock Ledger Entry`.is_cancelled = 0
        group by batch_id, warehouse
        order by warehouse {warehouse_order}, expiry_date ASC
    """, as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code in {items} and warehouse in {warehouse} and (batch_no is null or batch_no = '')
        group by item_code, warehouse
        order by warehouse {warehouse_order}""",
        as_dict=True
    )
    
    for data in stock_data_batchless:
        if data.get("actual_qty") is None: continue
        stock_data_batch.append(data)

    return stock_data_batch

def fetch_free_stock_detail(free_list, free_warehouse):
    print("Free warehouse fetch!")
    items = [data["item_code"] for data in free_list]

    if not (len(items) > 0): return []

    items = re.sub(r',\)$', ')', str(tuple(items)))

    stock_data_batch = frappe.db.sql(f"""
        select batch_id, `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
        from `tabBatch`
            join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
        where `tabStock Ledger Entry`.item_code in {items} and warehouse = '{free_warehouse}'
            and `tabStock Ledger Entry`.is_cancelled = 0
        group by batch_id, warehouse
        order by expiry_date ASC
    """, as_dict=True)
    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code in {items} and warehouse = '{free_warehouse}' and (batch_no is null or batch_no = '')
        group by item_code, warehouse
        """,
        as_dict=True
    )
    
    for data in stock_data_batchless:
        if data.get("actual_qty") is None: continue
        stock_data_batch.append(data)
    
    return stock_data_batch

def fetch_pick_put_list_data(customer_type, sales_list, settings):
    items = [data["item_code"] for data in sales_list]
    items = re.sub(r',\)$', ')', str(tuple(items)))

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"], settings["free_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"], settings["free_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"], settings["free_warehouse"]]
    
    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))

    pick_put_list_stock = frappe.db.sql(
        f"""select ppli.item as item_code, ppli.batch, ppli.batch_picked, ppli.warehouse, ppli.quantity_to_be_picked, ppli.quantity_picked, ppli.warehouse
        from `tabPick Put List Items` as ppli
            join `tabPick Put List` as ppl on (ppli.parent = ppl.name)
        where ppli.item in {items} and ppl.pick_list_stage != 'Invoiced' and ppl.pick_list_stage != 'Ready for Picking' and ppl.docstatus < 2 and ppli.warehouse in {warehouse}""",
        as_dict=1
    )

    return pick_put_list_stock

def update_stock_detail_with_picked_stock(stock_data, free_data, picked_data):
    struct_pick = {}

    for p in picked_data:
        if p["quantity_picked"] is not None:
            p_qty = p["quantity_picked"]
        elif p["quantity_to_be_picked"] is not None:
            p_qty = p["quantity_to_be_picked"]
        else:
            p_qty = 0
        
        if p["batch_picked"] is not None:
            p_batch = p["batch_picked"]
        elif p["batch"] is not None:
            p_batch = p["batch"]
        else:
            p_batch = ''
        if p["warehouse"] not in struct_pick:  
            struct_pick[p["warehouse"]] = {}
            struct_pick[p["warehouse"]][p["item_code"]] = {}
            struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty  
            if p["item_code"] not in struct_pick[p["warehouse"]]:
                struct_pick[p["warehouse"]][p["item_code"]] = {}
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
            else:
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
        else:
            if p["item_code"] not in struct_pick[p["warehouse"]]:
                struct_pick[p["warehouse"]][p["item_code"]] = {}
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
            else:
                struct_pick[p["warehouse"]][p["item_code"]][p_batch] = p_qty
   
    for s in stock_data:
        try:
            if s["actual_qty"] > struct_pick[s["warehouse"]][s["item_code"]][s["batch_id"]]:
                s["actual_qty"] -= struct_pick[s["warehouse"]][s["item_code"]][s["batch_id"]]
            else:
                s["actual_qty"] = 0
        except:
            pass
    
    for f in free_data:
        try:
            if f["actual_qty"] > struct_pick[f["warehouse"]][f["item_code"]][f["batch_id"]]:
                f["actual_qty"] -= struct_pick[f["warehouse"]][f["item_code"]][f["batch_id"]]
            else:
                f["actual_qty"] = 0
        except:
            pass
    
    return stock_data, free_data

def handle_stock_data(stock_data):
    stock_map = {}
    for data in stock_data:
        if data["item_code"] not in stock_map:
            stock_map[data["item_code"]] = []
        batch = {}
        batch["batch_no"] = data["batch_id"]
        batch["warehouse"] = data["warehouse"]
        batch["stock_uom"] = data["stock_uom"]
        try:
            batch["expiry_date"] = data["expiry_date"]
        except:
            pass
        batch["actual_qty"] = data["actual_qty"]
        stock_map[data["item_code"]].append(batch) 
    return stock_map

def handle_free_data(free_data):
    stock_map = {}
    for data in free_data:
        if data["item_code"] not in stock_map:
            stock_map[data["item_code"]] = []
        batch = {}
        batch["batch_no"] = data["batch_id"]
        batch["warehouse"] = data["warehouse"]
        batch["stock_uom"] = data["stock_uom"]
        try:
            batch["expiry_date"] = data["expiry_date"]
        except:
            pass
        batch["actual_qty"] = data["actual_qty"]
        stock_map[data["item_code"]].append(batch) 
    return stock_map

def fetch_wbs_location(customer_type, sales_list, settings):
    items = [data["item_code"] for data in sales_list]
    # print(items)
    if customer_type == "Retail":
        warehouse = settings["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        warehouse = settings["hospital_warehouse"]
    elif customer_type == "Institutional":
        warehouse = settings["institutional_warehouse"]

    wbs_setting_id = frappe.db.sql(
        f"""select name, start_date from `tabWBS Settings` where warehouse = '{warehouse}' order by start_date DESC""", as_dict=True
    )
    if len(wbs_setting_id) == 0:
        return {}
    wbs_location_list = []
    for item in items:
        wbs_location = frappe.db.sql(
            f"""select item_code, `tabWBS Storage Location`.name_of_attribute_id, `tabWBS Storage Location`.name, `tabWBS Storage Location`.rarb_warehouse
            from `tabWBS Stored Items`
                join `tabWBS Storage Location`
                    on (`tabWBS Stored Items`.parent = `tabWBS Storage Location`.name)
            where item_code = '{item}' and wbs_settings_id = '{wbs_setting_id[0]["name"]}'""", as_dict=True
        )
        if len(wbs_location) > 0:
            wbs_location_list.append(wbs_location[0])
        else:
            # fetch from wbs stock balance report
            wbs_location_anyitem = frappe.db.sql(
                f"""select item_code, `tabStock Entry Detail`.creation, `tabWBS Storage Location`.name_of_attribute_id, `tabWBS Storage Location`.name, `tabWBS Storage Location`.rarb_warehouse 
                from `tabStock Entry Detail`
                    join `tabWBS Storage Location`
                        on (target_warehouse_storage_location = `tabWBS Storage Location`.name)
                where item_code = '{item}' and target_warehouse_storage_location is not null and `tabStock Entry Detail`.docstatus = 1
                order by `tabStock Entry Detail`.creation DESC""",
                as_dict=True
            )
            if len(wbs_location_anyitem) > 0:
                wbs_location_list.append(wbs_location_anyitem[0])
            

    wbs_structured = {}
    for data in wbs_location_list:
        if data["rarb_warehouse"] not in wbs_structured:
            wbs_structured[data["rarb_warehouse"]] = {}
        if data["item_code"] not in wbs_structured[data["rarb_warehouse"]]:
            wbs_structured[data["rarb_warehouse"]][data["item_code"]] = {}
        wbs_structured[data["rarb_warehouse"]][data["item_code"]]["wbs_storage_location_id"] = data["name_of_attribute_id"]
        wbs_structured[data["rarb_warehouse"]][data["item_code"]]["wbs_storage_location"] = data["name"]

    return wbs_structured

def sales_order_handle(sales_list, stock_data, free_data, wbs_details, settings):
    today = datetime.date.today()
    pick_up_list = []
    free_pick_list = []

    for sales in sales_list:
        to_pickup = sales["qty"]
        if sales["warehouse"] != settings['free_warehouse']:
            print("Normal Data")
            if stock_data.get(sales["item_code"]) is None: continue
            for stock in stock_data[sales["item_code"]]:
                if stock["actual_qty"] == 0: continue
                try:
                    date_delta = stock["expiry_date"] - today
                    if date_delta.days < settings['expiry_date']: continue
                except:
                    pass
                pick_up = {}
                pick_up["item_code"] = sales["item_code"]
                pick_up["stock_uom"] = stock["stock_uom"]
                pick_up["warehouse"] = stock["warehouse"]
                pick_up["promo_type"] = sales["promo_type"]
                pick_up["so_detail"] = sales["so_detail"]
                try:
                    pick_up["wbs_storage_location_id"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location_id"]
                    pick_up["wbs_storage_location"] = wbs_details[stock["warehouse"]][sales["item_code"]]["wbs_storage_location"]
                except:
                    pick_up["wbs_storage_location_id"] = ''
                    pick_up["wbs_storage_location"] = ''
                if stock["actual_qty"] >= to_pickup:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = to_pickup
                    stock["actual_qty"] -= to_pickup
                    to_pickup = 0
                else:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = stock["actual_qty"]
                    to_pickup -= stock["actual_qty"]
                    stock["actual_qty"] = 0
                pick_up_list.append(pick_up)
                if to_pickup == 0: break
        else:
            if free_data.get(sales["item_code"]) is None: continue
            for stock in free_data[sales["item_code"]]:
                if stock["actual_qty"] == 0: continue
                try:
                    date_delta = stock["expiry_date"] - today
                    if date_delta.days < settings['expiry_date']: continue
                except:
                    pass
                pick_up = {}
                pick_up["item_code"] = sales["item_code"]
                pick_up["stock_uom"] = stock["stock_uom"]
                pick_up["warehouse"] = stock["warehouse"]
                pick_up["promo_type"] = sales["promo_type"]
                pick_up["so_detail"] = sales["so_detail"]
                try:
                    pick_up["wbs_storage_location_id"] = wbs_details[settings["retail_primary_warehouse"]][sales["item_code"]]["wbs_storage_location_id"]
                    pick_up["wbs_storage_location"] = wbs_details[settings["retail_primary_warehouse"]][sales["item_code"]]["wbs_storage_location"]
                except:
                    pick_up["wbs_storage_location_id"] = ''
                    pick_up["wbs_storage_location"] = ''
                if stock["actual_qty"] >= to_pickup:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = to_pickup
                    stock["actual_qty"] -= to_pickup
                    to_pickup = 0
                else:
                    pick_up["batch_no"] = stock["batch_no"]
                    pick_up["qty"] = stock["actual_qty"]
                    to_pickup -= stock["actual_qty"]
                    stock["actual_qty"] = 0
                free_pick_list.append(pick_up)
                if to_pickup == 0: break
        
    return pick_up_list + free_pick_list


def fetch_item_qty_details(item_code, customer_type, settings):
    today = datetime.date.today()

    print('FETCH STOCK SETTINGS', settings)

    if customer_type == "Retail":
        warehouse = [settings["retail_primary_warehouse"], settings["retail_bulk_warehouse"]]
    elif customer_type == "Hospital":
        warehouse = [settings["hospital_warehouse"]]
    elif customer_type == "Institutional":
        warehouse = [settings["institutional_warehouse"]]

    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))
       
    stock_data_batch = frappe.db.sql(f"""
            select batch_id , `tabBatch`.stock_uom, item as item_code, expiry_date, `tabStock Ledger Entry`.warehouse as warehouse, sum(`tabStock Ledger Entry`.actual_qty) as actual_qty
            from `tabBatch`
                join `tabStock Ledger Entry` ignore index (item_code, warehouse)
                    on (`tabBatch`.batch_id = `tabStock Ledger Entry`.batch_no )
            where `tabStock Ledger Entry`.item_code = '{item_code}' AND warehouse in {warehouse}
                and `tabStock Ledger Entry`.is_cancelled = 0
            group by batch_id, warehouse
            order by expiry_date ASC, warehouse DESC
        """, as_dict=True)

    stock_data_batchless = frappe.db.sql(
        f"""select batch_no as batch_id, item_code, warehouse, stock_uom, sum(actual_qty) as actual_qty from `tabStock Ledger Entry`
        where item_code = '{item_code}' and warehouse in {warehouse} and (batch_no is null or batch_no = '')
        group by item_code, warehouse""",
        as_dict=True
    )

    sales_data = frappe.db.sql(
        f"""select sum(soi.qty - soi.delivered_qty) as pending_qty
        from `tabSales Order Item` as soi
            join `tabSales Order` as so on (soi.parent = so.name)
        where soi.docstatus < 2 and soi.item_code = '{item_code}' and soi.warehouse in {warehouse} and so.pch_picking_status != ''""", as_dict=True
    )
    
    print("expiry limit", settings["expiry_date_limit"])
    batch_total = 0
    for batch_info in stock_data_batch:
        if batch_info["expiry_date"] is not None: 
            date_delta = batch_info["expiry_date"] - today
            if date_delta.days < settings["expiry_date_limit"]: continue
            print("batch expiry", date_delta.days, "qty", batch_info["actual_qty"])
        batch_total += batch_info["actual_qty"]

    batchless_total = sum(data["actual_qty"] for data in stock_data_batchless)
    print("batch", batch_total)
    print("batchless", batchless_total)
    try:
        available_qty = batch_total + batchless_total - sales_data[0]["pending_qty"]
    except:
        available_qty = batch_total + batchless_total
        sales_data[0]["pending_qty"] = 0

    if available_qty < 0:
        available_qty = 0

    return dict(available_qty = available_qty, sales_qty = sales_data[0]["pending_qty"])

@frappe.whitelist()
def item_qty_available_container(item_code, company):
    fulfillment_settings = fetch_fulfillment_settings(company)
    data = fetch_item_qty_details(item_code, "Retail", fulfillment_settings)

    return data


def item_list_container(so_name, company):
    customer = get_customer(so_name)
    customer_type = fetch_customer_type(so_name)
    fulfillment_settings = fetch_fulfillment_settings(company, customer)
    print("Settings", fulfillment_settings)

    if customer_type == "Retail":
        warehouse = fulfillment_settings["retail_primary_warehouse"]
    elif customer_type == "Hospital":
        warehouse = fulfillment_settings["hospital_warehouse"]
    elif customer_type == "Institutional":
        warehouse = fulfillment_settings["institutional_warehouse"]

    sales_list = fetch_item_list(so_name)
    free_list = list(filter(lambda x:x["warehouse"] == fulfillment_settings["free_warehouse"], sales_list))
    order_list = list(filter(lambda x:x["warehouse"] in warehouse, sales_list))

    stock_data = fetch_stock_details(customer_type, order_list, fulfillment_settings)
    free_data = fetch_free_stock_detail(free_list, fulfillment_settings["free_warehouse"])
    p_stock = fetch_pick_put_list_data(customer_type, order_list, fulfillment_settings)

    stock_data, free_data = update_stock_detail_with_picked_stock(stock_data, free_data, p_stock)

    handled_data = handle_stock_data(stock_data)
    handled_free = handle_free_data(free_data)

    wbs_details = fetch_wbs_location(customer_type, sales_list, fulfillment_settings)
    pick_put_list = sales_order_handle(sales_list, handled_data, handled_free, wbs_details, fulfillment_settings)
    return pick_put_list


def fetch_customer_detail(so_name):
    customer = frappe.db.get_value('Sales Order', so_name, 'customer', as_dict=1)
    customer_name = frappe.db.get_value('Customer', customer['customer'], 'customer_name', as_dict=1)
    territory = frappe.db.get_value('Customer', customer['customer'], 'territory', as_dict=1)

    return dict(customer = customer['customer'], customer_name = customer_name['customer_name'], territory = territory['territory'])


@frappe.whitelist()
def pick_put_list_container(so_name, company):
    customer = fetch_customer_detail(so_name)

    outerJson_ppl = {
		"doctype": "Pick Put List",
		"type": "Pick",
		"pick_list_stage": "Ready for Picking",
		"sales_order": so_name,
        "customer": customer['customer'],
        "customer_name": customer['customer_name'],
        "territory": customer['territory'],
		"item_list": []
	}

    pick_put_list = item_list_container(so_name, company)

    for x in pick_put_list:
        innerJson = {
            "doctype": "Pick Put List Items",
			"item": x.get("item_code", ""),
            "uom": x.get("stock_uom", ""),
			"batch": x.get("batch_no", ""),
			"wbs_storage_location": x.get("wbs_storage_location_id", ""),
			"warehouse": x.get("warehouse", ""),
			"quantity_to_be_picked": x.get("qty", 0),
			"promo_type": x.get("promo_type", ""),
			"so_detail": x.get("so_detail", ""),
        }

        outerJson_ppl["item_list"].append(innerJson)
    
    doc_ppl = frappe.new_doc("Pick Put List")
    doc_ppl.update(outerJson_ppl)
    doc_ppl.save()

    return dict(so_name = so_name, ppl_name = doc_ppl.name)


@frappe.whitelist()
def fetch_pick_put_list_items(name):
    items = frappe.get_doc('Pick Put List', name).as_dict().get('item_list', [])
    if len(items) == 0: frappe.msgprint('NO ITEMS FOUND ERROR')
    return items


def update_batch_price(item):
	print(item.get('batch_no'))

	batch_name = frappe.db.sql(
		f"""select name from `tabBatch` where batch_id = '{item.get('batch_no')}' and item = '{item.get('item_code')}'""",
		as_dict=1
	)
	if len(batch_name) > 0:
		batch = frappe.get_doc('Batch', batch_name[0])
		print(batch.as_dict())
		batch.pch_mrp = item.get('pch_mrp')
		batch.pch_ptr = item.get('pch_ptr')
		batch.pch_pts = item.get('pch_pts')

		batch.save()

def create_batchless_price(item):
	p = frappe.db.sql(
		f"""select name from `tabRate Contract` where selling_price = 1""", as_dict=1
	)

	if len(p) > 0:
		selling = frappe.get_doc("Rate Contract", p[0]["name"])
		selling.append("item", {
			"item": item.get('item_code'),
			"batched_item": "No",
			"selling_price_for_customer": item.get('pch_ptr'),
			"mrp": item.get('pch_mrp'),
			"pts": item.get('pch_pts'),
			"discount_percentage_for_customer_from_mrp": 0
		})
		
		selling.save()

def update_batchless_price(item):
	print("*"*100)
	print("updating batchless item")
	rc = frappe.db.sql(
		f"""select rci.name, rci.parent
		from `tabRate Contract Item` as rci
			join `tabRate Contract` as rc on (rci.parent = rc.name)
		where rci.item = '{item.get('item_code')}' and rc.selling_price = 1""",
		as_dict=1
	)

	if len(rc) > 0:
		print("updating batchless price")
		selling = frappe.get_doc("Rate Contract Item", rc[0]["name"])
		selling.selling_price_for_customer = item.get('pch_ptr')
		selling.mrp = item.get('pch_mrp')
		selling.pts = item.get('pch_pts')

		selling.save()
	else :
		create_batchless_price(item)

# Purchase receipt
@frappe.whitelist()
def update_price_list_batch(items):
	print("-"*100)
	print("update price")
	items = json.loads(items)
	items = list(filter(lambda x: x.get('pch_fields') == 1, items))
	for i in items:
		if i.get('pch_mrp') == 0 or i.get('pch_ptr') == 0 or i.get('pch_pts') == 0: continue
		if i.get('batch_no') == "" or i.get('batch_no') is None: update_batchless_price(i)
		else: update_batch_price(i)
	return dict(items = items)

def create_prestock_transfer(items, name):
	today = datetime.date.today()
	doc_name = ""
	outerJson = {
		"doctype": "Pre_Stock Transfer",
		"date": today,
		"purchase_receipt_no": name,
		"items": []
	}

	for i in items:
		innerJson = {
			"doctype": "Pre_Stock Transfer Items",
			"item_code": i.get('item_code'),
			"item_name": i.get('item_name'),
			"batch": i.get('batch_no'),
			"quantity": i.get('qty'),
			"rate": i.get('rate'),
			"source_warehouse": i.get('warehouse')
		}
		outerJson['items'].append(innerJson)
	
	if len(outerJson['items']) > 0:
		doc = frappe.new_doc("Pre_Stock Transfer")
		doc.update(outerJson)
		doc.save()
		doc_name = doc.name
	
	return dict(name = doc_name)

@frappe.whitelist()
def generate_prestock_transfer(items, name):
	items = json.loads(items)
	n = create_prestock_transfer(items, name)
	return n

@frappe.whitelist()
def check_customer_state_test():
    l = []

    address = frappe.db.get_list('Address')
    for a in address:
        doc = frappe.get_doc('Address', a['name']).as_dict()
        l.append(doc)
    
    return l

@frappe.whitelist()
def update_pick_put_list_name(name, pl_name):
    doc = frappe.get_doc('Sales Order', name)
    doc.pch_pick_put_list = pl_name

    doc.save()