import frappe
import json
import datetime
import re


def fetch_item_code(brand, division):
    i = frappe.db.get_list('Item',{'brand': brand, 'pch_division': division}, ['item_code', 'item_name', 'stock_uom'])
    
    if len(i) > 0:
        return dict(valid = True, items = i)
    return dict(valid = False, items = None)


def fetch_last30_sales(item_code, start_date, end_date):
    i = frappe.db.sql(
        f"""select sum(sii.qty) as qty
        from `tabSales Invoice Item` as sii
            join `tabSales Invoice` as si on (si.name = sii.parent)
        where sii.item_code = '{item_code}' and si.posting_date <= '{end_date}' and si.posting_date >= '{start_date}'""",
        as_dict=1
    )
    print(i)
    if len(i) > 0: return i[0]
    else: return dict(qty = 0)


def fetch_warehouse():
    f = frappe.db.sql(
        """select retail_primary_warehouse as retail, retail_bulk_warehouse as bulk, hospital_warehouse as hospital, institutional_warehouse as institutional, free_warehouse as free
        from `tabFulfillment Settings Details V1`""",
        as_dict=1
    )

    if len(f) > 0:
        w = []
        w.append(f[0].get('retail'))
        w.append(f[0].get('bulk'))
        w.append(f[0].get('hospital'))
        w.append(f[0].get('institutional'))
        w.append(f[0].get('free'))
        return w


def fetch_available_stock(item_code):
    warehouse = fetch_warehouse()
    warehouse = re.sub(r',\)$', ')', str(tuple(warehouse)))

    s = frappe.db.sql(
        f"""select sum(sle.actual_qty) as qty
        from `tabStock Ledger Entry` as sle
        where item_code = '{item_code}' and warehouse in {warehouse}""",
        as_dict=True
    )
    print("available", s)
    if len(s) > 0: return s[0]
    else: return dict(qty = 0)


def fetch_purchase_promo_detail(item_code):
    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt1.quantity_bought as bought_qty, pt1.discount_percentage as discount
        from `tabPurchase Promos` as pp
            join `tabPromo Type 1` as pt1 on (pt1.parent = pp.name)
        where pt1.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt2.bought_item as free_item, pt2.for_every_quantity_that_is_bought as bought_qty, pt2.quantity_of_free_items_thats_given as free_qty
        from `tabPurchase Promos` as pp
            join `tabPromo Type 2` as pt2 on (pt2.parent = pp.name)
        where pt2.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt3.free_item, pt3.for_every_quantity_that_is_bought as bought_qty, pt3.quantity_of_free_items_thats_given as free_qty
        from `tabPurchase Promos` as pp
            join `tabPromo Type 3` as pt3 on (pt3.parent = pp.name)
        where pt3.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt5.for_every_quantity_that_is_bought as bought_qty, pt5.quantity_of_free_items_thats_given as free_qty, pt5.discount 
        from `tabPurchase Promos` as pp
            join `tabPromo Type 5` as pt5 on (pt5.parent = pp.name)
        where pt5.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    return dict(valid = False, detail = {})


def fetch_sales_promo_detail(item_code):
    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt1.quantity_bought as bought_qty, pt1.discount_percentage as discount
        from `tabSales Promos` as pp
            join `tabPromo Type 1` as pt1 on (pt1.parent = pp.name)
        where pt1.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt2.bought_item as free_item, pt2.for_every_quantity_that_is_bought as bought_qty, pt2.quantity_of_free_items_thats_given as free_qty
        from `tabSales Promos` as pp
            join `tabPromo Type 2` as pt2 on (pt2.parent = pp.name)
        where pt2.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt3.free_item, pt3.for_every_quantity_that_is_bought as bought_qty, pt3.quantity_of_free_items_thats_given as free_qty
        from `tabSales Promos` as pp
            join `tabPromo Type 3` as pt3 on (pt3.parent = pp.name)
        where pt3.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    p = frappe.db.sql(
        f"""select pp.name, pp.start_date, pp.end_date, pp.promo_type, pt5.for_every_quantity_that_is_bought as bought_qty, pt5.quantity_of_free_items_thats_given as free_qty, pt5.discount 
        from `tabSales Promos` as pp
            join `tabPromo Type 5` as pt5 on (pt5.parent = pp.name)
        where pt5.bought_item = '{item_code}'""",
        as_dict=1
    )
    if len(p) > 0: return dict(valid = True, detail = p[0])

    return dict(valid = False, detail = {})


def handle_promo_detail(promo_detail):
    print("+"*50)
    print(promo_detail)
    if not promo_detail.get('valid'): return dict(text = "")
    if promo_detail['detail']['promo_type'] == 'Buy X of Item, get Y of Same Item Free' or promo_detail['detail']['promo_type'] == 'Buy X of Item, Get Y of another Item Free':
        msg = f"({promo_detail['detail'].get('free_item')})-{promo_detail['detail'].get('bought_qty')}-{promo_detail['detail'].get('free_qty')}"
        return dict(text = msg)
    if promo_detail['detail']['promo_type'] == 'Quantity Based Discount':
        msg = f"{promo_detail['detail'].get('bought_qty')}-{int(promo_detail['detail'].get('discount'))}%"
        return dict(text = msg)
    if promo_detail['detail']['promo_type'] == 'Free Item for Eligible Quantity, Discount for ineligible Quantity':
        msg = f"{promo_detail['detail'].get('bought_qty')}-{promo_detail['detail'].get('free_qty')}-{int(promo_detail['detail'].get('discount'))}%"
        return dict(text = msg)
    return dict(text = "there is a promo")


