import psycopg2
from psycopg2 import sql

# Connect to PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="invoicesaas",
    user="postgres",
    password="hamza"
)

cur = conn.cursor()

print("=== Test 11: Database CHECK Constraints ===\n")

# First, let's get a valid workspace_id and client_id
cur.execute("SELECT id FROM workspaces LIMIT 1;")
workspace = cur.fetchone()
if not workspace:
    print("❌ No workspace found. Please register a user first.")
    conn.close()
    exit(1)

workspace_id = workspace[0]
print(f"Using workspace_id: {workspace_id}")

# Create a test client
import uuid
client_id = str(uuid.uuid4())
cur.execute("""
    INSERT INTO clients (id, workspace_id, name, email, created_at, updated_at)
    VALUES (%s, %s, 'Test Client', 'test@client.com', NOW(), NOW())
    RETURNING id;
""", (client_id, workspace_id))
client_id = cur.fetchone()[0]
conn.commit()
print(f"Created test client: {client_id}")

# Test 1: Try to insert invoice with negative subtotal
print("\n1. Testing negative subtotal (should FAIL):")
try:
    invoice_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO invoices (id, workspace_id, client_id, invoice_number, currency, subtotal, tax_amount, total_amount, status, issue_date, due_date, created_at, updated_at)
        VALUES (%s, %s, %s, 'INV-NEG-001', 'AED', -100.00, 0.00, -100.00, 'draft', '2024-01-01', '2024-01-31', NOW(), NOW());
    """, (invoice_id, workspace_id, client_id))
    conn.commit()
    print("   ❌ FAILED - Constraint not enforced!")
except psycopg2.Error as e:
    print(f"   ✅ PASSED - Constraint enforced: {e.pgerror.strip()}")
    conn.rollback()

# Test 2: Try to insert invoice with negative tax_amount
print("\n2. Testing negative tax_amount (should FAIL):")
try:
    invoice_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO invoices (id, workspace_id, client_id, invoice_number, currency, subtotal, tax_amount, total_amount, status, issue_date, due_date, created_at, updated_at)
        VALUES (%s, %s, %s, 'INV-NEG-002', 'AED', 100.00, -10.00, 90.00, 'draft', '2024-01-01', '2024-01-31', NOW(), NOW());
    """, (invoice_id, workspace_id, client_id))
    conn.commit()
    print("   ❌ FAILED - Constraint not enforced!")
except psycopg2.Error as e:
    print(f"   ✅ PASSED - Constraint enforced: {e.pgerror.strip()}")
    conn.rollback()

# Test 3: Try to insert invoice with valid positive amounts
print("\n3. Testing valid positive amounts (should SUCCEED):")
try:
    invoice_id = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO invoices (id, workspace_id, client_id, invoice_number, currency, subtotal, tax_amount, total_amount, status, issue_date, due_date, created_at, updated_at)
        VALUES (%s, %s, %s, 'INV-VALID-001', 'AED', 100.00, 5.00, 105.00, 'draft', '2024-01-01', '2024-01-31', NOW(), NOW())
        RETURNING id;
    """, (invoice_id, workspace_id, client_id))
    invoice_id = cur.fetchone()[0]
    conn.commit()
    print(f"   ✅ PASSED - Invoice created: {invoice_id}")
except psycopg2.Error as e:
    print(f"   ❌ FAILED - Could not create valid invoice: {e.pgerror.strip()}")
    conn.rollback()

# Test 4: Try to insert invoice item with negative quantity
print("\n4. Testing negative invoice item quantity (should FAIL):")
try:
    # Get the invoice we just created
    cur.execute("SELECT id FROM invoices WHERE invoice_number = 'INV-VALID-001' LIMIT 1;")
    invoice = cur.fetchone()
    if invoice:
        item_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO invoice_items (id, invoice_id, description, quantity, unit_price, tax_rate, total_price, created_at, updated_at)
            VALUES (%s, %s, 'Test Item', -1.00, 10.00, 0.00, -10.00, NOW(), NOW());
        """, (item_id, invoice[0]))
        conn.commit()
        print("   ❌ FAILED - Constraint not enforced!")
except psycopg2.Error as e:
    print(f"   ✅ PASSED - Constraint enforced: {e.pgerror.strip()}")
    conn.rollback()

# Cleanup
print("\n4. Cleaning up test data...")
cur.execute("DELETE FROM invoice_items WHERE description = 'Test Item';")
cur.execute("DELETE FROM invoices WHERE invoice_number LIKE 'INV-NEG-%' OR invoice_number = 'INV-VALID-001';")
cur.execute("DELETE FROM clients WHERE email = 'test@client.com';")
conn.commit()
print("   ✅ Cleanup complete")

cur.close()
conn.close()

print("\n=== Test 11 Complete ===")
