import json
import frappe
import datetime
from erpnext.accounts.utils import get_balance_on
import re

# Sales invoice delivery trip
def fetch_customer_address(customer):
	a = frappe.get_doc('Customer', customer)
	print(a.as_dict())

@frappe.whitelist()
def generate_delivery_trip(delivery_notes):
	delivery_notes = json.loads(delivery_notes)

	print(delivery_notes)

	outerJson = {
		'doctype': 'Delivery Trip',
		'naming_series': 'DT-DL-',
		'delivery_stops': []
	}

	for x in delivery_notes:
		address = fetch_customer_address(x['customer'])

		innerJson = {
			'doctype': 'Delivery Stop',
			'customer': x['customer'],
			'delivery_note': x['delivery_note']
		}

		outerJson['delivery_stops'].append(innerJson)
	
	# doc = frappe.new_doc('Delivery Trip')
	# doc.update(outerJson)
	# doc.save()

	# return doc.name


@frappe.whitelist()
def generate_delivery_note(sales_invoice):
	print('hello')
	sales_order_name = frappe.get_doc('Sales Invoice', sales_invoice).as_dict()['items'][0]['sales_order']
	print(sales_order_name)
	sales_order_details = frappe.get_doc('Sales Order', sales_order_name).as_dict()
	
	for s in sales_order_details['items']:
		s.pop('pch_batch_no')
		s.pop('promo_type')

	outerJson_delivery_note = {
		'doctype': 'Delivery Note',
		'naming_series': 'DL-DL-',
		'customer': sales_order_details.get('customer'),
		'items': sales_order_details.get('items'),
		'taxes': sales_order_details.get('taxes')
	}

	doc = frappe.new_doc('Delivery Note')
	doc.update(outerJson_delivery_note)
	doc.save()

	return dict(customer = sales_order_details.get('customer'), delivery_note = doc.name)


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

def fetch_fulfillment_settings(company, customer):
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

        if customer_expiry.get('pch_expiry_date_limit', 0) > 0: settings[0]["expiry_date_limit"] = customer_expiry["pch_expiry_date_limit"]
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

    print('customer data!!!!!')
    print(customer)
    print(customer_name)
    print(territory)

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