def fetch_item_for_division(brand, division):
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days = 30)

    print("Dates", start_date, end_date)

    handle = []
    for d in division:
        items = fetch_item_code(brand, d.get('division'))
        if items.get('valid'):
            for i in items.get('items'):
                last30_qty = fetch_last30_sales(i.get('item_code'), start_date, end_date)
                stock_in_hand = fetch_available_stock(i.get('item_code'))

                purchase_promo_detail = fetch_purchase_promo_detail(i.get('item_code'))
                handle_purchase_promo = handle_promo_detail(purchase_promo_detail)

                sales_promo_detail = fetch_sales_promo_detail(i.get('item_code'))
                handle_sales_promo = handle_promo_detail(sales_promo_detail)
                print("*"*50)
                print(purchase_promo_detail)

                to_add = {
                    'item_name': i.get('item_name'),
                    'uom': i.get('stock_uom'),
                    'last30_qty': last30_qty.get('qty'),
                    'stock_in_hand': stock_in_hand.get('qty'),
                    'start_date': purchase_promo_detail['detail'].get('start_date'),
                    'end_date': purchase_promo_detail['detail'].get('end_date'),
                    'purchase_promo': handle_purchase_promo.get('text', ''),
                    'sales_promo': handle_sales_promo.get('text', ''),
                    'item_code': i.get('item_code')
                }
                handle.append(to_add)
    
    return handle


@frappe.whitelist()
def fetch_items_container(brand, division):
    division = json.loads(division)

    items = fetch_item_for_division(brand, division)

    return dict(items = items)


def fetch_goods_warehouse():
    warehouse = frappe.db.get_list("Fulfillment Settings Details V1", 'goods_warehouse')
    print(warehouse)
    return warehouse[0].get('goods_warehouse')


def generate_json(supplier, data):
    name = None
    warehouse = fetch_goods_warehouse()
    outerJson = {
        'doctype': 'Purchase Receipt',
        'supplier': supplier,
        'naming_series': 'BMGAPR-',
        'set_warehouse': warehouse,
        'items': []
    }
    
    for x in data:
        if not x.get('qty_ordered', 0) > 0: continue
        print("innerjson")
        innerJson = {
            'doctype': 'Purchase Receipt Item',
            'item_code': x.get('item_code'),
            'qty': x.get('qty_ordered')
        }
        outerJson['items'].append(innerJson)

    if len(outerJson['items']) > 0:
        print("create purchase receipt")
        doc = frappe.new_doc('Purchase Receipt')
        doc.update(outerJson)
        doc.save()
        name = doc.name
    
    return name



@frappe.whitelist()
def generate_purchase_receipt(supplier, data):
    data = json.loads(data)
    name = generate_json(supplier, data)
    return dict(name = name, data = data)


def get_purchase_qty(p):
    purchase_doc = frappe.get_doc('Purchase Receipt', p.get('purchase_receipt'))
    if purchase_doc.docstatus == 2:
        return dict(to_remove = True, name = p.get('purchase_receipt'))
    
    pr = frappe.db.sql(
        f"""select sum(received_stock_qty) as received_stock_qty, item_code
        from `tabPurchase Receipt Item`
        where parent = '{p.get('purchase_receipt')}' and docstatus < 2
        group by item_code""",
        as_dict=1
    )
    
    if len(pr) > 0:
        return dict(to_remove = False, detail = pr)
    
    return dict(to_remove = True, name = p.get('purchase_receipt'))


def init_pending_qty(name):
    doc = frappe.get_doc("BMGA Purchase Order", name)
    for child in doc.get_all_children():
        if child.doctype != 'BMGA Purchase Items': continue
        child_doc = frappe.get_doc(child.doctype, child.name)
        child_doc.pending_qty = child_doc.qty_ordered
        child_doc.save()


def update_qty(received_summary, name):
    order_doc = frappe.get_doc('BMGA Purchase Order', name)
    for child in order_doc.get_all_children():
        if child.doctype != 'BMGA Purchase Items': continue
        if child.as_dict().get('item_code') not in received_summary: continue
        child_doctype = child.doctype
        child_doc = frappe.get_doc(child_doctype, child.name)

        child_doc.pending_qty = child_doc.qty_ordered - received_summary.get(child_doc.item_code)
        child_doc.save()


@frappe.whitelist()
def update_pending_qty(purchase_receipt):
    purchase_receipt = json.loads(purchase_receipt)
    to_remove = []
    received_summary = {}

    init_pending_qty(purchase_receipt[0].get('parent'))

    for p in purchase_receipt:
        validator = get_purchase_qty(p)
        if validator.get('to_remove'):
            to_remove.append(validator.get('name'))
        else:
            for x in validator.get('detail'):
                received_summary[x['item_code']] = received_summary.get(x['item_code'], 0) + x.get('received_stock_qty')
    
    print('summary', received_summary)
    update_qty(received_summary, purchase_receipt[0].get('parent'))

    return dict(to_remove = to_remove, received_summary = received_summary)