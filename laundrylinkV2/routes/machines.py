import os
import re
import uuid
from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from database import (
    attach_job_order_transaction,
    claim_job_order_for_activation,
    clear_machine_run_window,
    create_machine,
    delete_machine,
    get_active_shift,
    get_all_machines,
    get_machine,
    get_services_by_ids,
    get_transaction_by_request_id,
    increment_customer_order_count,
    insert_transaction_with_items,
    upsert_customer,
    set_machine_run_window,
    update_machine,
    update_machine_settings_bulk,
    update_machine_vend_price_bulk,
    update_machine_status,
    delete_transactions,
    revert_job_order_usage,
)
from routes.security import require_admin_pin
from services.esp32 import send_pulse, get_esp32_status, async_send_pulse
from services.esp32 import check_esp32_life
from services.sync import try_immediate_sync

machines_bp = Blueprint("machines", __name__)

IS_DEV = os.environ.get("FLASK_ENV", "development") == "development"
DEFAULT_LOCATION_ID = os.environ.get("LOCATION_ID", "local")
MACHINE_RUN_SECONDS = int(os.environ.get("MACHINE_RUN_SECONDS", str(35 * 60)))
EXTRA_WASH_NAME = "extra wash"
EXTRA_DRY_NAME = "extra dry"
QUICK_SERVICE_NAMES = {EXTRA_WASH_NAME, EXTRA_DRY_NAME}
PHONE_PATTERN = re.compile(r"^\d{10,11}$")


def _normalize_machine_id(raw_id):
    normalized = str(raw_id or "").strip().lower()
    if not normalized:
        return ""
    if not re.fullmatch(r"[a-z0-9_-]+", normalized):
        return ""
    return normalized


def _is_valid_ipv4(value):
    parts = str(value or "").strip().split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit():
            return False
        number = int(part)
        if number < 0 or number > 255:
            return False
    return True


def _exclude_quick_service_items(sale_items):
    service_items = [
        item for item in (sale_items or [])
        if str(item.get("kind") or "").strip().lower() == "service"
    ]
    if not service_items:
        return sale_items or []

    service_ids = [str(item.get("item_id") or "").strip() for item in service_items]
    service_map = get_services_by_ids(service_ids)
    filtered = []

    for item in sale_items or []:
        if str(item.get("kind") or "").strip().lower() != "service":
            filtered.append(item)
            continue

        service_id = str(item.get("item_id") or "").strip()
        service = service_map.get(service_id)
        service_name = str((service or {}).get("name") or "").strip().lower()
        if service_name in QUICK_SERVICE_NAMES:
            continue
        filtered.append(item)

    return filtered


def _resolve_customer_payload(data):
    payload = data if isinstance(data, dict) else {}
    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}

    name = str(customer.get("name") or "").strip()
    if not name:
        return None

    phone_raw = customer.get("phone")
    phone = str(phone_raw).strip() if phone_raw not in (None, "") else None
    if phone and not PHONE_PATTERN.fullmatch(phone):
        raise ValueError("Customer phone must be 10 to 11 digits")

    return upsert_customer(name=name, phone=phone)


