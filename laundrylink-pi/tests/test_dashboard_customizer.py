import json
import os
import tempfile
import unittest

import database as db
from app import create_app


class DashboardCustomizerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test_laundrylink.db")
        db.init_db()

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # Set up a test PIN in the environment
        self.original_admin_pin = os.environ.get("ADMIN_PIN")
        os.environ["ADMIN_PIN"] = "123456"

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()
        if self.original_admin_pin is not None:
            os.environ["ADMIN_PIN"] = self.original_admin_pin
        elif "ADMIN_PIN" in os.environ:
            del os.environ["ADMIN_PIN"]

    def test_get_layout_empty_by_default(self):
        res = self.client.get("/dashboard/settings/layout")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn("layout", data)
        self.assertIsNone(data["layout"])

    def test_post_layout_without_pin_forbidden(self):
        payload = {"layout": {"gridlock": False, "layout": []}}
        res = self.client.post(
            "/dashboard/settings/layout",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_post_layout_with_incorrect_pin_forbidden(self):
        payload = {"layout": {"gridlock": False, "layout": []}}
        res = self.client.post(
            "/dashboard/settings/layout",
            headers={"X-Admin-Pin": "incorrect_pin"},
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_post_layout_with_correct_pin_succeeds(self):
        layout_obj = {
            "gridlock": False,
            "layout": [
                {"id": "widget-low-stock", "span": 2, "visible": True, "order": 1}
            ],
        }
        payload = {"layout": layout_obj}

        res = self.client.post(
            "/dashboard/settings/layout",
            headers={"X-Admin-Pin": "123456"},
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        # Verify it was saved and can be retrieved
        get_res = self.client.get("/dashboard/settings/layout")
        self.assertEqual(get_res.status_code, 200)
        get_data = json.loads(get_res.data)
        self.assertEqual(get_data["layout"], layout_obj)


if __name__ == "__main__":
    unittest.main()
