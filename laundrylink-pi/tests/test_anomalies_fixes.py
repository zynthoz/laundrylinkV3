import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta

import database as db
from app import create_app

class AnomaliesFixesTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test_laundrylink.db")
        db.init_db()

        # Add a dummy washer
        db.upsert_machine(
            "m1",
            "Washer 1",
            "washer",
            "standard",
            "127.0.0.1",
            50,
            50,
            2,
            60,
        )

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def _create_employee_and_shift(self, name="Test Employee"):
        emp_id = db.create_employee(name, "1234")
        db.end_active_shift("local", reason="test_reset")
        shift_id = db.start_shift(emp_id, "local")
        return emp_id, shift_id

    def test_job_order_creation_logs_stock_movements(self):
        product_id = db.create_product(
            "Test Detergent",
            unit_price=20,
            unit_cost=8,
            stock_on_hand=50,
            low_stock_threshold=5,
        )

        customer = db.upsert_customer("Test Customer", "09123456789")
        order = db.create_job_order(
            customer_id=customer["customer_id"],
            customer_name=customer["name"],
            customer_phone=customer.get("phone"),
            machine_id="m1",
            machine_name="Washer 1",
            machine_type="washer",
            wash_qty=1,
            dry_qty=0,
            wash_unit_price=60,
            dry_unit_price=0,
            product_qty=1,
            product_amount=20,
            items=[{
                "item_type": "product",
                "item_id": product_id,
                "item_name": "Test Detergent",
                "quantity": 1,
                "unit_price": 20,
                "unit_cost": 8
            }]
        )

        # Verify stock is decremented
        conn = db.get_connection()
        prod = conn.execute("SELECT stock_on_hand FROM products WHERE id = ?", (product_id,)).fetchone()
        self.assertEqual(prod["stock_on_hand"], 49)

        # Verify stock movement is recorded
        mv = conn.execute("SELECT * FROM stock_movements WHERE product_id = ?", (product_id,)).fetchone()
        conn.close()
        
        self.assertIsNotNone(mv)
        self.assertEqual(mv["delta_qty"], -1)
        self.assertEqual(mv["stock_after"], 49)
        self.assertEqual(mv["reason"], "job_order_creation")
        self.assertIsNone(mv["transaction_id"])

    def test_job_order_usage_copies_items_and_populates_totals(self):
        emp_id, shift_id = self._create_employee_and_shift()
        
        product_id = db.create_product(
            "Test Detergent",
            unit_price=15,
            unit_cost=5,
            stock_on_hand=50,
            low_stock_threshold=5,
        )

        customer = db.upsert_customer("Test Customer 2", "09123456788")
        order = db.create_job_order(
            customer_id=customer["customer_id"],
            customer_name=customer["name"],
            customer_phone=customer.get("phone"),
            machine_id="m1",
            machine_name="Washer 1",
            machine_type="washer",
            wash_qty=1,
            dry_qty=0,
            wash_unit_price=60,
            dry_unit_price=0,
            product_qty=2,
            product_amount=30,
            items=[{
                "item_type": "product",
                "item_id": product_id,
                "item_name": "Test Detergent",
                "quantity": 2,
                "unit_price": 15,
                "unit_cost": 5
            }]
        )

        # Start machine using this Job Order
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-jo-use-test",
                "customer": {"name": "Test Customer 2", "phone": "09123456788"},
                "job_order_id": order["id"],
            },
        )
        self.assertEqual(resp.status_code, 200)

        # Retrieve resulting transaction
        tx = db.get_transaction_by_request_id("req-jo-use-test")
        self.assertIsNotNone(tx)
        
        # Verify washer transaction is recorded at its base price and has no products/services
        self.assertEqual(int(tx.get("product_total") or 0), 0)
        self.assertEqual(int(tx.get("service_total") or 0), 0)
        self.assertEqual(int(tx.get("amount") or 0), 60) # 60 wash only, no variation

        # Find the addon transaction for this job order
        conn = db.get_connection()
        addon_tx_row = conn.execute("SELECT * FROM transactions WHERE job_order_id = ? AND machine_id = 'post-cycle-addons'", (order["id"],)).fetchone()
        self.assertIsNotNone(addon_tx_row)
        addon_tx = dict(addon_tx_row)
        
        # Verify the addons transaction contains the products
        self.assertEqual(int(addon_tx.get("product_total") or 0), 30)
        self.assertEqual(int(addon_tx.get("service_total") or 0), 0)
        self.assertEqual(int(addon_tx.get("amount") or 0), 30) # P30 products

        # Verify transaction_items are inserted for the addon transaction
        items = conn.execute("SELECT * FROM transaction_items WHERE transaction_id = ?", (addon_tx["id"],)).fetchall()
        
        # Verify no double stock decrement
        prod = conn.execute("SELECT stock_on_hand FROM products WHERE id = ?", (product_id,)).fetchone()
        self.assertEqual(prod["stock_on_hand"], 48) # 50 - 2 = 48 (not 46)

        # Verify no extra stock movement log on use (should only have the job_order_creation one)
        mvs = conn.execute("SELECT * FROM stock_movements WHERE product_id = ?", (product_id,)).fetchall()
        conn.close()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_name"], "Test Detergent")
        self.assertEqual(items[0]["quantity"], 2)
        self.assertEqual(items[0]["line_total"], 30)

        self.assertEqual(len(mvs), 1)
        self.assertEqual(mvs[0]["reason"], "job_order_creation")

    def test_direct_activation_updates_customer_order_count(self):
        emp_id, shift_id = self._create_employee_and_shift()
        
        # Create registered customer
        customer = db.upsert_customer("Registered Customer", "09999999999")
        self.assertEqual(customer["wash_order_count"], 0)

        # Start machine directly via dashboard (no Job Order)
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-direct-start-test",
                "customer": {"name": "Registered Customer", "phone": "09999999999"},
                "sale_items": [],
            },
        )
        self.assertEqual(resp.status_code, 200)

        # Verify customer counts are incremented
        conn = db.get_connection()
        cust = conn.execute("SELECT wash_order_count, dry_order_count FROM customers WHERE customer_id = ?", (customer["customer_id"],)).fetchone()
        conn.close()

        self.assertEqual(cust["wash_order_count"], 1)
        self.assertEqual(cust["dry_order_count"], 0)

    def test_shift_session_auto_timeout(self):
        emp_id = db.create_employee("Overworked Cashier", "1111")
        db.end_active_shift("local", reason="test_reset")
        
        # Manually insert a shift session that started 25 hours ago
        conn = db.get_connection()
        started_at = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        shift_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO shift_sessions (id, employee_id, location_id, started_at, created_at) VALUES (?, ?, 'local', ?, ?)",
            (shift_id, emp_id, started_at, started_at)
        )
        conn.commit()
        conn.close()

        # Check active shift (this should trigger the auto-timeout)
        active_shift = db.get_active_shift("local")
        self.assertIsNone(active_shift)

        # Verify database session is ended with correct reason and estimated ended_at
        conn = db.get_connection()
        session = conn.execute("SELECT * FROM shift_sessions WHERE id = ?", (shift_id,)).fetchone()
        conn.close()

        self.assertIsNotNone(session["ended_at"])
        self.assertEqual(session["end_reason"], "auto_timeout")
        
        # Estimated end time should be exactly 12 hours after started_at
        expected_ended_at = (datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S") + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        self.assertEqual(session["ended_at"], expected_ended_at)

if __name__ == "__main__":
    unittest.main()
