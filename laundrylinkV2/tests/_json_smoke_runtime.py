import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database as db
from app import create_app


def assert_json_response(resp, expected_status=None):
    if expected_status is not None and resp.status_code != expected_status:
        raise AssertionError(f"Expected {expected_status}, got {resp.status_code}, body={resp.data!r}")
    try:
        data = resp.get_json(force=False, silent=False)
    except Exception as exc:
        raise AssertionError(f"Response is not valid JSON: status={resp.status_code}, body={resp.data!r}, err={exc}") from exc
    if data is None:
        raise AssertionError(f"Response JSON is None: status={resp.status_code}, body={resp.data!r}")
    return data


def main():
    tmpdir = tempfile.TemporaryDirectory()
    original_db_path = db.DB_PATH
    db.DB_PATH = os.path.join(tmpdir.name, "json_smoke.db")

    try:
        db.init_db()
        db.upsert_machine("m1", "Washer 1", "washer", "standard", "127.0.0.1", 50, 50, 2, 60)
        db.upsert_machine("d1", "Dryer 1", "dryer", "standard", "127.0.0.1", 50, 50, 2, 60)

        emp_id = db.create_employee("Smoke Employee", "1234")
        db.start_shift(emp_id, "local")

        app = create_app()
        client = app.test_client()

        # Dashboard HTML should render (catches Jinja/embedded JS breakages)
        html_resp = client.get("/")
        if html_resp.status_code != 200:
            raise AssertionError(f"Dashboard HTML failed: status={html_resp.status_code}")

        # Customer listing
        data = assert_json_response(client.get("/dashboard/customers?limit=10"), 200)
        assert "customers" in data

        # Create JO (washer)
        jo_create = assert_json_response(
            client.post(
                "/dashboard/job-orders",
                json={
                    "machine_id": "m1",
                    "location_id": "local",
                    "customer": {"name": "Smoke Customer", "phone": "09123456789"},
                    "wash_qty": 1,
                    "dry_qty": 0,
                    "product_qty": 2,
                    "service_qty": 1,
                    "product_amount": 30,
                    "service_amount": 20,
                },
            ),
            201,
        )
        order = jo_create["job_order"]
        assert int(order.get("total_amount") or 0) == 110

        # Create JO (dryer) to validate combined JO receipt printing
        jo_create_dryer = assert_json_response(
            client.post(
                "/dashboard/job-orders",
                json={
                    "machine_id": "d1",
                    "location_id": "local",
                    "customer": {"name": "Smoke Customer", "phone": "09123456789"},
                    "wash_qty": 0,
                    "dry_qty": 1,
                },
            ),
            201,
        )
        dryer_order = jo_create_dryer["job_order"]

        # Open JO list
        list_data = assert_json_response(client.get("/dashboard/job-orders/open?limit=10"), 200)
        assert isinstance(list_data.get("job_orders"), list)

        # Print JO endpoint returns JSON (may be error if no printer, but still JSON)
        print_resp = client.post(f"/reports/job-order/{order['id']}/print", json={})
        print_data = assert_json_response(print_resp)
        if print_resp.status_code not in (200, 500):
            raise AssertionError(f"Unexpected print status={print_resp.status_code}, json={print_data}")

        # Combined receipt for washer+dryer JO should be a single print request
        bulk_print_resp = client.post(
            "/reports/job-orders/bulk/print",
            json={"job_order_ids": [order["id"], dryer_order["id"]]},
        )
        bulk_print_data = assert_json_response(bulk_print_resp)
        if bulk_print_resp.status_code not in (200, 500):
            raise AssertionError(f"Unexpected combined print status={bulk_print_resp.status_code}, json={bulk_print_data}")

        # Activate using JO
        start_data = assert_json_response(
            client.post(
                "/dashboard/machine/start",
                json={
                    "machine_id": "m1",
                    "location_id": "local",
                    "request_id": "smoke-req-1",
                    "sale_items": [],
                    "customer": {"name": "Smoke Customer", "phone": "09123456789"},
                    "job_order_id": order["id"],
                },
            ),
            200,
        )
        assert start_data.get("status") in ("COMPLETED", "SIMULATED")

        # Reusing same JO should return JSON error
        reuse_resp = client.post(
            "/dashboard/machine/start",
            json={
                "machine_id": "m1",
                "location_id": "local",
                "request_id": "smoke-req-2",
                "sale_items": [],
                "customer": {"name": "Smoke Customer", "phone": "09123456789"},
                "job_order_id": order["id"],
            },
        )
        reuse_data = assert_json_response(reuse_resp)
        if reuse_resp.status_code not in (400, 409):
            raise AssertionError(f"Unexpected JO reuse status={reuse_resp.status_code}, json={reuse_data}")

        # Open JO deletion should succeed
        delete_resp = client.delete(f"/dashboard/job-orders/{dryer_order['id']}", json={})
        delete_data = assert_json_response(delete_resp)
        if delete_resp.status_code != 200:
            raise AssertionError(f"Unexpected JO delete status={delete_resp.status_code}, json={delete_data}")

        # Grouped JO (wash + dry) should be activated across washer and dryer under one JO
        grouped_jo_create = assert_json_response(
            client.post(
                "/dashboard/job-orders",
                json={
                    "location_id": "local",
                    "customer": {"name": "Grouped Customer", "phone": "09123456780"},
                    "wash_qty": 1,
                    "dry_qty": 1,
                    "wash_mode": "normal",
                    "dry_mode": "normal",
                },
            ),
            201,
        )
        grouped_order = grouped_jo_create["job_order"]

        db.clear_machine_run_window("m1")
        db.clear_machine_run_window("d1")

        grouped_start_wash = assert_json_response(
            client.post(
                "/dashboard/machine/start",
                json={
                    "machine_id": "m1",
                    "location_id": "local",
                    "request_id": "smoke-req-grouped-wash",
                    "sale_items": [],
                    "job_order_id": grouped_order["id"],
                },
            ),
            200,
        )
        assert int(grouped_start_wash.get("job_order_remaining_wash_qty") or 0) == 0
        assert int(grouped_start_wash.get("job_order_remaining_dry_qty") or 0) == 1

        db.clear_machine_run_window("d1")

        grouped_start_dry = assert_json_response(
            client.post(
                "/dashboard/machine/start",
                json={
                    "machine_id": "d1",
                    "location_id": "local",
                    "request_id": "smoke-req-grouped-dry",
                    "sale_items": [],
                    "job_order_id": grouped_order["id"],
                },
            ),
            200,
        )
        assert str(grouped_start_dry.get("job_order_status") or "").upper() == "USED"

        print(json.dumps({"ok": True, "message": "JSON smoke checks passed"}))
    finally:
        db.DB_PATH = original_db_path
        tmpdir.cleanup()


if __name__ == "__main__":
    main()
