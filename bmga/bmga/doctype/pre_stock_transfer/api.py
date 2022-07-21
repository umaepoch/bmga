import datetime
import json
import frappe


def fetch_fulfillment_settings():
    f = frappe.db.sql(
        """select retail_primary_warehouse as retail, retail_bulk_warehouse as bulk, hospital_warehouse as hospital, institutional_warehouse as institutional, free_warehouse as free
        from `tabFulfillment Settings Details V1`""",
        as_dict=1
    )

    if len(f) > 0:
        return f[0]


def validate_user_input_qty(data):
    for i, x in enumerate(data):
        if x.get('quantity') != x.get('retail') + x.get('bulk') + x.get('free') + x.get('hospital') + x.get('institutional'):
            return dict(valid = False, index = i + 1)
    return dict(valid = True, index = None)


def fetch_wbs_location_id(warehouse):
    today = datetime.date.today()
    wbs_settings_id = frappe.db.get_list('WBS Settings', filters=[{'warehouse': warehouse}, {'start_date': ['<', today]}], fields=['name', 'start_date'], order_by='start_date desc')
    
    if len(wbs_settings_id) == 0: return dict(valid = False, name = None)
    return dict(valid = True, name = wbs_settings_id[0]['name'], start_date = wbs_settings_id[0].get('start_date'))


def validate_qty(x):
    return x > 0


def check_if_wbs_location_is_needed(details, settings):
    user_input = []
    valid_wbs_id = False

    wbs_id = fetch_wbs_location_id(settings.get('retail'))
    if not wbs_id['valid']: return dict(valid_wbs_id = valid_wbs_id, wbs_loc_list = None)

    for x in details:
        if not validate_qty(x.get('retail')): continue
        wbs_location = frappe.db.sql(
            f"""select wsl.name_of_attribute_id, wsl.name
            from `tabWBS Stored Items` as wsi
                join `tabWBS Storage Location` as wsl on (wsi.parent = wsl.name)
            where wsi.item_code = '{x.get('item_code')}' and wsl.wbs_settings_id = '{wbs_id['name']}'""",
            as_dict=1
        )
        print("specific", wbs_location)

        if len(wbs_location) > 0: continue
        wbs_location_anyitem = frappe.db.sql(
            f"""select sed.creation, wsl.name_of_attribute_id, wsl.name
            from `tabStock Entry Detail` as sed
                join `tabWBS Storage Location` as wsl on (sed.target_warehouse_storage_location = wsl.name)
            where item_code = '{x.get('item_code')}' and sed.target_warehouse_storage_location is not null
            and sed.docstatus = 1 and sed.creation > {wbs_id['start_date']}""",
            as_dict=1
        )
        print("any", wbs_location_anyitem)
        
        if len(wbs_location_anyitem) > 0: continue
        valid_wbs_id = True
        to_add = {'item_code': x.get('item_code'), 'warehouse': settings.get('retail')}
        user_input.append(to_add)
    
    return dict(valid_wbs_id = valid_wbs_id, wbs_loc_list = user_input)


@frappe.whitelist()
def valided_stock_transfer(details):
    details = json.loads(details)
    v = validate_user_input_qty(details)
    if not v.get('valid'):
        frappe.msgprint(f'Make sure the QTY is equal to the Sum for transfers in line {v.get("index")}')
        return dict(details = details, show = False, valid = False)
    settings = fetch_fulfillment_settings()
    print(settings)
    wbs_id = check_if_wbs_location_is_needed(details, settings)
    print(wbs_id)
    if not wbs_id['valid_wbs_id']:
        return dict(details = details, show = False, valid = True)
    return dict(details = details, show = True, wbs_loc_list = wbs_id['wbs_loc_list'], valid = True)


def fetch_source_warehouse(purchase_no):
    warehouse = frappe.db.get_value('Purchase Receipt', {'name': purchase_no}, 'set_warehouse', as_dict=1)
    return warehouse.get('set_warehouse')


