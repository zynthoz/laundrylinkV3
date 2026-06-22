import os
import tempfile
import unittest
import uuid

import database as db
from app import create_app
from services.emailing import _aggregate_days
from routes.reports import _build_day_receipt_data


class EmailReportTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test_laundrylink.db")
        db.init_db()

        # Create machines
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
        db.upsert_machine(
            "m2",
            "Dryer 1",
            "dryer",
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

    def test_aggregate_days_and_promo_breakdown(self):
        # We will create two operational days: 2026-06-15 and 2026-06-16.
        # Set day change time to 00:00.
        db.set_day_change_time("00:00")

        conn = db.get_connection()

        # Day 1: 2026-06-15
        # Let's insert a job order for Day 1
        jo_id1 = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO job_orders (
                id, job_order_no, customer_id, customer_name, customer_phone,
                machine_id, machine_name, machine_type, wash_mode, dry_mode,
                wash_qty, dry_qty, product_qty, service_qty, paid_by_gcash,
                wash_unit_price, dry_unit_price, total_amount, status,
                created_at, updated_at, promo_id, promo_name
            ) VALUES (?, 1001, 'cust1', 'Cust One', '123', 'm1', 'Washer 1', 'washer', 'normal', 'normal',
                      1, 0, 0, 0, 0, 60, 0, 60, 'OPEN', '2026-06-15 10:00:00', '2026-06-15 10:00:00',
                      'promo-a', 'Promo A')
            """,
            (jo_id1,),
        )

        # Let's add a transaction on Day 1 for machine usage breakdown
        conn.execute(
            """
            INSERT INTO transactions (
                id, machine_id, amount, status, started_at, product_total, service_total, paid_by_gcash
            ) VALUES (?, 'm1', 60, 'COMPLETED', '2026-06-15 10:05:00', 0, 0, 0)
            """,
            (str(uuid.uuid4()),),
        )

        # Day 2: 2026-06-16
        # Let's insert two job orders for Day 2: one Promo A, one Promo B
        jo_id2 = str(uuid.uuid4())
        jo_id3 = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO job_orders (
                id, job_order_no, customer_id, customer_name, customer_phone,
                machine_id, machine_name, machine_type, wash_mode, dry_mode,
                wash_qty, dry_qty, product_qty, service_qty, paid_by_gcash,
                wash_unit_price, dry_unit_price, total_amount, status,
                created_at, updated_at, promo_id, promo_name
            ) VALUES (?, 1002, 'cust2', 'Cust Two', '456', 'm1', 'Washer 1', 'washer', 'normal', 'normal',
                      1, 0, 0, 0, 0, 60, 0, 60, 'OPEN', '2026-06-16 11:00:00', '2026-06-16 11:00:00',
                      'promo-a', 'Promo A')
            """,
            (jo_id2,),
        )
        conn.execute(
            """
            INSERT INTO job_orders (
                id, job_order_no, customer_id, customer_name, customer_phone,
                machine_id, machine_name, machine_type, wash_mode, dry_mode,
                wash_qty, dry_qty, product_qty, service_qty, paid_by_gcash,
                wash_unit_price, dry_unit_price, total_amount, status,
                created_at, updated_at, promo_id, promo_name
            ) VALUES (?, 1003, 'cust3', 'Cust Three', '789', 'm2', 'Dryer 1', 'dryer', 'normal', 'normal',
                      0, 1, 0, 0, 0, 0, 60, 60, 'OPEN', '2026-06-16 12:00:00', '2026-06-16 12:00:00',
                      'promo-b', 'Promo B')
            """,
            (jo_id3,),
        )

        # Let's add transactions on Day 2 for machine usage
        conn.execute(
            """
            INSERT INTO transactions (
                id, machine_id, amount, status, started_at, product_total, service_total, paid_by_gcash
            ) VALUES (?, 'm1', 60, 'COMPLETED', '2026-06-16 11:05:00', 0, 0, 0)
            """,
            (str(uuid.uuid4()),),
        )
        conn.execute(
            """
            INSERT INTO transactions (
                id, machine_id, amount, status, started_at, product_total, service_total, paid_by_gcash
            ) VALUES (?, 'm2', 60, 'COMPLETED', '2026-06-16 12:05:00', 0, 0, 0)
            """,
            (str(uuid.uuid4()),),
        )

        conn.commit()
        conn.close()

        # Let's test _build_day_receipt_data for Day 1
        data1 = _build_day_receipt_data("2026-06-15")
        self.assertEqual(data1["job_order_count"], 1)
        self.assertEqual(data1["job_order_promo_count"], 1)
        self.assertEqual(len(data1["job_order_promo_breakdown"]), 1)
        self.assertEqual(data1["job_order_promo_breakdown"][0]["name"], "Promo A")
        self.assertEqual(data1["job_order_promo_breakdown"][0]["count"], 1)

        # Let's test _build_day_receipt_data for Day 2
        data2 = _build_day_receipt_data("2026-06-16")
        self.assertEqual(data2["job_order_count"], 2)
        self.assertEqual(data2["job_order_promo_count"], 2)
        # Should have Promo A and Promo B
        self.assertEqual(len(data2["job_order_promo_breakdown"]), 2)
        pbd2 = sorted(data2["job_order_promo_breakdown"], key=lambda x: x["name"])
        self.assertEqual(pbd2[0]["name"], "Promo A")
        self.assertEqual(pbd2[0]["count"], 1)
        self.assertEqual(pbd2[1]["name"], "Promo B")
        self.assertEqual(pbd2[1]["count"], 1)

        # Now test aggregation of both days
        agg = _aggregate_days(["2026-06-15", "2026-06-16"])
        self.assertIsNotNone(agg)
        self.assertEqual(agg["job_order_count"], 3)
        self.assertEqual(agg["job_order_promo_count"], 3)
        self.assertEqual(agg["job_order_total_amount"], 180)

        # Check job_order_promo_breakdown aggregation
        agg_pbd = sorted(agg["job_order_promo_breakdown"], key=lambda x: x["name"])
        self.assertEqual(len(agg_pbd), 2)
        self.assertEqual(agg_pbd[0]["name"], "Promo A")
        self.assertEqual(agg_pbd[0]["count"], 2)
        self.assertEqual(agg_pbd[1]["name"], "Promo B")
        self.assertEqual(agg_pbd[1]["count"], 1)

        # Check machine_usage_breakdown aggregation
        agg_mub = sorted(agg["machine_usage_breakdown"], key=lambda x: 0 if x["machine_type"] == "washer" else 1)
        self.assertEqual(len(agg_mub), 2)
        self.assertEqual(agg_mub[0]["machine_type"], "washer")
        self.assertEqual(agg_mub[0]["count"], 2)
        self.assertEqual(agg_mub[0]["revenue"], 120)
        self.assertEqual(agg_mub[1]["machine_type"], "dryer")
        self.assertEqual(agg_mub[1]["count"], 1)
        self.assertEqual(agg_mub[1]["revenue"], 60)

    def test_email_rendering_contains_job_orders_and_promos(self):
        # We render templates within the Flask application context
        with self.app.app_context():
            # Dummy data mimicking the output of _aggregate_days
            report_data = {
                "shop_name": "Test Laundromat",
                "gross_collected": 300,
                "net_sales": 250,
                "machine_revenue": 200,
                "product_revenue": 60,
                "service_revenue": 40,
                "total_sales": 260,
                "cash_sales": 200,
                "gcash_revenue": 100,
                "manual_expenses": 30,
                "cogs_total": 20,
                "total_expenses": 50,
                "transaction_count": 5,
                "job_order_count": 8,
                "job_order_used_count": 6,
                "job_order_open_count": 2,
                "job_order_total_amount": 480,
                "job_order_promo_count": 3,
                "job_order_promo_breakdown": [
                    {"name": "Free Dry Promo", "count": 2},
                    {"name": "10% Discount", "count": 1}
                ],
                "products_used": 4,
                "services_used": 2,
                "gcash_job_order_count": 2,
                "machine_usage_breakdown": [
                    {"machine_type_label": "Washer", "count": 3, "revenue": 150},
                    {"machine_type_label": "Dryer", "count": 2, "revenue": 100}
                ]
            }

            from flask import render_template
            html = render_template(
                "email_report.html",
                report=report_data,
                title="Test Monthly Report",
                frequency="monthly",
                period_label="2026-06-01 to 2026-06-30",
                include_flags={
                    "include_operational_stats": True,
                    "include_revenue_breakdown": True,
                    "include_payment_methods": True,
                    "include_expenses": True,
                    "include_machine_usage": True,
                },
                low_stock_products=[]
            )

            # Assert sections and values are in HTML
            self.assertTrue("Job Orders & Promos" in html or "Job Orders &amp; Promos" in html)
            self.assertIn("Total Job Orders", html)
            self.assertIn("Used Job Orders", html)
            self.assertIn("Open Job Orders", html)
            self.assertIn("Job Order Revenue", html)
            self.assertIn("Promo Orders", html)
            self.assertIn("Promo Usage Breakdown", html)
            self.assertIn("Free Dry Promo", html)
            self.assertIn("10% Discount", html)
            # Check values
            self.assertIn("8", html)
            self.assertIn("6", html)
            self.assertIn("2", html)
            self.assertIn("₱480.00", html)
            self.assertIn("3", html)


if __name__ == "__main__":
    unittest.main()
