import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://localhost:8000"

def make_request(method, endpoint, data=None, token=None, extra_headers=None):
    url = f"{BASE_URL}{endpoint}"
    req_data = json.dumps(data).encode('utf-8') if data else None
    
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        raise Exception(f"HTTP {e.code}: {err_body}")

def run_tests():
    print("Starting End-to-End API Integration Tests...")
    results = {}
    
    try:
        # 0. AUTHENTICATION
        print("\n--- 0. Authentication ---")
        email = f"test_{int(time.time())}@example.com"
        password = "password123"
        
        # Register
        make_request("POST", "/auth/register", {
            "email": email,
            "password": password,
            "name": "Test User",
            "workspace_name": "Test Workspace",
            
        })
        
        # Login
        login_res = make_request("POST", "/auth/login", {
            "email": email,
            "password": password
        })
        token = login_res['data']['access_token']
        print("[OK] Authenticated successfully")
        
        
        # 1. WORKSPACE SETTINGS
        print("\n--- 1. Workspace Configuration ---")
        ws = make_request("GET", "/api/v1/workspaces/me", token=token)
        print("[OK] Workspace GET successful:", ws['data']['name'])
        workspace_id = ws['data']['id']
        results['Workspace'] = 'PASS'
        
        # 2. PRODUCT MASTER
        print("\n--- 2. Product Master Data ---")
        uom = make_request("POST", "/api/v1/products/uom", {"name": "Pieces", "code": "PCS", "is_base_unit": True}, token=token)
        uom_id = uom['data']['id']
        
        cat = make_request("POST", "/api/v1/products/categories", {"name": "Electronics", "code": "ELEC"}, token=token)
        cat_id = cat['data']['id']
        
        prod = make_request("POST", "/api/v1/products", {
            "name": "Test Capacitor",
            "internal_sku": f"CAP-{int(time.time())}",
            "base_uom_id": uom_id,
            "category_id": cat_id,
            "product_type": "STOCK",
            "track_inventory": True
        }, token=token)
        prod_id = prod['data']['id']
        print("[OK] Product created:", prod['data']['internal_sku'])
        results['Product Catalog'] = 'PASS'
        
        # 3. SUPPLIER MASTER
        print("\n--- 3. Supplier Master ---")
        sup = make_request("POST", "/api/v1/suppliers", {
            "name": "Acme Corp",
            "supplier_code": f"V-{int(time.time())}",
            "currency": "AED",
            "supplier_type": "DISTRIBUTOR"
        }, token=token)
        sup_id = sup['data']['id']
        print("[OK] Supplier created:", sup['data']['name'])
        results['Supplier Master'] = 'PASS'
        
        # 4. INVENTORY FOUNDATION
        print("\n--- 4. Inventory Foundation ---")
        wh = make_request("POST", "/api/v1/inventory/warehouses", {
            "name": "Main Warehouse",
            "code": f"WH1-{int(time.time())}"
        }, token=token)
        wh_id = wh['data']['id']
        print("[OK] Warehouse created:", wh['data']['name'])
        results['Inventory & Warehouses'] = 'PASS'
        
        # 5. PROCUREMENT (PR)
        print("\n--- 5. Procurement Request (PR) ---")
        pr = make_request("POST", "/api/v1/procurement/requests", {
            "source_type": "STOCK_REPLENISHMENT",
            "destination_type": "WAREHOUSE",
            "warehouse_id": wh_id,
            "priority": "NORMAL",
            "procurement_method": "DIRECT",
            "required_by_date": "2026-12-31",
            "items": [
                {
                    "product_id": prod_id,
                    "uom_id": uom_id,
                    "requested_quantity": 100
                }
            ]
        }, token=token)
        pr_id = pr['data']['id']
        print("[OK] PR created:", pr['data']['request_number'])
        results['Procurement Request'] = 'PASS'
        
        # 6. SOURCING (RFQ)
        print("\n--- 6. Request for Quotation (RFQ) ---")
        rfq = make_request("POST", "/api/v1/rfq/requests", {
            "rfq_type": "STANDARD",
            "award_mode": "SPLIT",
            "evaluation_criteria": "LOWEST_LANDED_COST",
            "deadline": "2026-12-01T00:00:00Z",
            "currency": "AED",
            "items": [
                {
                    "product_id": prod_id,
                    "uom_id": uom_id,
                    "quantity": 100,
                    "is_mandatory": True
                }
            ]
        }, token=token)
        rfq_id = rfq['data']['id']
        print("[OK] RFQ created:", rfq['data']['rfq_number'])
        results['RFQ Sourcing'] = 'PASS'
        
        # 7. PURCHASE ORDER (SPO)
        print("\n--- 7. Supplier Purchase Order (SPO) ---")
        spo = make_request("POST", "/api/v1/spo/orders", {
            "supplier_id": sup_id,
            "currency": "AED",
            "exchange_rate": 1.0,
            "expected_delivery_date": "2026-12-10",
            "items": [
                {
                    "product_id": prod_id,
                    "uom_id": uom_id,
                    "quantity": 100,
                    "unit_price": 50.0
                }
            ]
        }, token=token)
        spo_id = spo['data']['id']
        spo_item_id = spo['data']['items'][0]['id']
        print("[OK] SPO created:", spo['data']['po_number'], "| Total Amount:", spo['data']['total_amount'])
        results['Purchase Orders (SPO)'] = 'PASS'
        
        # 8. GOODS RECEIPT NOTE (GRN)
        print("\n--- 8. Goods Receipt Note (GRN) ---")
        grn = make_request("POST", "/api/v1/grn/receipts", {
            "supplier_id": sup_id,
            "spo_id": spo_id,
            "warehouse_id": wh_id,
            "receipt_date": "2026-11-01",
            "items": [
                {
                    "product_id": prod_id,
                    "spo_item_id": spo_item_id,
                    "quantity_received": 100,
                    "quantity_accepted": 90,
                    "quantity_rejected": 10
                }
            ]
        }, token=token)
        print("[OK] GRN created:", grn['data']['grn_number'])
        results['Goods Receipt (GRN)'] = 'PASS'
        
        # 9. FINANCE & INVOICING
        print("\n--- 9. Finance & Invoicing ---")
        cli = make_request("POST", "/api/v1/clients", {
            "name": "Test Client LLC",
            "email": "test@client.com"
        }, token=token)
        cli_id = cli['data']['id']
        
        inv = make_request("POST", "/api/v1/invoices", {
            "client_id": cli_id,
            "issue_date": "2026-08-01",
            "due_date": "2026-08-30",
            "items": [
                {
                    "description": "Consulting Services",
                    "quantity": 1,
                    "unit_price": 5000
                }
            ]
        }, token=token)
        inv_id = inv['data']['id']
        print("[OK] Invoice created:", inv['data']['invoice_number'])
        
        # Record Payment (PDC)
        pay = make_request("POST", f"/api/v1/invoices/{inv_id}/payments", extra_headers={"Idempotency-Key": "test-key-123"}, data={
            "payment_method": "PDC",
            "amount": 2500,
            "payment_date": "2026-08-05",
            "reference_number": "CHEQ-999",
            "pdc_date": "2026-09-01"
        }, token=token)
        print("[OK] Payment (PDC) recorded.")
        results['Invoices & Payments'] = 'PASS'
        
        # 10. DASHBOARD STATS
        print("\n--- 10. Dashboard Analytics ---")
        stats = make_request("GET", "/api/v1/dashboard/stats", token=token)
        print("[OK] Dashboard Stats:", stats['data'])
        results['Dashboard Analytics'] = 'PASS'
        
    except Exception as e:
        print("\n[FAIL] TEST FAILED:", str(e))
        results['CURRENT_STEP'] = f'FAIL - {str(e)}'

    print("\n\n" + "="*40)
    print("E2E TEST SUMMARY REPORT")
    print("="*40)
    for module, status in results.items():
        icon = "[OK]" if status == 'PASS' else "[FAIL]"
        print(f"{icon} {module.ljust(25)} : {status}")

if __name__ == "__main__":
    run_tests()
