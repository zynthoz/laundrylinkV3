import sqlite3
import argparse
import os
import shutil
import random
import datetime
from datetime import timedelta
import uuid
import hashlib
import sys

# Add current directory to path to allow importing from database
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from database import init_db
except ImportError:
    init_db = None

DB_PATH = os.path.join(os.path.dirname(__file__), 'laundrylink.db')
BACKUP_PATH = f"{DB_PATH}.before-seed"

FILIPINO_FIRST_NAMES = ["Juan", "Maria", "Jose", "Pedro", "Lourdes", "Teresita", "Antonio", "Carmelita", "Manuel", "Rosario", "Mark", "Grace", "Reynaldo", "Marites", "Ronaldo", "Jonalyn", "Ramon", "Analyn", "Eduardo", "Evelyn"]
FILIPINO_LAST_NAMES = ["Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Garcia", "Mendoza", "Torres", "Tomas", "Aquino", "Villanueva", "Perez", "Ramos", "Castro", "Flores", "Dela Cruz", "Gonzales", "Lopez", "Navarro", "Rivera"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pin(pin):
    return hashlib.sha256(str(pin).encode("utf-8")).hexdigest()

def backup_db():
    if os.path.exists(DB_PATH):
        print(f"Creating backup at {BACKUP_PATH}")
        shutil.copy2(DB_PATH, BACKUP_PATH)

def restore_db():
    if os.path.exists(BACKUP_PATH):
        print(f"Restoring database from {BACKUP_PATH}")
        shutil.copy2(BACKUP_PATH, DB_PATH)
        print("Restore complete.")
    else:
        print(f"No backup found at {BACKUP_PATH}")

def wipe_data():
    print("Wiping dummy data (transactions, shift_sessions, customers, stock_movements, manual_expenses)...")
    conn = get_db()
    cursor = conn.cursor()
    tables_to_clear = [
        'transactions', 'transaction_items', 'stock_movements',
        'shift_sessions', 'customers', 'manual_expenses', 'post_cycle_payment_logs'
    ]
    for table in tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass
    
    # Update products stock to 100 for a fresh start
    try:
        cursor.execute("UPDATE products SET stock_on_hand = 100")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()
    print("Wipe complete.")

def seed_data():
    # Ensure database migrations are run
    if init_db:
        print("Running database migrations/initialization...")
        init_db()

    print("Seeding database with dummy data...")
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Setup Base Data (Employees, Products, Services)
    print("Setting up base data...")
    
    # Add default admin employee if none exists
    cursor.execute("SELECT * FROM employees WHERE display_name = 'admin'")
    if not cursor.fetchone():
         cursor.execute("""
            INSERT INTO employees (id, display_name, pin_hash, is_active, created_at, updated_at) 
            VALUES (?, ?, ?, 1, ?, ?)
         """, (str(uuid.uuid4()), 'admin', hash_pin('1234'), now_str, now_str))
    
    cursor.execute("SELECT * FROM employees WHERE display_name LIKE 'staff%'")
    staff_employees = cursor.fetchall()
    if not staff_employees:
        cursor.execute("""
            INSERT INTO employees (id, display_name, pin_hash, is_active, created_at, updated_at) 
            VALUES (?, ?, ?, 1, ?, ?)
        """, (str(uuid.uuid4()), 'staff1', hash_pin('1111'), now_str, now_str))
        cursor.execute("""
            INSERT INTO employees (id, display_name, pin_hash, is_active, created_at, updated_at) 
            VALUES (?, ?, ?, 1, ?, ?)
        """, (str(uuid.uuid4()), 'staff2', hash_pin('2222'), now_str, now_str))
        cursor.execute("SELECT * FROM employees WHERE display_name LIKE 'staff%'")
        staff_employees = cursor.fetchall()

    staff_ids = [emp['id'] for emp in staff_employees]

    # Services
    services_data = [
        ('svc-extra-wash', 'Extra Wash', 20),
        ('svc-extra-dry', 'Extra Dry', 20),
        ('svc-standard-wash', 'Standard Wash', 60),
        ('svc-standard-dry', 'Standard Dry', 70),
    ]
    for code, name, price in services_data:
        try:
            cursor.execute("""
                INSERT INTO services (id, name, unit_price, bonus_pulses, is_active, created_at, updated_at) 
                VALUES (?, ?, ?, 1, 1, ?, ?)
            """, (code, name, price, now_str, now_str))
        except sqlite3.IntegrityError:
            pass

    # Products
    products_data = [
        ('detergent_liquid', 'Liquid Detergent', 15.00, 5.00, 100),
        ('fabric_conditioner', 'Fabric Conditioner', 15.00, 5.00, 100),
        ('bleach', 'Bleach', 10.00, 3.00, 50)
    ]
    for code, name, price, cost, stock in products_data:
        try:
            cursor.execute("""
                INSERT INTO products (id, name, unit_price, unit_cost, stock_on_hand, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (code, name, price, cost, stock, now_str, now_str))
        except sqlite3.IntegrityError:
            cursor.execute("UPDATE products SET stock_on_hand = ? WHERE id = ?", (stock, code))

    # Customers
    print("Generating customers...")
    customer_ids = []
    generated_names = set()
    for i in range(50):
        c_id = str(uuid.uuid4())
        cus_code = f"CUS-20260525-{i+1:03d}"
        while True:
            name = f"{random.choice(FILIPINO_FIRST_NAMES)} {random.choice(FILIPINO_LAST_NAMES)}"
            if name.lower() not in generated_names:
                generated_names.add(name.lower())
                break
        phone = f"09{random.randint(100000000, 999999999)}"
        cursor.execute("""
            INSERT INTO customers (id, customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (c_id, cus_code, name, phone, random.randint(5, 20), random.randint(5, 20), now_str, now_str))
        customer_ids.append(c_id)

    # 2. Generate Historical Data (Shifts and Transactions)
    print("Generating 30 days of historical data...")
    now = datetime.datetime.now()
    
    # Get active machines
    cursor.execute("SELECT id FROM machines")
    machine_ids = [row['id'] for row in cursor.fetchall()]
    if not machine_ids:
        print("No machines found in database. Defaulting to washers w1-w10 and dryers d1-d9.")
        # Washers w1 to w10
        for i in range(1, 11):
            cursor.execute("""
                INSERT OR IGNORE INTO machines (id, name, type, esp32_ip, vend_price, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"w{i}", f"Washer {i}", "washer", f"192.168.1.{100+i}", 60, "IDLE"))
        # Dryers d1 to d9
        for i in range(1, 10):
            cursor.execute("""
                INSERT OR IGNORE INTO machines (id, name, type, esp32_ip, vend_price, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"d{i}", f"Dryer {i}", "dryer", f"192.168.1.{200+i}", 70, "IDLE"))
        cursor.execute("SELECT id FROM machines")
        machine_ids = [row['id'] for row in cursor.fetchall()]

    for day_offset in range(30, -1, -1):
        current_date = now - timedelta(days=day_offset)
        
        # Create 1 or 2 shifts per day
        num_shifts = random.randint(1, 2)
        for shift_num in range(num_shifts):
            staff_id = random.choice(staff_ids)
            
            shift_start = current_date.replace(hour=8 + (shift_num * 6), minute=random.randint(0, 30), second=0, microsecond=0)
            if shift_start > now:
                continue
            
            # If it's today and the last shift, leave it open
            if day_offset == 0 and shift_num == num_shifts - 1:
                shift_end = None
            else:
                shift_end = shift_start + timedelta(hours=random.uniform(5, 8))

            start_str = shift_start.strftime("%Y-%m-%d %H:%M:%S")
            end_str = shift_end.strftime("%Y-%m-%d %H:%M:%S") if shift_end else None
            shift_id = str(uuid.uuid4())

            cursor.execute("""
                INSERT INTO shift_sessions (id, employee_id, location_id, started_at, ended_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (shift_id, staff_id, 'loc_1', start_str, end_str, start_str))

            # Generate transactions for this shift
            num_transactions = random.randint(5, 15)
            shift_end_time_for_tx = shift_end or now
            
            for _ in range(num_transactions):
                tx_time = shift_start + timedelta(seconds=random.randint(0, int((shift_end_time_for_tx - shift_start).total_seconds())))
                tx_time_str = tx_time.strftime("%Y-%m-%d %H:%M:%S")
                
                customer_id = random.choice(customer_ids)
                
                total_amount = 0.0
                product_total = 0.0
                service_total = 0.0
                payment_method = random.choices(['cash', 'gcash'], weights=[0.7, 0.3])[0]

                machine_id = random.choice(machine_ids)
                
                # Insert Transaction
                tx_id = str(uuid.uuid4())
                
                # Transaction Items
                items = []
                
                # Add machine service
                service_code = 'svc-standard-wash' if 'w' in machine_id else 'svc-standard-dry'
                service_name = 'Standard Wash' if 'w' in machine_id else 'Standard Dry'
                price = 60.0 if 'w' in machine_id else 70.0
                items.append({
                    'item_type': 'service',
                    'item_id': service_code,
                    'item_name': service_name,
                    'quantity': 1,
                    'unit_price': price,
                    'subtotal': price
                })
                service_total += price
                total_amount += price
                
                # Add products randomly
                if random.random() > 0.5:
                    product_code = random.choice(['detergent_liquid', 'fabric_conditioner', 'bleach'])
                    prod_price = 15.0 if product_code != 'bleach' else 10.0
                    prod_cost = 5.0 if product_code != 'bleach' else 3.0
                    prod_name = 'Liquid Detergent' if product_code == 'detergent_liquid' else ('Fabric Conditioner' if product_code == 'fabric_conditioner' else 'Bleach')
                    qty = random.randint(1, 2)
                    subtotal = prod_price * qty
                    items.append({
                        'item_type': 'product',
                        'item_id': product_code,
                        'item_name': prod_name,
                        'quantity': qty,
                        'unit_price': prod_price,
                        'unit_cost': prod_cost,
                        'subtotal': subtotal
                    })
                    product_total += subtotal
                    total_amount += subtotal
                    
                    # Stock movement
                    cursor.execute("SELECT stock_on_hand FROM products WHERE id = ?", (product_code,))
                    stock_row = cursor.fetchone()
                    stock_before = stock_row['stock_on_hand'] if stock_row else 100
                    stock_after = stock_before - qty

                    cursor.execute("""
                        INSERT INTO stock_movements (id, product_id, transaction_id, delta_qty, stock_after, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (str(uuid.uuid4()), product_code, tx_id, -qty, stock_after, 'sale', tx_time_str))
                    
                    cursor.execute("""
                        UPDATE products SET stock_on_hand = ? WHERE id = ?
                    """, (stock_after, product_code))

                # Retrieve customer name and phone
                cursor.execute("SELECT name, phone FROM customers WHERE id = ?", (customer_id,))
                cus_row = cursor.fetchone()
                customer_name = cus_row['name']
                customer_phone = cus_row['phone']

                paid_by_gcash = 1 if payment_method == 'gcash' else 0
                gcash_amount = int(total_amount) if payment_method == 'gcash' else 0

                cursor.execute("""
                    INSERT INTO transactions (
                        id, machine_id, amount, status, started_at, ended_at, synced,
                        employee_id, shift_id, product_total, service_total, request_id,
                        customer_id, customer_name, customer_phone, paid_by_gcash, gcash_amount
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx_id, machine_id, int(total_amount), 'completed', tx_time_str, tx_time_str,
                    staff_id, shift_id, int(product_total), int(service_total), tx_id,
                    customer_id, customer_name, customer_phone, paid_by_gcash, gcash_amount
                ))

                for item in items:
                    cursor.execute("""
                        INSERT INTO transaction_items (
                            id, transaction_id, item_type, item_id, item_name, 
                            unit_price, quantity, line_total, created_at, unit_cost, line_cost
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(uuid.uuid4()), tx_id, item['item_type'], item['item_id'], item['item_name'],
                        int(item['unit_price']), item['quantity'], int(item['subtotal']), tx_time_str,
                        int(item.get('unit_cost', 0)), int(item.get('unit_cost', 0) * item['quantity'])
                    ))
            
            # Generate random expense for this shift
            if random.random() > 0.4:
                expense_id = str(uuid.uuid4())
                amount = random.randint(50, 300)
                note = random.choice(["Store supplies", "Cleaning rags", "Drinking water", "Snacks for staff", "Light bulb replacement"])
                cursor.execute("""
                    INSERT INTO manual_expenses (id, amount, note, expense_at, shift_id, employee_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (expense_id, amount, note, tx_time_str, shift_id, staff_id, tx_time_str))

    conn.commit()
    conn.close()
    print("Seeding complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed or Wipe Dummy Data for LaundryLink V2")
    parser.add_argument('--wipe', action='store_true', help="Wipe generated dummy data")
    parser.add_argument('--restore', action='store_true', help="Restore database from pre-seed backup")
    
    args = parser.parse_args()

    if args.restore:
        restore_db()
    elif args.wipe:
        wipe_data()
    else:
        backup_db()
        wipe_data() # Wipe first to avoid duplicates
        seed_data()