def handle_wbs_locations(wbs_list):
    handle = {}

    for x in wbs_list:
        if x['item_code'] not in handle:
            handle[x['item_code']] = {
                'wbs_storage_location': x['wbs_storage_location'],
                'storage_location_id': x['storage_location_id']
            }
    
    return handle


def generate_material_issue(data, warehouse):
    name = None

    if len(data) == 0: return dict(issue_name = name)

    outerJson = {
        'doctype': 'Stock Entry',
        'stock_entry_type': 'Material Issue',
        'from_warehouse': warehouse,
        'items': []
    }

    for i in data:
        innerJson = {
            'doctype': 'Stock Entry Detail',
            'item_code': i.get('item_code'),
            'batch_no': i.get('batch'),
            'qty': i.get('quantity')
        }

        outerJson['items'].append(innerJson)
    
    doc = frappe.new_doc('Stock Entry')
    doc.update(outerJson)
    doc.save()
    doc.submit()
    name = doc.name

    return dict(issue_name = name)


def retail_innerJson(i, wbs_data, warehouse, qty):
    print("rate for retail!", i.get('rate'))
    if i.get('item_code') in wbs_data:
        innerJson = {
            'doctype': 'Stock Entry Detail',
            'item_code': i.get('item_code'),
            'batch_no': i.get('batch'),
            't_warehouse': warehouse,
            'target_warehouse_storage_location': wbs_data[i['item_code']]['wbs_storage_location'],
            'target_storage_location_id': wbs_data[i['item_code']]['storage_location_id'],
            'basic_rate': i.get('rate'),
            'qty': qty
        }
    else:
        innerJson = {
            'doctype': 'Stock Entry Detail',
            'item_code': i.get('item_code'),
            'batch_no': i.get('batch'),
            't_warehouse': warehouse,
            'basic_rate': i.get('rate'),
            'qty': qty
        }
    
    return innerJson


def other_innerJson(i, warehouse, qty):
    print("rate for other!", i.get('rate'))
    innerJson = {
            'doctype': 'Stock Entry Detail',
            'item_code': i.get('item_code'),
            'batch_no': i.get('batch'),
            't_warehouse': warehouse,
            'basic_rate': i.get('rate'),
            'qty': qty
        }
    
    return innerJson


def free_innerJson(i, warehouse, qty):
    print("rate for free!", 0)
    innerJson = {
            'doctype': 'Stock Entry Detail',
            'item_code': i.get('item_code'),
            'batch_no': i.get('batch'),
            't_warehouse': warehouse,
            'basic_rate': 0,
            'qty': qty
        }
    
    return innerJson


def generate_material_receipt(data, wbs_data):
    name = None
    settings = fetch_fulfillment_settings()

    if len(data) == 0: return dict(receipt_name = name)

    outerJson = {
        'doctype': 'Stock Entry',
        'stock_entry_type': 'Material Receipt',
        'items': []
    }

    for i in data:
        if validate_qty(i.get('retail')):
            outerJson['items'].append(retail_innerJson(i, wbs_data, settings.get('retail'), i.get('retail')))
        
        if validate_qty(i.get('bulk')):
            outerJson['items'].append(other_innerJson(i, settings.get('bulk'), i.get('bulk')))
        
        if validate_qty(i.get('hospital')):
            outerJson['items'].append(other_innerJson(i, settings.get('hospital'), i.get('hospital')))
        
        if validate_qty(i.get('institutional')):
            outerJson['items'].append(other_innerJson(i, settings.get('institutional'), i.get('institutional')))
        # fuck this shit, price is not changing in my local machine. ERPNext sucks
        if validate_qty(i.get('free')):
            outerJson['items'].append(free_innerJson(i, settings.get('free'), i.get('free')))
    
    doc = frappe.new_doc('Stock Entry')
    doc.update(outerJson)
    doc.save()
    doc.submit()
    name = doc.name

    return dict(receipt_name = name)


def generate_stock_entries(data, wbs_data, s_warehouse):
    i_name = generate_material_issue(data, s_warehouse)
    r_name = generate_material_receipt(data, wbs_data)

    return {**i_name, **r_name}


def fetch_company(po):
    c = frappe.db.get_value('Purchase Receipt', {'name': po}, 'company', as_dict=1)
    return c.get('company')


