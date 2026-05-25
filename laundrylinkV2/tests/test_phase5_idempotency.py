import os
import tempfile
import unittest
import uuid

import database as db


class IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test_laundrylink.db")
        db.init_db()

        self.product_id = db.create_product(
            name="Idempotency Product",
            unit_price=10,
            unit_cost=4,
            stock_on_hand=5,
            low_stock_threshold=2,
        )
        self.service_id = db.create_service(name="Idempotency Service", unit_price=15)

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def test_repeated_request_id_creates_single_transaction(self):
        req_id = "req-test-123"

        first = db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="washer-a",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 12:00:00",
            sale_items=[
                {"kind": "product", "item_id": self.product_id, "quantity": 2},
                {"kind": "service", "item_id": self.service_id, "quantity": 1},
            ],
            request_id=req_id,
        )

        second = db.insert_transaction_with_items(
            txn_id=str(uuid.uuid4()),
            machine_id="washer-a",
            base_amount=60,
            status="COMPLETED",
            started_at="2026-03-27 12:00:01",
            sale_items=[
                {"kind": "product", "item_id": self.product_id, "quantity": 2},
                {"kind": "service", "item_id": self.service_id, "quantity": 1},
            ],
            request_id=req_id,
        )

        self.assertFalse(first["idempotent_hit"])
        self.assertTrue(second["idempotent_hit"])
        self.assertEqual(first["transaction_id"], second["transaction_id"])

        conn = db.get_connection()
        tx_count = conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE request_id = ?",
            (req_id,),
        ).fetchone()["c"]
        stock_after = conn.execute(
            "SELECT stock_on_hand FROM products WHERE id = ?",
            (self.product_id,),
        ).fetchone()["stock_on_hand"]
        conn.close()

        self.assertEqual(tx_count, 1)
        self.assertEqual(stock_after, 3)


if __name__ == "__main__":
    unittest.main()
