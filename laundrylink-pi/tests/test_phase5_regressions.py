import os
import tempfile
import unittest
import uuid

import database as db
from app import create_app
from routes import reports as reports_module


class Phase5RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test_laundrylink.db")
        db.init_db()

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

    def _create_employee_and_shift(self, name="Reg Employee"):
        try:
            emp_id = db.create_employee(name, "1234")
        except Exception:
            employees = db.list_employees(active_only=False)
            emp_id = next(e["id"] for e in employees if e["display_name"] == name)

        db.end_active_shift("local", reason="test_reset")
        shift_id = db.start_shift(emp_id, "local")
        return emp_id, shift_id

    def _create_job_order(self, customer_name, customer_phone, wash_qty=1, dry_qty=0):
        customer = db.upsert_customer(customer_name, customer_phone)
        return db.create_job_order(
            customer_id=customer["customer_id"],
            customer_name=customer["name"],
            customer_phone=customer.get("phone"),
            machine_id="m1",
            machine_name="Washer 1",
            machine_type="washer",
            wash_qty=wash_qty,
            dry_qty=dry_qty,
            wash_unit_price=60,
            dry_unit_price=0,
            created_by_employee_id=None,
            created_by_employee_name=None,
        )

    def test_start_requires_active_shift(self):
        db.end_active_shift("local", reason="test_reset")
        order = self._create_job_order("No Shift Customer", "09123456789")

        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-no-shift",
                "customer": {"name": "No Shift Customer", "phone": "09123456789"},
                "job_order_id": order["id"],
            },
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("No active employee shift", resp.json.get("error", ""))

    def test_start_assigns_employee_and_shift(self):
        emp_id, shift_id = self._create_employee_and_shift()
        order = self._create_job_order("Start Assign Customer", "09123456780")

        req_id = "req-assign-1"
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "sale_items": [],
                "customer": {"name": "Start Assign Customer", "phone": "09123456780"},
                "job_order_id": order["id"],
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("employee_id"), emp_id)
        self.assertEqual(resp.json.get("shift_id"), shift_id)

        tx = db.get_transaction_by_request_id(req_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["employee_id"], emp_id)
        self.assertEqual(tx["shift_id"], shift_id)

    def test_start_works_without_job_order(self):
        emp_id, shift_id = self._create_employee_and_shift("Direct Starter")

        req_id = "req-direct-start"
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "sale_items": [],
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("employee_id"), emp_id)
        self.assertEqual(resp.json.get("shift_id"), shift_id)
        self.assertEqual(resp.json.get("job_order_id"), None)
        self.assertEqual(resp.json.get("activation_mode"), "standard")

        tx = db.get_transaction_by_request_id(req_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["employee_id"], emp_id)
        self.assertEqual(tx["shift_id"], shift_id)
        self.assertIsNone(tx.get("job_order_id"))

    def test_start_supports_direct_quick_mode(self):
        emp_id, shift_id = self._create_employee_and_shift("Quick Starter")
        db.update_machine("m1", quick_wash_pulse_count=5, quick_wash_price=99)

        req_id = "req-direct-quick-start"
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "activation_mode": "quick",
                "sale_items": [],
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("employee_id"), emp_id)
        self.assertEqual(resp.json.get("shift_id"), shift_id)
        self.assertEqual(resp.json.get("activation_mode"), "quick")
        self.assertEqual(resp.json.get("base_amount"), 99)
        self.assertEqual(resp.json.get("job_order_id"), None)

        tx = db.get_transaction_by_request_id(req_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["employee_id"], emp_id)
        self.assertEqual(tx["shift_id"], shift_id)
        self.assertEqual(tx["amount"], 99)

    def test_start_supports_direct_paid_by_gcash(self):
        self._create_employee_and_shift("GCash Starter")

        req_id = "req-direct-gcash-start"
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "sale_items": [],
                "paid_by_gcash": True,
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("paid_by_gcash"), 1)

        tx = db.get_transaction_by_request_id(req_id)
        self.assertIsNotNone(tx)
        self.assertEqual(int(tx.get("paid_by_gcash") or 0), 1)

    def test_employee_can_update_transaction_gcash_amount_post_cycle(self):
        emp_id, shift_id = self._create_employee_and_shift("Post Cycle Payment Tester")
        txn_id = str(uuid.uuid4())

        db.insert_transaction_with_items(
            txn_id=txn_id,
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 14:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-post-cycle-payment-1",
            paid_by_gcash=False,
        )

        resp = self.client.post(
            f"/dashboard/transactions/{txn_id}/payment-method",
            json={"gcash_amount": 25},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(int(resp.json.get("gcash_amount") or 0), 25)
        self.assertEqual(int(resp.json.get("cash_amount") or 0), 35)
        self.assertEqual(int(resp.json.get("paid_by_gcash") or 0), 1)

        report = reports_module._build_transaction_receipt_data(txn_id)
        self.assertIsNotNone(report)
        self.assertEqual(report.get("payment_method"), "Split (Cash + GCash)")
        self.assertEqual(int(report.get("gcash_amount") or 0), 25)
        self.assertEqual(int(report.get("cash_amount") or 0), 35)

    def test_post_cycle_logging_without_transaction_id_reclassifies_shift_summary(self):
        emp_id, shift_id = self._create_employee_and_shift("Unmatched Post Cycle Logger")
        txn_id = str(uuid.uuid4())

        db.insert_transaction_with_items(
            txn_id=txn_id,
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 14:10:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-post-cycle-unmatched-1",
            paid_by_gcash=False,
        )

        before = self.client.get("/dashboard/summary/shift")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(int(before.json.get("cash_collected") or 0), 60)
        self.assertEqual(int(before.json.get("gcash_collected") or 0), 0)

        resp = self.client.post(
            "/dashboard/post-cycle-payment/log",
            json={"gcash_amount": 25},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((resp.json or {}).get("status"), "ok")
        self.assertIn("No matching transaction", (resp.json or {}).get("warning") or "")

        after = self.client.get("/dashboard/summary/shift")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(int(after.json.get("cash_collected") or 0), 35)
        self.assertEqual(int(after.json.get("gcash_collected") or 0), 25)
        self.assertEqual(int(after.json.get("post_cycle_transfer_amount") or 0), 25)
        self.assertEqual(int(after.json.get("post_cycle_transfer_count") or 0), 1)

        conn = db.get_connection()
        txn_row = conn.execute(
            "SELECT gcash_amount, paid_by_gcash FROM transactions WHERE id = ? LIMIT 1",
            (txn_id,),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(txn_row)
        self.assertEqual(int(txn_row["gcash_amount"] or 0), 0)
        self.assertEqual(int(txn_row["paid_by_gcash"] or 0), 0)

    def test_post_cycle_unmatched_log_affects_day_receipt_gcash_and_cash_revenue(self):
        emp_id, shift_id = self._create_employee_and_shift("Day Receipt Post Cycle Logger")
        day = "2026-03-28"

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 09:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-post-cycle-day-1",
            paid_by_gcash=False,
        )

        db.create_post_cycle_payment_log(
            amount=20,
            logged_at=f"{day} 09:30:00",
            shift_id=shift_id,
            employee_id=emp_id,
        )

        report = reports_module._build_day_receipt_data(day)
        self.assertIsNotNone(report)
        self.assertEqual(int(report.get("cash_revenue") or 0), 40)
        self.assertEqual(int(report.get("gcash_revenue") or 0), 20)
        self.assertEqual(int(report.get("post_cycle_transfer_amount") or 0), 20)
        self.assertEqual(int(report.get("post_cycle_transfer_count") or 0), 1)

    def test_post_cycle_addons_logs_standalone_transaction_with_gcash_option(self):
        self._create_employee_and_shift("Post Cycle Add-ons Logger")

        product_id = db.create_product(
            "Post Cycle Product",
            unit_price=12,
            unit_cost=4,
            stock_on_hand=20,
            low_stock_threshold=2,
        )
        service_id = db.create_service("Post Cycle Service", unit_price=15)

        resp = self.client.post(
            "/dashboard/post-cycle-payment/add-ons",
            json={
                "location_id": "local",
                "paid_by_gcash": True,
                "sale_items": [
                    {"kind": "product", "item_id": product_id, "quantity": 2},
                    {"kind": "service", "item_id": service_id, "quantity": 1},
                ],
            },
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual((resp.json or {}).get("status"), "ok")
        self.assertEqual(int((resp.json or {}).get("total_amount") or 0), 39)
        self.assertEqual(int((resp.json or {}).get("product_total") or 0), 24)
        self.assertEqual(int((resp.json or {}).get("service_total") or 0), 15)
        self.assertEqual(int((resp.json or {}).get("gcash_amount") or 0), 39)
        self.assertEqual(int((resp.json or {}).get("cash_amount") or 0), 0)

        txn_id = (resp.json or {}).get("transaction_id")
        self.assertTrue(txn_id)

        conn = db.get_connection()
        txn_row = conn.execute(
            "SELECT machine_id, amount, paid_by_gcash, gcash_amount, product_total, service_total FROM transactions WHERE id = ? LIMIT 1",
            (txn_id,),
        ).fetchone()
        item_count_row = conn.execute(
            "SELECT COUNT(*) AS c FROM transaction_items WHERE transaction_id = ?",
            (txn_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(txn_row)
        self.assertEqual(str(txn_row["machine_id"]), "post-cycle-addons")
        self.assertEqual(int(txn_row["amount"] or 0), 39)
        self.assertEqual(int(txn_row["paid_by_gcash"] or 0), 1)
        self.assertEqual(int(txn_row["gcash_amount"] or 0), 39)
        self.assertEqual(int(txn_row["product_total"] or 0), 24)
        self.assertEqual(int(txn_row["service_total"] or 0), 15)
        self.assertEqual(int(item_count_row["c"] or 0), 2)

    def test_post_cycle_addons_requires_at_least_one_item(self):
        self._create_employee_and_shift("Post Cycle Empty Add-ons")

        resp = self.client.post(
            "/dashboard/post-cycle-payment/add-ons",
            json={
                "location_id": "local",
                "paid_by_gcash": False,
                "sale_items": [],
            },
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("at least one", str((resp.json or {}).get("error") or "").lower())

    def test_find_transaction_by_amount_returns_sum_matching_transactions(self):
        emp_id, shift_id = self._create_employee_and_shift("Amount Match Tester")

        tx_60 = str(uuid.uuid4())
        tx_70 = str(uuid.uuid4())

        db.insert_transaction_with_items(
            txn_id=tx_60,
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 14:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-amount-match-60",
        )
        db.insert_transaction_with_items(
            txn_id=tx_70,
            machine_id="m1",
            base_amount=70,
            status="COMPLETED",
            started_at="2026-03-27 15:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-amount-match-70",
        )

        resp = self.client.get("/dashboard/transactions/find-by-amount?amount=130")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(int(resp.json.get("matched_total") or 0), 130)
        self.assertEqual(int(resp.json.get("transaction_count") or 0), 2)

        transactions = resp.json.get("transactions") or []
        ids = [t.get("transaction_id") for t in transactions]
        self.assertIn(tx_60, ids)
        self.assertIn(tx_70, ids)

    def test_admin_verify_pin_endpoint_rejects_wrong_pin(self):
        wrong = self.client.post(
            "/dashboard/admin/verify-pin",
            json={"admin_pin": "9999"},
        )
        self.assertEqual(wrong.status_code, 403)

        ok = self.client.post(
            "/dashboard/admin/verify-pin",
            json={"admin_pin": "1234"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual((ok.json or {}).get("status"), "ok")

    def test_start_works_with_job_order_only_without_customer_payload(self):
        emp_id, shift_id = self._create_employee_and_shift("JO Only Starter")
        order = self._create_job_order("JO Only Customer", "09123456770")

        req_id = "req-jo-only-start"
        resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "sale_items": [],
                "job_order_id": order["id"],
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("employee_id"), emp_id)
        self.assertEqual(resp.json.get("shift_id"), shift_id)
        self.assertEqual(resp.json.get("job_order_id"), order["id"])

        tx = db.get_transaction_by_request_id(req_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["employee_id"], emp_id)
        self.assertEqual(tx["shift_id"], shift_id)
        self.assertEqual(tx.get("job_order_id"), order["id"])

    def test_start_tracks_customer_wash_order_count(self):
        self._create_employee_and_shift("Customer Counter Tester")
        first_order = self._create_job_order("Maria Santos", "09123456783")

        first = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-customer-count-1",
                "sale_items": [],
                "customer": {"name": "Maria Santos", "phone": "09123456783"},
                "job_order_id": first_order["id"],
            },
        )
        self.assertEqual(first.status_code, 200)
        first_customer = first.json.get("customer") or {}
        self.assertEqual(first_customer.get("name"), "Maria Santos")
        self.assertEqual(first_customer.get("wash_order_count"), 1)
        first_customer_id = first_customer.get("customer_id")
        self.assertTrue(first_customer_id)

        db.clear_machine_run_window("m1")
        second_order = self._create_job_order("Maria Santos", "09123456783")

        second = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-customer-count-2",
                "sale_items": [],
                "customer": {"name": "Maria Santos", "phone": "09123456783"},
                "job_order_id": second_order["id"],
            },
        )
        self.assertEqual(second.status_code, 200)
        second_customer = second.json.get("customer") or {}
        self.assertEqual(second_customer.get("customer_id"), first_customer_id)
        self.assertEqual(second_customer.get("wash_order_count"), 2)

    def test_open_job_order_can_be_activated_in_future_shift(self):
        emp1_id, shift1_id = self._create_employee_and_shift("Shift One")

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "Carryover Customer", "phone": "09123456766"},
                "wash_qty": 1,
                "dry_qty": 0,
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        order = create_resp.json.get("job_order") or {}
        self.assertTrue(order.get("id"))
        self.assertEqual(order.get("status"), "OPEN")

        end_resp = self.client.post(
            "/shifts/time-out",
            json={"location_id": "local"},
        )
        self.assertEqual(end_resp.status_code, 200)

        emp2_id = db.create_employee("Shift Two", "1235")
        time_in_resp = self.client.post(
            "/shifts/time-in",
            json={"employee_id": emp2_id, "pin": "1235", "location_id": "local"},
        )
        self.assertEqual(time_in_resp.status_code, 201)
        shift2_id = (time_in_resp.json.get("shift") or {}).get("id")
        self.assertTrue(shift2_id)

        start_resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-future-shift-jo",
                "sale_items": [],
                "customer": {"name": "Carryover Customer", "phone": "09123456766"},
                "job_order_id": order["id"],
            },
        )
        self.assertEqual(start_resp.status_code, 200)
        self.assertEqual(start_resp.json.get("shift_id"), shift2_id)

        claimed = db.get_job_order(order["id"])
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.get("status"), "USED")

    def test_bulk_job_order_creation_is_single_call_and_returns_all_orders(self):
        self._create_employee_and_shift("Bulk JO Shift")

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "location_id": "local",
                "customer": {"name": "Bulk JO Customer", "phone": "09123456760"},
                "machine_orders": [
                    {
                        "machine_id": "m1",
                        "wash_qty": 3,
                        "dry_qty": 0,
                    },
                    {
                        "machine_id": "m1",
                        "wash_qty": 2,
                        "dry_qty": 0,
                    },
                ],
            },
        )

        self.assertEqual(create_resp.status_code, 201)
        orders = create_resp.json.get("job_orders") or []
        self.assertEqual(len(orders), 2)
        self.assertEqual(create_resp.json.get("created_count"), 2)

        conn = db.get_connection()
        count = conn.execute(
            """
            SELECT COUNT(1) AS c
            FROM job_orders
            WHERE customer_name = ?
            """,
            ("Bulk JO Customer",),
        ).fetchone()["c"]
        conn.close()
        self.assertEqual(int(count or 0), 2)

    def test_job_order_creation_accepts_product_and_service_qty(self):
        self._create_employee_and_shift("JO Product Qty Shift")

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "Product Qty Customer", "phone": "09123456761"},
                "wash_qty": 1,
                "dry_qty": 0,
                "product_qty": 3,
                "service_qty": 2,
                "paid_by_gcash": True,
            },
        )

        self.assertEqual(create_resp.status_code, 201)
        order = (create_resp.json or {}).get("job_order") or {}
        self.assertEqual(int(order.get("product_qty") or 0), 3)
        self.assertEqual(int(order.get("service_qty") or 0), 2)
        self.assertEqual(int(order.get("paid_by_gcash") or 0), 1)

        conn = db.get_connection()
        row = conn.execute(
            "SELECT product_qty, service_qty, paid_by_gcash FROM job_orders WHERE id = ? LIMIT 1",
            (order.get("id"),),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(int(row["product_qty"] or 0), 3)
        self.assertEqual(int(row["service_qty"] or 0), 2)
        self.assertEqual(int(row["paid_by_gcash"] or 0), 1)

    def test_job_order_creation_accepts_wash_and_dry_modes(self):
        self._create_employee_and_shift("JO Mode Shift")
        db.update_machine("m1", vend_price=60, quick_wash_price=45)

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "Mode Customer", "phone": "09123456764"},
                "wash_qty": 1,
                "dry_qty": 0,
                "wash_mode": "quick",
                "dry_mode": "normal",
            },
        )

        self.assertEqual(create_resp.status_code, 201)
        order = (create_resp.json or {}).get("job_order") or {}
        self.assertEqual(str(order.get("wash_mode") or ""), "quick")
        self.assertEqual(str(order.get("dry_mode") or ""), "normal")
        self.assertEqual(int(order.get("wash_unit_price") or 0), 45)

    def test_start_uses_job_order_quick_mode_settings(self):
        self._create_employee_and_shift("JO Quick Activation Shift")
        db.update_machine("m1", vend_price=60, quick_wash_price=45, quick_wash_pulse_count=3)

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "Quick Mode Customer", "phone": "09123456766"},
                "wash_qty": 1,
                "dry_qty": 0,
                "wash_mode": "quick",
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        order = (create_resp.json or {}).get("job_order") or {}

        start_resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-jo-quick-mode-1",
                "sale_items": [],
                "job_order_id": order.get("id"),
            },
        )

        self.assertEqual(start_resp.status_code, 200)
        self.assertEqual(start_resp.json.get("activation_mode"), "quick")
        self.assertEqual(int(start_resp.json.get("base_amount") or 0), 45)

    def test_shift_receipt_includes_gcash_revenue_for_paid_job_orders(self):
        emp_id, shift_id = self._create_employee_and_shift("GCash Receipt Tester")

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "GCash Customer", "phone": "09123456763"},
                "wash_qty": 1,
                "dry_qty": 0,
                "paid_by_gcash": True,
            },
        )
        self.assertEqual(create_resp.status_code, 201)

        report = reports_module._build_shift_receipt_data(shift_id)
        self.assertIsNotNone(report)
        self.assertEqual(report.get("gcash_job_order_count"), 1)
        self.assertEqual(report.get("gcash_revenue"), int((create_resp.json.get("job_order") or {}).get("total_amount") or 0))

    def test_type_scoped_job_order_can_be_used_on_any_matching_machine(self):
        self._create_employee_and_shift("Any Machine JO Shift")

        db.upsert_machine(
            "m2",
            "Washer 2",
            "washer",
            "standard",
            "127.0.0.1",
            50,
            50,
            2,
            60,
        )

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "location_id": "local",
                "customer": {"name": "Any Washer Customer", "phone": "09123456762"},
                "machine_orders": [
                    {
                        "machine_type": "washer",
                        "wash_qty": 1,
                        "dry_qty": 0,
                    }
                ],
            },
        )

        self.assertEqual(create_resp.status_code, 201)
        order = (create_resp.json.get("job_orders") or [None])[0] or {}
        self.assertEqual(order.get("machine_type"), "washer")

        open_resp = self.client.get("/dashboard/job-orders/open?machine_type=washer")
        self.assertEqual(open_resp.status_code, 200)
        open_orders = open_resp.json.get("job_orders") or []
        self.assertTrue(any((o.get("id") == order.get("id")) for o in open_orders))

        start_resp = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m2",
                "location_id": "local",
                "request_id": "req-any-washer-1",
                "sale_items": [],
                "job_order_id": order.get("id"),
            },
        )

        self.assertEqual(start_resp.status_code, 200)
        self.assertEqual(start_resp.json.get("job_order_status"), "USED")

    def test_job_order_decrements_per_activation_and_completes_once(self):
        self._create_employee_and_shift("Multi Qty Shift")

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "Multi Qty Customer", "phone": "09123456765"},
                "wash_qty": 3,
                "dry_qty": 0,
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        order = create_resp.json.get("job_order") or {}
        self.assertEqual(int(order.get("wash_qty") or 0), 3)
        self.assertEqual(order.get("status"), "OPEN")

        first = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-jo-multi-1",
                "sale_items": [],
                "job_order_id": order["id"],
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json.get("job_order_status"), "OPEN")
        self.assertEqual(first.json.get("job_order_remaining_wash_qty"), 2)
        self.assertTrue(first.json.get("stored_transaction_id"))

        db.clear_machine_run_window("m1")

        second = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-jo-multi-2",
                "sale_items": [],
                "job_order_id": order["id"],
            },
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json.get("job_order_status"), "OPEN")
        self.assertEqual(second.json.get("job_order_remaining_wash_qty"), 1)
        self.assertTrue(second.json.get("stored_transaction_id"))

        db.clear_machine_run_window("m1")

        third = self.client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "req-jo-multi-3",
                "sale_items": [],
                "job_order_id": order["id"],
            },
        )
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third.json.get("job_order_status"), "USED")
        self.assertEqual(third.json.get("job_order_remaining_wash_qty"), 0)
        self.assertTrue(third.json.get("stored_transaction_id"))

        claimed = db.get_job_order(order["id"])
        self.assertEqual(claimed.get("status"), "USED")
        self.assertEqual(int(claimed.get("wash_qty") or 0), 0)

        conn = db.get_connection()
        tx_count = conn.execute(
            "SELECT COUNT(1) AS c FROM transactions WHERE job_order_id = ?",
            (order["id"],),
        ).fetchone()["c"]
        conn.close()
        self.assertEqual(int(tx_count or 0), 3)

    def test_shift_receipt_includes_job_orders_created_in_shift(self):
        emp_id, shift_id = self._create_employee_and_shift("Shift Receipt JO")

        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "Receipt JO Customer", "phone": "09123456767"},
                "wash_qty": 2,
                "dry_qty": 0,
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        order = create_resp.json.get("job_order") or {}
        self.assertTrue(order.get("id"))

        report = reports_module._build_shift_receipt_data(shift_id)
        self.assertIsNotNone(report)
        self.assertEqual(report.get("job_order_count"), 1)
        self.assertEqual(report.get("job_order_open_count"), 1)
        self.assertEqual(report.get("job_order_used_count"), 0)
        self.assertEqual(report.get("job_order_total_amount"), int(order.get("total_amount") or 0))
        self.assertTrue(any((row.get("job_order_no") == order.get("job_order_no")) for row in (report.get("job_order_breakdown") or [])))

    def test_low_stock_warning_and_negative_allowed(self):
        product_id = db.create_product(
            "LowStock Product",
            unit_price=10,
            unit_cost=3,
            stock_on_hand=1,
            low_stock_threshold=2,
        )

        result = db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 12:00:00",
            sale_items=[{"kind": "product", "item_id": product_id, "quantity": 2}],
            request_id="req-lowstock-1",
        )

        self.assertGreaterEqual(len(result["low_stock_warnings"]), 1)

        conn = db.get_connection()
        stock_after = conn.execute(
            "SELECT stock_on_hand FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()["stock_on_hand"]
        conn.close()

        self.assertEqual(stock_after, -1)

    def test_restock_product_increases_stock_and_logs_movement(self):
        self._create_employee_and_shift("Restock Tester")
        product_id = db.create_product(
            "Restock Product",
            unit_price=10,
            unit_cost=3,
            stock_on_hand=4,
            low_stock_threshold=2,
        )

        resp = self.client.post(
            f"/catalog/products/{product_id}/stock",
            json={"quantity": 6, "location_id": "local"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("added_qty"), 6)
        self.assertEqual(resp.json.get("stock_on_hand"), 10)

        conn = db.get_connection()
        stock_after = conn.execute(
            "SELECT stock_on_hand FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()["stock_on_hand"]
        movement = conn.execute(
            "SELECT delta_qty, stock_after, reason, transaction_id FROM stock_movements WHERE product_id = ? ORDER BY created_at DESC LIMIT 1",
            (product_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(stock_after, 10)
        self.assertEqual(movement["delta_qty"], 6)
        self.assertEqual(movement["stock_after"], 10)
        self.assertEqual(movement["reason"], "employee_restock")
        self.assertIsNone(movement["transaction_id"])

    def test_restock_boxes_increases_boxes_on_hand(self):
        self._create_employee_and_shift("Box Restock Tester")
        product_id = db.create_product(
            "Box Restock Product",
            unit_price=10,
            unit_cost=3,
            stock_on_hand=4,
            boxes_on_hand=2,
            low_stock_threshold=2,
        )

        resp = self.client.post(
            f"/catalog/products/{product_id}/boxes",
            json={"quantity": 3, "location_id": "local"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("added_boxes"), 3)
        self.assertEqual(resp.json.get("boxes_on_hand"), 5)

        conn = db.get_connection()
        boxes_after = conn.execute(
            "SELECT boxes_on_hand FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()["boxes_on_hand"]
        conn.close()

        self.assertEqual(boxes_after, 5)

    def test_day_receipt_totals_reconcile(self):
        emp_id, shift_id = self._create_employee_and_shift("Receipt Tester")
        day = "2026-03-27"

        product_id = db.create_product(
            "Receipt Product",
            unit_price=20,
            unit_cost=8,
            stock_on_hand=20,
            low_stock_threshold=5,
        )
        service_id = db.create_service("Receipt Service", unit_price=15)

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 10:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[
                {"kind": "product", "item_id": product_id, "quantity": 2},
                {"kind": "service", "item_id": service_id, "quantity": 1},
            ],
            request_id="req-receipt-1",
        )

        db.create_manual_expense(
            amount=50,
            note="utilities",
            expense_at=f"{day} 11:00:00",
            shift_id=shift_id,
            employee_id=emp_id,
        )

        report = reports_module._build_day_receipt_data(day)

        self.assertEqual(report["gross_collected"], 115)
        self.assertEqual(report["total_sales"], 115)
        self.assertEqual(report["product_revenue"], 40)
        self.assertEqual(report["service_revenue"], 15)
        self.assertEqual(report["machine_revenue"], 60)
        self.assertEqual(report["cogs_total"], 16)
        self.assertEqual(report["manual_expenses"], 50)
        self.assertEqual(report["total_expenses"], 66)
        self.assertEqual(report["net_sales"], 34)

    def test_shift_receipt_totals_exclude_service_tips(self):
        emp_id, shift_id = self._create_employee_and_shift("Shift Receipt Totals")
        day = "2026-03-27"

        product_id = db.create_product(
            "Shift Receipt Product",
            unit_price=20,
            unit_cost=5,
            stock_on_hand=20,
            low_stock_threshold=5,
        )
        service_id = db.create_service("Shift Receipt Service", unit_price=15)

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 12:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[
                {"kind": "product", "item_id": product_id, "quantity": 2},
                {"kind": "service", "item_id": service_id, "quantity": 1},
            ],
            request_id="req-shift-receipt-tips-1",
        )

        report = reports_module._build_shift_receipt_data(shift_id)

        self.assertEqual(report["gross_collected"], 115)
        self.assertEqual(report["service_revenue"], 15)
        self.assertEqual(report["product_revenue"], 40)
        self.assertEqual(report["machine_revenue"], 60)
        self.assertEqual(report["total_sales"], 115)
        self.assertEqual(report["net_sales"], 90)

    def test_receipt_overrides_do_not_mutate_service_revenue(self):
        base = {
            "machine_revenue": 60,
            "product_revenue": 40,
            "service_revenue": 15,
            "manual_expenses": 10,
            "cogs_total": 6,
            "total_expenses": 16,
            "total_sales": 100,
            "net_sales": 84,
        }

        overridden = reports_module._apply_receipt_overrides(
            base,
            {
                "service_revenue": 999,
                "machine_revenue": 70,
                "product_revenue": 45,
                "total_expenses": 20,
            },
        )

        self.assertEqual(overridden["service_revenue"], 15)
        self.assertEqual(overridden["machine_revenue"], 70)
        self.assertEqual(overridden["product_revenue"], 45)
        self.assertEqual(overridden["total_sales"], 115)
        self.assertEqual(overridden["net_sales"], 95)

    def test_shift_receipt_includes_unlinked_expenses_and_machine_usage_counts(self):
        emp_id, shift_id = self._create_employee_and_shift("Shift Receipt Expense Fallback")
        day = "2026-03-27"
        shift = db.get_shift(shift_id)

        db.upsert_machine(
            "m2",
            "Dryer 1",
            "dryer",
            "standard",
            "127.0.0.2",
            50,
            50,
            2,
            60,
        )

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 12:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-shift-machine-usage-1",
        )
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 12:15:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-shift-machine-usage-2",
        )
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m2",
            base_amount=70,
            status="COMPLETED",
            started_at=f"{day} 12:30:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-shift-machine-usage-3",
        )

        db.create_manual_expense(
            amount=35,
            note="detergent refill",
            expense_at=shift["started_at"],
            shift_id=None,
            employee_id=emp_id,
        )

        report = reports_module._build_shift_receipt_data(shift_id)

        self.assertEqual(report["manual_expenses"], 35)
        usage_rows = report.get("machine_usage_breakdown") or []
        washer_row = next((r for r in usage_rows if r.get("machine_type") == "washer"), None)
        dryer_row = next((r for r in usage_rows if r.get("machine_type") == "dryer"), None)

        self.assertIsNotNone(washer_row)
        self.assertEqual(int(washer_row.get("count") or 0), 2)
        self.assertEqual(int(washer_row.get("revenue") or 0), 120)

        self.assertIsNotNone(dryer_row)
        self.assertEqual(int(dryer_row.get("count") or 0), 1)
        self.assertEqual(int(dryer_row.get("revenue") or 0), 70)

    def test_shift_receipt_includes_unlinked_expenses_without_employee_id(self):
        emp_id, shift_id = self._create_employee_and_shift("Shift Expense No Employee")
        shift = db.get_shift(shift_id)

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=shift["started_at"],
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-shift-expense-no-employee",
        )

        db.create_manual_expense(
            amount=45,
            note="water refill",
            expense_at=shift["started_at"],
            shift_id=None,
            employee_id=None,
        )

        report = reports_module._build_shift_receipt_data(shift_id)
        self.assertEqual(report["manual_expenses"], 45)

    def test_day_print_with_overrides_requires_admin_pin(self):
        self._create_employee_and_shift("Override Pin Test")

        blocked = self.client.post(
            "/reports/day/2026-03-27/print",
            json={
                "overrides": {
                    "machine_revenue": 999,
                }
            },
        )
        self.assertEqual(blocked.status_code, 403)

    def test_day_print_with_overrides_allows_admin_pin(self):
        self._create_employee_and_shift("Override Success Test")

        original_sender = reports_module._send_to_cups
        reports_module._send_to_cups = lambda *_args, **_kwargs: {"printer": "test-printer", "job": "job-override"}
        try:
            resp = self.client.post(
                "/reports/day/2026-03-27/print",
                json={
                    "admin_pin": "1234",
                    "overrides": {
                        "machine_revenue": 999,
                        "product_revenue": 1,
                        "total_expenses": 2,
                    },
                },
            )
        finally:
            reports_module._send_to_cups = original_sender

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("status"), "ok")

    def test_shift_receipt_text_hides_job_orders_and_places_product_total_after_items(self):
        emp_id, shift_id = self._create_employee_and_shift("Shift Receipt Text Layout")
        day = "2026-03-27"

        product_id = db.create_product(
            "Receipt Layout Product",
            unit_price=20,
            unit_cost=8,
            stock_on_hand=20,
            low_stock_threshold=5,
        )

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 13:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[{"kind": "product", "item_id": product_id, "quantity": 2}],
            request_id="req-shift-text-layout",
        )

        report = reports_module._build_shift_receipt_data(shift_id)
        rendered = reports_module._render_receipt_text(report)
        lines = rendered.splitlines()

        self.assertNotIn("5) JOB ORDERS", rendered)
        product_line_idx = next(i for i, line in enumerate(lines) if "Receipt Layout Product x2" in line)
        product_total_idx = next(i for i, line in enumerate(lines) if line.strip().startswith("Total") and "P40" in line)
        self.assertLess(product_line_idx, product_total_idx)

    def test_manual_expense_accepts_name_and_quantity(self):
        emp_id, shift_id = self._create_employee_and_shift("Expense Tester")

        resp = self.client.post(
            "/expenses/manual",
            json={
                "expense_name": "Fabric Softener",
                "quantity": 3,
                "amount": 210,
                "shift_id": shift_id,
                "employee_id": emp_id,
            },
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json.get("expense_name"), "Fabric Softener")
        self.assertEqual(resp.json.get("quantity"), 3)
        self.assertEqual(resp.json.get("amount"), 210)

        conn = db.get_connection()
        row = conn.execute(
            "SELECT amount, note, shift_id, employee_id FROM manual_expenses ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()

        self.assertEqual(row["amount"], 210)
        self.assertEqual(row["note"], "Fabric Softener x3")
        self.assertEqual(row["shift_id"], shift_id)
        self.assertEqual(row["employee_id"], emp_id)

    def test_manual_expense_can_be_reassigned_to_specific_shift(self):
        emp_id, shift_id = self._create_employee_and_shift("Expense Reassign Tester")
        db.end_active_shift("local", reason="test_reassign_setup")
        other_emp_id = db.create_employee("Expense Reassign Source", "1235")
        other_shift_id = db.start_shift(other_emp_id, "local")

        expense_id = db.create_manual_expense(
            amount=75,
            note="detergent",
            expense_at="2026-03-27 11:00:00",
            shift_id=other_shift_id,
            employee_id=other_emp_id,
        )

        resp = self.client.patch(
            f"/expenses/manual/{expense_id}",
            json={
                "shift_id": shift_id,
                "employee_id": emp_id,
                "admin_pin": "1234",
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("status"), "ok")

        conn = db.get_connection()
        row = conn.execute(
            "SELECT shift_id, employee_id, amount, note FROM manual_expenses WHERE id = ? LIMIT 1",
            (expense_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(row["shift_id"], shift_id)
        self.assertEqual(row["employee_id"], emp_id)
        self.assertEqual(row["amount"], 75)
        self.assertEqual(row["note"], "detergent")

        report = reports_module._build_shift_receipt_data(shift_id)
        self.assertEqual(report["manual_expenses"], 75)

    def test_analytics_day_summary_includes_manual_expenses(self):
        emp_id, shift_id = self._create_employee_and_shift("Analytics Expense Tester")
        day = "2026-03-27"

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 09:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-day-summary-expense",
        )
        db.create_manual_expense(
            amount=25,
            note="water",
            expense_at=f"{day} 10:00:00",
            shift_id=shift_id,
            employee_id=emp_id,
        )

        resp = self.client.get(f"/dashboard/summary/day?date={day}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("total_sales"), 60)
        self.assertEqual(resp.json.get("manual_expenses"), 25)
        self.assertEqual(resp.json.get("net_after_expenses"), 35)

    def test_analytics_includes_gcash_statistics(self):
        emp_id, shift_id = self._create_employee_and_shift("Analytics GCash Tester")
        day = "2026-03-27"

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 11:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-analytics-gcash-1",
            paid_by_gcash=True,
        )
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=40,
            status="COMPLETED",
            started_at=f"{day} 12:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-analytics-gcash-2",
            paid_by_gcash=False,
        )

        resp = self.client.get(f"/dashboard/analytics?start={day}&end={day}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("total_revenue"), 100)
        self.assertEqual(resp.json.get("gcash_collected"), 60)
        self.assertEqual(resp.json.get("gcash_transaction_count"), 1)
        self.assertEqual(resp.json.get("gcash_share_pct"), 60)

    def test_print_individual_transaction_receipt(self):
        emp_id, shift_id = self._create_employee_and_shift("Txn Print Tester")
        product_id = db.create_product(
            "Txn Print Product",
            unit_price=12,
            unit_cost=4,
            stock_on_hand=10,
            low_stock_threshold=2,
        )

        txn_id = str(uuid.uuid4())
        db.insert_transaction_with_items(
            txn_id=txn_id,
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 12:30:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[{"kind": "product", "item_id": product_id, "quantity": 1}],
            request_id="req-txn-print-1",
        )

        original_sender = reports_module._send_to_cups
        reports_module._send_to_cups = lambda *_args, **_kwargs: {"printer": "test-printer", "job": "job-1"}
        try:
            resp = self.client.post(f"/reports/transaction/{txn_id}/print", json={})
        finally:
            reports_module._send_to_cups = original_sender

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("status"), "ok")
        self.assertEqual(resp.json.get("report_type"), "transaction")
        self.assertEqual(resp.json.get("reference_id"), txn_id)

    def test_analytics_day_summary_includes_itemized_product_service_breakdown(self):
        emp_id, shift_id = self._create_employee_and_shift("Itemized Summary Tester")
        day = "2026-03-28"

        product_id = db.create_product(
            "Detergent Sachet",
            unit_price=15,
            unit_cost=5,
            stock_on_hand=20,
            low_stock_threshold=3,
        )
        service_name = "Itemized Service " + uuid.uuid4().hex[:6]
        service_id = db.create_service(service_name, unit_price=10)

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 09:30:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[
                {"kind": "product", "item_id": product_id, "quantity": 2},
                {"kind": "service", "item_id": service_id, "quantity": 3},
            ],
            request_id="req-itemized-summary-1",
        )

        resp = self.client.get(f"/dashboard/summary/day?date={day}")
        self.assertEqual(resp.status_code, 200)

        product_rows = resp.json.get("product_breakdown") or []
        service_rows = resp.json.get("service_breakdown") or []

        self.assertTrue(any(r.get("name") == "Detergent Sachet" and r.get("qty") == 2 for r in product_rows))
        self.assertTrue(any(r.get("name") == service_name and r.get("qty") == 3 for r in service_rows))

    def test_analytics_shift_summary_includes_itemized_product_service_breakdown(self):
        emp_id, shift_id = self._create_employee_and_shift("Shift Itemized Summary Tester")

        product_id = db.create_product(
            "Shift Itemized Product",
            unit_price=14,
            unit_cost=4,
            stock_on_hand=20,
            low_stock_threshold=3,
        )
        service_name = "Shift Service " + uuid.uuid4().hex[:6]
        service_id = db.create_service(service_name, unit_price=9)

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-28 15:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[
                {"kind": "product", "item_id": product_id, "quantity": 4},
                {"kind": "service", "item_id": service_id, "quantity": 2},
            ],
            request_id="req-shift-itemized-summary-1",
        )

        resp = self.client.get("/dashboard/summary/shift?location_id=local")
        self.assertEqual(resp.status_code, 200)

        product_rows = resp.json.get("product_breakdown") or []
        service_rows = resp.json.get("service_breakdown") or []

        self.assertTrue(any(r.get("name") == "Shift Itemized Product" and r.get("qty") == 4 for r in product_rows))
        self.assertTrue(any(r.get("name") == service_name and r.get("qty") == 2 for r in service_rows))

    def test_day_receipt_uses_operational_window_0801_to_next_0800(self):
        db.set_day_change_time("08:01")
        emp_id, shift_id = self._create_employee_and_shift("Window Tester")
        day = "2026-03-29"

        # Excluded: before 08:01 of the operational day start.
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=50,
            status="COMPLETED",
            started_at=f"{day} 08:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-window-excluded-start",
        )

        # Included boundaries.
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 08:01:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-window-included-start",
        )
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=70,
            status="COMPLETED",
            started_at="2026-03-30 08:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-window-included-end",
        )

        # Excluded: after 08:00 end boundary.
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=80,
            status="COMPLETED",
            started_at="2026-03-30 08:01:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-window-excluded-end",
        )

        report = reports_module._build_day_receipt_data(day)
        self.assertEqual(report["transaction_count"], 2)
        self.assertEqual(report["gross_collected"], 130)

    def test_day_receipt_uses_configured_day_change_time(self):
        emp_id, shift_id = self._create_employee_and_shift("Custom Window Tester")
        day = "2026-03-31"
        db.set_day_change_time("06:30")

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=50,
            status="COMPLETED",
            started_at=f"{day} 06:29:59",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-custom-window-excluded-start",
        )

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 06:30:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-custom-window-included-start",
        )

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=70,
            status="COMPLETED",
            started_at="2026-04-01 06:29:59",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-custom-window-included-end",
        )

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=80,
            status="COMPLETED",
            started_at="2026-04-01 06:30:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-custom-window-excluded-end",
        )

        report = reports_module._build_day_receipt_data(day)
        self.assertEqual(report["transaction_count"], 2)
        self.assertEqual(report["gross_collected"], 130)

    def test_admin_can_update_day_change_time_setting(self):
        get_resp = self.client.get("/dashboard/settings/day-change-time")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json.get("day_change_time"), "00:00")

        post_resp = self.client.post(
            "/dashboard/settings/day-change-time",
            json={"day_change_time": "07:15", "admin_pin": "1234"},
        )
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual(post_resp.json.get("day_change_time"), "07:15")

        refreshed = self.client.get("/dashboard/settings/day-change-time")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json.get("day_change_time"), "07:15")

    def test_admin_can_update_receipt_format_setting(self):
        get_resp = self.client.get(
            "/dashboard/settings/receipt-format",
            headers={"X-Admin-Pin": "1234"},
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn("elements", get_resp.json or {})
        self.assertTrue((get_resp.json or {}).get("elements", {}).get("shiftday.net_sales_section"))
        self.assertTrue((get_resp.json or {}).get("shop_name"))

        post_resp = self.client.post(
            "/dashboard/settings/receipt-format",
            json={
                "admin_pin": "1234",
                "shop_name": "Laundry Hub",
                "elements": {
                    "shiftday.net_sales_section": False,
                    "common.generated_footer": False,
                },
                "order": {
                    "shiftday": [
                        "shiftday.net_sales_section",
                        "shiftday.date_line",
                    ],
                },
            },
        )
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual((post_resp.json or {}).get("shop_name"), "Laundry Hub")
        self.assertFalse((post_resp.json or {}).get("elements", {}).get("shiftday.net_sales_section"))
        self.assertFalse((post_resp.json or {}).get("elements", {}).get("common.generated_footer"))
        self.assertEqual(
            ((post_resp.json or {}).get("order", {}).get("shiftday") or [None])[0],
            "shiftday.net_sales_section",
        )

    def test_shift_receipt_respects_receipt_format_elements(self):
        emp_id, shift_id = self._create_employee_and_shift("Receipt Format Tester")
        day = "2026-04-03"
        db.set_receipt_format_config({
            "shop_name": "Laundry Hub",
            "elements": {
                "shiftday.net_sales_section": False,
                "common.generated_footer": False,
            }
        })

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at=f"{day} 09:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-receipt-format-1",
        )

        report = reports_module._build_day_receipt_data(day)
        text = reports_module._render_receipt_text(report)
        self.assertIn("Laundry Hub", text)
        self.assertNotIn("8) NET SALES", text)
        self.assertNotIn("Generated:", text)

    def test_machine_usage_breakdown_is_type_summary_with_revenue(self):
        emp_id, shift_id = self._create_employee_and_shift("Machine Summary Tester")
        washer_id = "m-summary-w1"
        dryer_id = "m-summary-d1"
        db.upsert_machine(washer_id, "Summary Washer", "washer", "standard", "127.0.0.2", 50, 50, 2, 60)
        db.upsert_machine(dryer_id, "Summary Dryer", "dryer", "standard", "127.0.0.3", 50, 50, 2, 70)

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id=washer_id,
            base_amount=60,
            status="COMPLETED",
            started_at="2026-04-04 09:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-summary-1",
        )
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id=washer_id,
            base_amount=80,
            status="COMPLETED",
            started_at="2026-04-04 09:10:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-summary-2",
        )
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id=dryer_id,
            base_amount=70,
            status="COMPLETED",
            started_at="2026-04-04 09:20:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-summary-3",
        )

        report = reports_module._build_shift_receipt_data(shift_id)
        self.assertIsNotNone(report)
        usage = report.get("machine_usage_breakdown") or []

        washer_row = next((row for row in usage if row.get("machine_type") == "washer"), None)
        dryer_row = next((row for row in usage if row.get("machine_type") == "dryer"), None)

        self.assertIsNotNone(washer_row)
        self.assertIsNotNone(dryer_row)
        self.assertEqual(int(washer_row.get("count") or 0), 2)
        self.assertEqual(int(dryer_row.get("count") or 0), 1)
        self.assertEqual(int(washer_row.get("revenue") or 0), 140)
        self.assertEqual(int(dryer_row.get("revenue") or 0), 70)

    def test_shift_receipt_respects_custom_section_order(self):
        emp_id, shift_id = self._create_employee_and_shift("Receipt Order Tester")

        db.set_receipt_format_config({
            "elements": {
                "shiftday.date_line": True,
                "shiftday.shift_number_line": True,
            },
            "order": {
                "shiftday": [
                    "shiftday.shift_number_line",
                    "shiftday.date_line",
                ],
            },
        })

        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-04-04 12:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="req-receipt-order-1",
        )

        report = reports_module._build_shift_receipt_data(shift_id)
        report["shift_number"] = "S1"
        report["report_date"] = "2026-04-04"
        text = reports_module._render_receipt_text(report)

        self.assertIn("SHIFT No.", text)
        self.assertIn("DATE", text)
        self.assertLess(text.find("SHIFT No."), text.find("DATE"))

    def test_quick_wash_records_transaction_with_product_and_service_addons(self):
        emp_id, shift_id = self._create_employee_and_shift("Quick Wash Tester")
        req_id = "req-quickwash-addons-1"
        order = self._create_job_order("Quick Wash Customer", "09123456781")

        product_id = db.create_product(
            "Quick Wash Product",
            unit_price=12,
            unit_cost=4,
            stock_on_hand=10,
            low_stock_threshold=2,
        )
        service_id = db.create_service("Quick Wash Service", unit_price=8)

        resp = self.client.post(
            "/dashboard/machine/quick-wash",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "customer": {"name": "Quick Wash Customer", "phone": "09123456781"},
                "job_order_id": order["id"],
                "sale_items": [
                    {"kind": "product", "item_id": product_id, "quantity": 2},
                    {"kind": "service", "item_id": service_id, "quantity": 3},
                ],
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("mode"), "quick_wash")
        self.assertEqual(resp.json.get("employee_id"), emp_id)
        self.assertEqual(resp.json.get("shift_id"), shift_id)
        self.assertEqual(resp.json.get("product_total"), 0)
        self.assertEqual(resp.json.get("service_total"), 0)
        self.assertEqual(resp.json.get("item_count"), 0)

        tx = db.get_transaction_by_request_id(req_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["employee_id"], emp_id)
        self.assertEqual(tx["shift_id"], shift_id)
        self.assertEqual(int(tx.get("product_total") or 0), 0)
        self.assertEqual(int(tx.get("service_total") or 0), 0)
        self.assertEqual(int(tx.get("item_count") or 0), 0)

    def test_quick_wash_transaction_print_creates_print_job_log(self):
        self._create_employee_and_shift("Quick Wash Print Tester")
        order = self._create_job_order("Quick Wash Print Customer", "09123456782")

        req_id = "req-quickwash-print-1"
        start_resp = self.client.post(
            "/dashboard/machine/quick-wash",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": req_id,
                "customer": {"name": "Quick Wash Print Customer", "phone": "09123456782"},
                "job_order_id": order["id"],
                "sale_items": [],
            },
        )
        self.assertEqual(start_resp.status_code, 200)

        txn_id = start_resp.json.get("stored_transaction_id") or start_resp.json.get("transaction_id")
        self.assertTrue(txn_id)

        original_sender = reports_module._send_to_cups
        reports_module._send_to_cups = lambda *_args, **_kwargs: {"printer": "test-printer", "job": "job-quickwash"}
        try:
            print_resp = self.client.post(f"/reports/transaction/{txn_id}/print", json={})
        finally:
            reports_module._send_to_cups = original_sender

        self.assertEqual(print_resp.status_code, 200)
        self.assertEqual(print_resp.json.get("report_type"), "transaction")
        self.assertEqual(print_resp.json.get("reference_id"), txn_id)

        conn = db.get_connection()
        print_job = conn.execute(
            "SELECT report_type, reference_id, status FROM print_jobs WHERE report_type = 'transaction' AND reference_id = ? ORDER BY created_at DESC LIMIT 1",
            (txn_id,),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(print_job)
        self.assertEqual(print_job["report_type"], "transaction")
        self.assertEqual(print_job["reference_id"], txn_id)
        self.assertEqual(print_job["status"], "PRINTED")

    def test_bulk_start_supports_quick_mode_and_single_group_request(self):
        emp_id, shift_id = self._create_employee_and_shift("Bulk Start Quick Tester")

        db.upsert_machine(
            "m2",
            "Dryer 2",
            "dryer",
            "standard",
            "127.0.0.2",
            50,
            50,
            2,
            80,
        )
        db.update_machine("m1", vend_price=60, quick_wash_price=95, quick_wash_pulse_count=3)
        db.update_machine("m2", vend_price=80, quick_wash_price=55, quick_wash_pulse_count=2)

        req_group = "bulk-regression-quick-1"
        resp = self.client.post(
            "/dashboard/machine/start-bulk",
            json={
                "location_id": "local",
                "machine_ids": ["m1", "m2"],
                "request_id": req_group,
                "activation_mode": "quick",
                "sale_items": [],
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("status"), "COMPLETED")
        self.assertEqual(int(resp.json.get("started_count") or 0), 2)
        self.assertEqual(int(resp.json.get("failed_count") or 0), 0)

        tx_m1 = db.get_transaction_by_request_id(f"{req_group}:0:m1")
        tx_m2 = db.get_transaction_by_request_id(f"{req_group}:1:m2")

        self.assertIsNotNone(tx_m1)
        self.assertIsNotNone(tx_m2)
        self.assertEqual(tx_m1["employee_id"], emp_id)
        self.assertEqual(tx_m1["shift_id"], shift_id)
        self.assertEqual(tx_m2["employee_id"], emp_id)
        self.assertEqual(tx_m2["shift_id"], shift_id)
        self.assertEqual(int(tx_m1.get("amount") or 0), 95)
        self.assertEqual(int(tx_m2.get("amount") or 0), 55)

    def test_bulk_transaction_receipt_print_endpoint(self):
        emp_id, shift_id = self._create_employee_and_shift("Bulk Receipt Print Tester")

        txn_1 = str(uuid.uuid4())
        txn_2 = str(uuid.uuid4())
        db.insert_transaction_with_items(
            txn_id=txn_1,
            machine_id="m1",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-29 12:00:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="bulk-print-reg-1:0:m1",
        )
        db.insert_transaction_with_items(
            txn_id=txn_2,
            machine_id="m1",
            base_amount=70,
            status="COMPLETED",
            started_at="2026-03-29 12:05:00",
            employee_id=emp_id,
            shift_id=shift_id,
            sale_items=[],
            request_id="bulk-print-reg-1:1:m1",
        )

        original_sender = reports_module._send_to_cups
        reports_module._send_to_cups = lambda *_args, **_kwargs: {"printer": "test-printer", "job": "job-bulk-receipt"}
        try:
            resp = self.client.post(
                "/reports/transactions/bulk/print",
                json={"transaction_ids": [txn_1, txn_2]},
            )
        finally:
            reports_module._send_to_cups = original_sender

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json.get("status"), "ok")
        self.assertEqual(resp.json.get("report_type"), "bulk_transaction")
        self.assertEqual(int(resp.json.get("transaction_count") or 0), 2)
        self.assertEqual(int(resp.json.get("total_amount") or 0), 130)

    def test_job_orders_summary_metrics_in_receipts_and_analytics(self):
        emp_id, shift_id = self._create_employee_and_shift("JO Metrics Shift")
        
        # Create a promo
        promo_id = db.create_promo("PromoCode100", 100)

        # Create a Job Order with the promo applied
        create_resp = self.client.post(
            "/dashboard/job-orders",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "customer": {"name": "JO Metrics Customer", "phone": "09123456789"},
                "wash_qty": 1,
                "dry_qty": 1,
                "promo_id": promo_id,
                "promo_name": "PromoCode100",
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        order = create_resp.json.get("job_order") or {}
        
        # Verify the dashboard shift summary returns the job order count, total amount and promo details
        summary_resp = self.client.get("/dashboard/summary/shift")
        self.assertEqual(summary_resp.status_code, 200)
        summary = summary_resp.json
        self.assertEqual(summary.get("job_order_count"), 1)
        self.assertEqual(summary.get("job_order_open_count"), 1)
        self.assertEqual(summary.get("job_order_used_count"), 0)
        self.assertEqual(summary.get("job_order_total_amount"), int(order.get("total_amount") or 0))
        self.assertEqual(summary.get("job_order_promo_count"), 1)
        self.assertEqual(summary.get("job_order_promo_breakdown"), [{"name": "PromoCode100", "count": 1}])

        # Check rendering in receipt text
        report = reports_module._build_shift_receipt_data(shift_id)
        self.assertEqual(report.get("job_order_count"), 1)
        self.assertEqual(report.get("job_order_promo_count"), 1)
        self.assertEqual(report.get("job_order_promo_breakdown"), [{"name": "PromoCode100", "count": 1}])
        
        # Render text receipt
        rendered = reports_module._render_receipt_text(report)
        self.assertIn("JOB ORDERS SUMMARY", rendered)
        self.assertIn("Total Orders", rendered)
        self.assertIn("Total Revenue", rendered)
        self.assertIn("Promo Orders", rendered)
        self.assertIn("- PromoCode100", rendered)

        # Check recent shifts summary receipt data builder incorporates these metrics
        recent_report = reports_module._build_recent_shifts_summary_receipt_data(5)
        self.assertIsNotNone(recent_report)
        self.assertEqual(recent_report.get("job_order_count"), 1)
        self.assertEqual(recent_report.get("job_order_total_amount"), int(order.get("total_amount") or 0))
        self.assertEqual(recent_report.get("job_order_promo_count"), 1)
        self.assertEqual(recent_report.get("job_order_promo_breakdown"), [{"name": "PromoCode100", "count": 1}])

    def test_receipt_spacing_and_padding_customization(self):
        # 1. Update config settings
        db.set_receipt_format_config({
            "shop_name": "Laundry Room",
            "top_spacing_lines": 5,
            "bottom_spacing_lines": 4,
            "top_padding_px": 10,
            "bottom_padding_px": 12,
            "elements": {
                "shiftday.net_sales_section": True,
                "common.generated_footer": True,
            }
        })

        config = db.get_receipt_format_config()
        self.assertEqual(config.get("top_spacing_lines"), 5)
        self.assertEqual(config.get("bottom_spacing_lines"), 4)
        self.assertEqual(config.get("top_padding_px"), 10)
        self.assertEqual(config.get("bottom_padding_px"), 12)

        # 2. Check layout normalization limits
        config_clamped = db._normalize_receipt_format_config({
            "top_spacing_lines": 100,  # should be clamped to 20
            "bottom_spacing_lines": -5, # should default to 6 or clamp to min 0
            "top_padding_px": 250,      # should be clamped to 100
            "bottom_padding_px": -10,   # should default to 4 or clamp to min 0
        })
        self.assertEqual(config_clamped.get("top_spacing_lines"), 20)
        self.assertEqual(config_clamped.get("bottom_spacing_lines"), 0)
        self.assertEqual(config_clamped.get("top_padding_px"), 100)
        self.assertEqual(config_clamped.get("bottom_padding_px"), 0)

        # 3. Create active shift and transactions to verify print outputs
        emp_id, shift_id = self._create_employee_and_shift("Spacing Tester")
        report = reports_module._build_shift_receipt_data(shift_id)

        # Verify spacing is respected in _render_receipt_text
        text = reports_module._render_receipt_text(report)
        lines = text.split("\n")
        self.assertTrue(all(line == "" for line in lines[:5]))
        self.assertEqual(lines[5], "Laundry Room")
        self.assertTrue(all(line == "" for line in lines[-4:]))

        # 4. Verify spacing and padding in HTML print endpoint response
        resp = self.client.get(f"/reports/shift/{shift_id}/receipt")
        self.assertEqual(resp.status_code, 200)
        html_data = resp.data.decode("utf-8")
        self.assertIn("padding: 10px 2px 12px;", html_data)
        self.assertIn("Laundry Room", html_data)
        self.assertEqual(html_data.count("Laundry Room"), 1)

        # Verify HTML layout mode when receipt_text is not passed
        with self.client.application.app_context():
            from flask import render_template
            report_with_padding = dict(report)
            report_with_padding["top_spacing_lines"] = config.get("top_spacing_lines")
            report_with_padding["bottom_spacing_lines"] = config.get("bottom_spacing_lines")
            report_with_padding["top_padding_px"] = config.get("top_padding_px")
            report_with_padding["bottom_padding_px"] = config.get("bottom_padding_px")
            html_data_else = render_template("receipt_print.html", report=report_with_padding, receipt_text=None)
            self.assertIn("padding: 10px 2px 12px;", html_data_else)
            self.assertIn('height: 1.15em;">&nbsp;</div>', html_data_else)

    def test_selected_shifts_summary_receipt_data_and_printing(self):
        emp_1, shift_1 = self._create_employee_and_shift("Summary Tester Shift 1")
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=50,
            status="COMPLETED",
            started_at="2026-03-27 10:00:00",
            employee_id=emp_1,
            shift_id=shift_1,
            sale_items=[],
            request_id="req-summary-print-1",
        )
        db.end_shift(shift_1)

        emp_2, shift_2 = self._create_employee_and_shift("Summary Tester Shift 2")
        db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="m1",
            base_amount=80,
            status="COMPLETED",
            started_at="2026-03-27 11:00:00",
            employee_id=emp_2,
            shift_id=shift_2,
            sale_items=[],
            request_id="req-summary-print-2",
        )
        db.end_shift(shift_2)

        # 1. Test helper data builder directly
        report = reports_module._build_shifts_summary_receipt_data_by_ids([shift_1, shift_2])
        self.assertIsNotNone(report)
        self.assertEqual(report.get("actual_count"), 2)
        self.assertEqual(report.get("total_sales"), 130)
        self.assertEqual(report.get("transaction_count"), 2)

        # 2. Test GET preview endpoint
        resp_preview = self.client.get(f"/reports/shifts/summary/preview?shift_ids={shift_1},{shift_2}")
        self.assertEqual(resp_preview.status_code, 200)
        html_data = resp_preview.data.decode("utf-8")
        self.assertIn("SELECTED 2", html_data)

        # 3. Test POST print endpoint
        original_sender = reports_module._send_to_cups
        reports_module._send_to_cups = lambda *_args, **_kwargs: {"printer": "test-printer", "job": "job-shifts-summary"}
        try:
            resp_print = self.client.post(
                "/reports/shifts/summary/print",
                json={"shift_ids": [shift_1, shift_2]},
            )
        finally:
            reports_module._send_to_cups = original_sender

        self.assertEqual(resp_print.status_code, 200)
        self.assertEqual(resp_print.json.get("status"), "ok")
        self.assertEqual(resp_print.json.get("actual_count"), 2)
        self.assertEqual(resp_print.json.get("total_sales"), 130)

    def test_time_based_shifts_workflow(self):
        # 1. GET shifts (empty initially)
        get_resp = self.client.get("/shifts/time-based")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json.get("shifts"), [])

        # 2. POST shift - invalid PIN
        post_resp = self.client.post(
            "/shifts/time-based",
            json={"name": "Morning", "start_time": "08:00", "end_time": "16:00", "admin_pin": "wrong"},
        )
        self.assertEqual(post_resp.status_code, 403)

        # 3. POST shift - valid PIN
        post_resp = self.client.post(
            "/shifts/time-based",
            json={"name": "Morning", "start_time": "08:00", "end_time": "16:00", "admin_pin": "1234"},
        )
        self.assertEqual(post_resp.status_code, 201)
        shift_id = post_resp.json.get("shift", {}).get("id")
        self.assertIsNotNone(shift_id)

        # 4. PUT shift
        put_resp = self.client.put(
            f"/shifts/time-based/{shift_id}",
            json={"name": "Morning Updated", "start_time": "09:00", "end_time": "17:00", "admin_pin": "1234"},
        )
        self.assertEqual(put_resp.status_code, 200)
        self.assertEqual(put_resp.json.get("shift", {}).get("name"), "Morning Updated")

        # 5. GET shifts (shows the updated shift)
        get_resp = self.client.get("/shifts/time-based")
        self.assertEqual(len(get_resp.json.get("shifts")), 1)

        # 6. DELETE shift - invalid PIN
        del_resp = self.client.delete(f"/shifts/time-based/{shift_id}", json={"admin_pin": "wrong"})
        self.assertEqual(del_resp.status_code, 403)

        # 7. DELETE shift - valid PIN
        del_resp = self.client.delete(f"/shifts/time-based/{shift_id}", headers={"X-Admin-Pin": "1234"})
        self.assertEqual(del_resp.status_code, 200)

        # 8. GET shifts (empty again)
        get_resp = self.client.get("/shifts/time-based")
        self.assertEqual(get_resp.json.get("shifts"), [])


if __name__ == "__main__":
    unittest.main()