def fetch_item_uom(item_code):
    u = frappe.db.get_value('Item', {'name': item_code}, 'stock_uom', as_dict=1)
    return u.get('stock_uom')


def fetch_wbs_location(item_code, wbs_id):
    wbs_location = frappe.db.sql(
            f"""select wsl.name_of_attribute_id as id, wsl.name
            from `tabWBS Stored Items` as wsi
                join `tabWBS Storage Location` as wsl on (wsi.parent = wsl.name)
            where wsi.item_code = '{item_code}' and wsl.wbs_settings_id = '{wbs_id}'""",
            as_dict=1
        )
    print("specific", wbs_location)
    if len(wbs_location) > 0: return wbs_location[0]['id']

    wbs_location_anyitem = frappe.db.sql(
        f"""select sed.creation, wsl.name_of_attribute_id as id, wsl.name
        from `tabStock Entry Detail` as sed
            join `tabWBS Storage Location` as wsl on (sed.target_warehouse_storage_location = wsl.name)
        where item_code = '{item_code}' and sed.target_warehouse_storage_location is not null
        and sed.docstatus = 1 and sed.creation > {wbs_id['start_date']}""",
        as_dict=1
    )
    print("any", wbs_location_anyitem)
    if len(wbs_location) > 0: return wbs_location_anyitem[0]['id']


def put_json(x, wbs_data, warehouse, qty):
    uom = fetch_item_uom(x.get('item_code'))
    wbs_id = fetch_wbs_location_id(warehouse)
    if wbs_id.get('valid'):
        if x.get('item_code') in wbs_data:
            location = wbs_data['item_code']
        else:
            location = fetch_wbs_location(x.get('item_code'), wbs_id.get('name'))
    else:
        location = ''
    
    print(wbs_id)
    print('location', location)
    print('uom', uom)

    innerJson = {
        'doctype': 'Put List Item',
        'item_code': x.get('item_code'),
        'uom': uom,
        'batch': x.get('batch'),
        'wbs_storage_location': location,
        'warehouse': warehouse,
        'quantity': qty
    }

    return innerJson


def generate_put_list(data, wbs_data, purchase_no):
    name = None
    settings = fetch_fulfillment_settings()
    company = fetch_company(purchase_no)

    outerJson = {
        'doctype': 'Pick Put List',
        'company': company,
        'type': 'Put',
        'pre_stock_transfer': data[0].get('parent'),
        'put_list': []
    }

    for x in data:
        print(x)
        if validate_qty(x.get('retail')):
            outerJson['put_list'].append(put_json(x, wbs_data, settings.get('retail'), x.get('retail')))
        if validate_qty(x.get('bulk')):
            outerJson['put_list'].append(put_json(x, wbs_data, settings.get('bulk'), x.get('bulk')))
        if validate_qty(x.get('free')):
            outerJson['put_list'].append(put_json(x, wbs_data, settings.get('free'), x.get('free')))
        if validate_qty(x.get('hospital')):
            outerJson['put_list'].append(put_json(x, wbs_data, settings.get('hospital'), x.get('hospital')))
        if validate_qty(x.get('institutional')):
            outerJson['put_list'].append(put_json(x, wbs_data, settings.get('institutional'), x.get('institutional')))
    
    if len(outerJson['put_list']) > 0:
        doc = frappe.new_doc('Pick Put List')
        doc.update(outerJson)
        doc.save()
        name = doc.name
    
    return dict(put_name = name)
        

@frappe.whitelist()
def generate_stock_transfer(details, wbs_locations, purchase_no):
    details = json.loads(details)
    print(details)
    wbs_locations = json.loads(wbs_locations)

    s_warehouse = fetch_source_warehouse(purchase_no)
    wbs_handled = handle_wbs_locations(wbs_locations)

    names = generate_stock_entries(details, wbs_handled, s_warehouse)
    put_name = generate_put_list(details, wbs_handled, purchase_no)

    return dict(details = details, wbs_locations = wbs_locations, purchase_no = purchase_no, names = {**names, **put_name})