def _json_api_guard(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except Exception as exc:
            return jsonify({"error": f"Internal server error: {exc}"}), 500

    return wrapped


@machines_bp.route("/machines", methods=["GET"])
def list_machines():
    machines = get_all_machines()
    for m in machines:
        m["status"] = get_esp32_status(m["esp32_ip"])
    return jsonify(machines)


@machines_bp.route("/machines", methods=["POST"])
def add_machine():
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    machine_id = _normalize_machine_id(data.get("id"))
    name = str(data.get("name") or "").strip()
    machine_type = str(data.get("type") or "washer").strip().lower()
    machine_function = str(data.get("machine_function") or "standard").strip() or "standard"
    esp32_ip = str(data.get("esp32_ip") or "").strip()

    if not machine_id:
        return jsonify({"error": "Valid machine id is required (letters, numbers, - or _)."}), 400
    if not name:
        return jsonify({"error": "Machine name is required."}), 400
    if machine_type not in ("washer", "dryer"):
        return jsonify({"error": "Machine type must be washer or dryer."}), 400
    if not esp32_ip:
        return jsonify({"error": "ESP32 IP is required."}), 400
    if not _is_valid_ipv4(esp32_ip):
        return jsonify({"error": "ESP32 IP must be a valid IPv4 address."}), 400
    if get_machine(machine_id):
        return jsonify({"error": "Machine ID already exists."}), 409

    try:
        create_machine(
            machine_id=machine_id,
            name=name,
            machine_type=machine_type,
            esp32_ip=esp32_ip,
            machine_function=machine_function,
            pulse_on=int(data.get("pulse_on", 50)),
            pulse_off=int(data.get("pulse_off", 50)),
            pulse_count=int(data.get("pulse_count", 2)),
            vend_price=int(data.get("vend_price", 60)),
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numeric fields for pulse or vend price."}), 400

    return jsonify({"status": "ok", "machine_id": machine_id}), 201


@machines_bp.route("/machines/<machine_id>", methods=["PUT"])
def edit_machine(machine_id):
    guard = require_admin_pin()
    if guard:
        return guard

    current = get_machine(machine_id)
    if not current:
        return jsonify({"error": "Machine not found"}), 404

    data = request.get_json(silent=True) or {}

    if "esp32_ip" in data:
        candidate_ip = str(data.get("esp32_ip") or "").strip()
        if not candidate_ip:
            return jsonify({"error": "ESP32 IP cannot be empty."}), 400
        if not _is_valid_ipv4(candidate_ip):
            return jsonify({"error": "ESP32 IP must be a valid IPv4 address."}), 400

    machine_type = None
    if "type" in data:
        machine_type = str(data.get("type") or "").strip().lower()
        if machine_type not in ("washer", "dryer"):
            return jsonify({"error": "Machine type must be washer or dryer."}), 400

    try:
        updated = update_machine(
            machine_id=machine_id,
            name=(str(data.get("name") or "").strip() if "name" in data else None),
            machine_type=machine_type,
            machine_function=(str(data.get("machine_function") or "").strip() if "machine_function" in data else None),
            esp32_ip=(str(data.get("esp32_ip") or "").strip() if "esp32_ip" in data else None),
            pulse_on=(int(data["pulse_on"]) if "pulse_on" in data else None),
            pulse_off=(int(data["pulse_off"]) if "pulse_off" in data else None),
            pulse_count=(int(data["pulse_count"]) if "pulse_count" in data else None),
            vend_price=(int(data["vend_price"]) if "vend_price" in data else None),
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numeric fields for pulse or vend price."}), 400

    if not updated:
        return jsonify({"error": "No fields to update."}), 400

    return jsonify({"status": "ok"})


@machines_bp.route("/machines/<machine_id>", methods=["DELETE"])
def remove_machine(machine_id):
    guard = require_admin_pin()
    if guard:
        return guard

    machine = get_machine(machine_id)
    if not machine:
        return jsonify({"error": "Machine not found"}), 404
    if machine.get("status") == "BUSY":
        return jsonify({"error": "Cannot remove a running machine."}), 409

    if not delete_machine(machine_id):
        return jsonify({"error": "Failed to remove machine."}), 500

    return jsonify({"status": "ok"})


@machines_bp.route("/machines/pricing/bulk", methods=["POST"])
def bulk_update_machine_pricing():
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    machine_type = str(data.get("machine_type") or "all").strip().lower()
    if machine_type not in ("all", "washer", "dryer"):
        return jsonify({"error": "machine_type must be all, washer, or dryer"}), 400

    try:
        vend_price = int(data.get("vend_price"))
    except (TypeError, ValueError):
        return jsonify({"error": "vend_price must be a valid number"}), 400

    if vend_price < 0:
        return jsonify({"error": "vend_price must be 0 or higher"}), 400

    updated_count = update_machine_vend_price_bulk(vend_price, machine_type=machine_type)
    return jsonify(
        {
            "status": "ok",
            "machine_type": machine_type,
            "vend_price": vend_price,
            "updated_count": updated_count,
        }
    )


@machines_bp.route("/machines/settings/bulk", methods=["POST"])
def bulk_update_machine_settings():
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}
    machine_ids = data.get("machine_ids") or []
    if not isinstance(machine_ids, list):
        return jsonify({"error": "machine_ids must be a list"}), 400

    normalized_ids = [
        _normalize_machine_id(machine_id)
        for machine_id in machine_ids
    ]
    normalized_ids = [machine_id for machine_id in normalized_ids if machine_id]
    if not normalized_ids:
        return jsonify({"error": "Select at least one machine"}), 400

    try:
        vend_price = int(data["vend_price"]) if "vend_price" in data else None
        pulse_count = int(data["pulse_count"]) if "pulse_count" in data else None
        quick_wash_price = int(data["quick_wash_price"]) if "quick_wash_price" in data else None
        quick_wash_pulse_count = int(data["quick_wash_pulse_count"]) if "quick_wash_pulse_count" in data else None
    except (TypeError, ValueError):
        return jsonify({"error": "Bulk settings must be valid whole numbers"}), 400

    if vend_price is not None and vend_price < 0:
        return jsonify({"error": "vend_price must be 0 or higher"}), 400
    if pulse_count is not None and pulse_count < 1:
        return jsonify({"error": "pulse_count must be at least 1"}), 400
    if quick_wash_price is not None and quick_wash_price < 0:
        return jsonify({"error": "quick_wash_price must be 0 or higher"}), 400
    if quick_wash_pulse_count is not None and quick_wash_pulse_count < 1:
        return jsonify({"error": "quick_wash_pulse_count must be at least 1"}), 400

    if (
        vend_price is None
        and pulse_count is None
        and quick_wash_price is None
        and quick_wash_pulse_count is None
    ):
        return jsonify({"error": "Provide at least one setting to update"}), 400

    updated_count = update_machine_settings_bulk(
        machine_ids=normalized_ids,
        vend_price=vend_price,
        pulse_count=pulse_count,
        quick_wash_price=quick_wash_price,
        quick_wash_pulse_count=quick_wash_pulse_count,
    )

    return jsonify(
        {
            "status": "ok",
            "updated_count": updated_count,
            "machine_ids": normalized_ids,
        }
    )


@machines_bp.route("/machines/<machine_id>/start", methods=["POST"])
@_json_api_guard
def start_machine(machine_id):
    machine = get_machine(machine_id)
    if not machine:
        return jsonify({"error": "Machine not found"}), 404

    data = request.get_json(silent=True) or {}
    location_id = data.get("location_id") or DEFAULT_LOCATION_ID
    request_id = data.get("request_id")
    job_order_id = data.get("job_order_id")

    if request_id:
        existing = get_transaction_by_request_id(request_id)
        if existing:
            runtime_machine = get_machine(machine_id)
            remaining_seconds = 0
            if runtime_machine and runtime_machine.get("run_ends_at"):
                try:
                    remaining_seconds = max(
                        0,
                        int((datetime.strptime(runtime_machine["run_ends_at"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()),
                    )
                except (TypeError, ValueError):
                    remaining_seconds = 0
            return jsonify({
                "status": existing["status"],
                "transaction_id": existing["id"],
                "stored_transaction_id": existing["id"],
                "machine": machine["name"],
                "amount": int(existing.get("amount") or 0),
                "base_amount": int(existing.get("amount") or 0) - int(existing.get("product_total") or 0) - int(existing.get("service_total") or 0),
                "product_total": int(existing.get("product_total") or 0),
                "service_total": int(existing.get("service_total") or 0),
                "item_count": int(existing.get("item_count") or 0),
                "low_stock_warnings": [],
                "idempotent_hit": True,
                "remaining_seconds": remaining_seconds,
                "employee_id": existing.get("employee_id"),
                "shift_id": existing.get("shift_id"),
                "customer_id": existing.get("customer_id"),
                "customer_name": existing.get("customer_name"),
                "customer_phone": existing.get("customer_phone"),
                "job_order_id": existing.get("job_order_id"),
                "job_order_no": existing.get("job_order_no"),
            })

    if machine.get("status") == "BUSY":
        return jsonify({"error": "Machine is already running"}), 409

    active_shift = get_active_shift(location_id)
    if not active_shift:
        return jsonify({"error": "No active employee shift. Please time in first."}), 400

    if not str(job_order_id or "").strip():
        return jsonify({"error": "Valid job_order_id is required before machine activation"}), 400

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pulse_count = int(machine["pulse_count"])

    import uuid

    txn_id = str(uuid.uuid4())
    txn_status = "COMPLETED"

    try:
        claimed_job_order = claim_job_order_for_activation(
            job_order_id=job_order_id,
            machine_id=machine_id,
            machine_type=machine.get("type"),
        )
    except ValueError as exc:
        error_message = str(exc)
        status_code = 409 if "already used" in error_message.lower() or "closed" in error_message.lower() else 400
        return jsonify({"error": error_message}), status_code

    customer = {
        "customer_id": claimed_job_order.get("customer_id"),
        "name": claimed_job_order.get("customer_name"),
        "phone": claimed_job_order.get("customer_phone"),
    }

    txn_result = {
        "total_amount": 0,
        "product_total": 0,
        "service_total": 0,
        "item_count": 0,
        "low_stock_warnings": [],
        "idempotent_hit": False,
    }
    transaction_id = None
    is_job_order_completed = str(claimed_job_order.get("status") or "").upper() == "USED"
    if is_job_order_completed:
        finalize_request_id = request_id or f"jo-finalize:{claimed_job_order.get('id')}"
        txn_result = insert_transaction_with_items(
            txn_id,
            machine_id,
            int(claimed_job_order.get("total_amount") or 0),
            txn_status,
            timestamp,
            employee_id=active_shift["employee_id"],
            shift_id=active_shift["id"],
            sale_items=[],
            request_id=finalize_request_id,
            customer_id=customer.get("customer_id"),
            customer_name=customer.get("name"),
            customer_phone=customer.get("phone"),
            job_order_id=claimed_job_order.get("id"),
            job_order_no=claimed_job_order.get("job_order_no"),
            paid_by_gcash=bool(int(claimed_job_order.get("paid_by_gcash") or 0)),
        )
        transaction_id = txn_result.get("transaction_id", txn_id)
        attach_job_order_transaction(claimed_job_order.get("id"), transaction_id)
    updated_customer = increment_customer_order_count(customer["customer_id"], machine.get("type"), quantity=1) or customer
    run_ends_at = (datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=MACHINE_RUN_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
    set_machine_run_window(machine_id, timestamp, run_ends_at)

    print(f"[{timestamp}] Transaction {txn_id} recorded for {machine['name']} — {txn_status}")

    try_immediate_sync()

    def on_result(success, message):
        if not success and not IS_DEV:
            if transaction_id:
                delete_transactions([transaction_id])
            revert_job_order_usage(claimed_job_order.get("id"), machine.get("type"))
            clear_machine_run_window(machine_id)
            update_machine_status(machine_id, "OFFLINE")

    async_send_pulse(
        machine["esp32_ip"],
        machine["pulse_on"],
        machine["pulse_off"],
        pulse_count,
        on_result
    )

    return jsonify({
        "status": txn_status,
        "transaction_id": transaction_id,
        "stored_transaction_id": transaction_id,
        "machine": machine["name"],
        "amount": txn_result["total_amount"],
        "base_amount": machine["vend_price"],
        "product_total": txn_result["product_total"],
        "service_total": txn_result["service_total"],
        "item_count": txn_result["item_count"],
        "low_stock_warnings": txn_result["low_stock_warnings"],
        "idempotent_hit": txn_result.get("idempotent_hit", False),
        "remaining_seconds": MACHINE_RUN_SECONDS,
        "employee_id": active_shift["employee_id"],
        "employee_name": active_shift.get("display_name"),
        "shift_id": active_shift["id"],
        "customer": updated_customer,
        "customer_id": (updated_customer or {}).get("customer_id"),
        "customer_name": (updated_customer or {}).get("name"),
        "customer_phone": (updated_customer or {}).get("phone"),
        "job_order_id": claimed_job_order.get("id"),
        "job_order_no": claimed_job_order.get("job_order_no"),
        "job_order_status": claimed_job_order.get("status"),
        "job_order_remaining_wash_qty": int(claimed_job_order.get("wash_qty") or 0),
        "job_order_remaining_dry_qty": int(claimed_job_order.get("dry_qty") or 0),
    })


@machines_bp.route("/machines/<machine_id>/stop", methods=["POST"])
def stop_machine(machine_id):
    machine = get_machine(machine_id)
    if not machine:
        return jsonify({"error": "Machine not found"}), 404

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clear_machine_run_window(machine_id)
    print(f"[{timestamp}] Machine {machine['name']} stopped manually")

    return jsonify({"status": "STOPPED", "machine": machine["name"]})


@machines_bp.route("/machines/<machine_id>/status", methods=["GET"])
def machine_status(machine_id):
    machine = get_machine(machine_id)
    if not machine:
        return jsonify({"error": "Machine not found"}), 404

    status = get_esp32_status(machine["esp32_ip"])
    update_machine_status(machine_id, status)

    return jsonify({"id": machine_id, "name": machine["name"], "status": status})


@machines_bp.route("/machines/<machine_id>/life", methods=["POST"])
def machine_life(machine_id):
    machine = get_machine(machine_id)
    if not machine:
        return jsonify({"error": "Machine not found"}), 404

    ok, message = check_esp32_life(machine["esp32_ip"])
    if ok:
        return jsonify({"status": "ALIVE", "machine": machine["name"], "message": message}), 200
    return jsonify({"status": "OFFLINE", "machine": machine["name"], "error": message}), 502
