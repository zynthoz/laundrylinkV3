import os
from flask import Blueprint, jsonify, request
from sqlite3 import IntegrityError

from database import (
    create_employee,
    deactivate_employee,
    end_active_shift,
    end_shift,
    get_active_shift,
    get_employee,
    query_shift_history,
    list_employees,
    rotate_employee_pin,
    start_shift,
    verify_employee_pin,
)

shifts_bp = Blueprint("shifts", __name__)

DEFAULT_LOCATION_ID = os.environ.get("LOCATION_ID", "local")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")


def _location_id_from_payload(data):
    return (data.get("location_id") or DEFAULT_LOCATION_ID).strip()


@shifts_bp.route("/employees", methods=["GET"])
def get_employees():
    active_only = (request.args.get("active_only", "false").lower() == "true")
    return jsonify({"employees": list_employees(active_only=active_only)})


@shifts_bp.route("/employees", methods=["POST"])
def create_employee_account():
    data = request.get_json() or {}
    admin_pin = str(data.get("admin_pin") or "")
    display_name = str(data.get("display_name") or "").strip()
    pin = str(data.get("pin") or "").strip()

    if admin_pin != ADMIN_PIN:
        return jsonify({"error": "Invalid admin PIN"}), 403
    if not display_name:
        return jsonify({"error": "display_name is required"}), 400
    if len(pin) < 4:
        return jsonify({"error": "PIN must be at least 4 digits"}), 400

    try:
        employee_id = create_employee(display_name, pin)
    except IntegrityError:
        return jsonify({"error": "Employee name already exists"}), 409

    employee = get_employee(employee_id)
    return jsonify({"status": "ok", "employee": employee}), 201


@shifts_bp.route("/employees/<employee_id>/pin", methods=["PUT"])
def update_employee_pin(employee_id):
    data = request.get_json() or {}
    admin_pin = str(data.get("admin_pin") or "")
    new_pin = str(data.get("new_pin") or "").strip()

    if admin_pin != ADMIN_PIN:
        return jsonify({"error": "Invalid admin PIN"}), 403
    if len(new_pin) < 4:
        return jsonify({"error": "PIN must be at least 4 digits"}), 400
    if not get_employee(employee_id):
        return jsonify({"error": "Employee not found"}), 404

    rotate_employee_pin(employee_id, new_pin)
    return jsonify({"status": "ok"})


@shifts_bp.route("/employees/<employee_id>", methods=["DELETE"])
def disable_employee(employee_id):
    data = request.get_json(silent=True) or {}
    admin_pin = str(data.get("admin_pin") or "")

    if admin_pin != ADMIN_PIN:
        return jsonify({"error": "Invalid admin PIN"}), 403
    employee = get_employee(employee_id)
    if not employee:
        return jsonify({"error": "Employee not found"}), 404

    active = get_active_shift(_location_id_from_payload(data))
    if active and active.get("employee_id") == employee_id:
        return jsonify({"error": "Cannot remove employee with active shift. Time out first."}), 409

    deactivate_employee(employee_id)
    return jsonify({"status": "ok"})


@shifts_bp.route("/shifts/active", methods=["GET"])
def active_shift():
    location_id = (request.args.get("location_id") or DEFAULT_LOCATION_ID).strip()
    active = get_active_shift(location_id)
    return jsonify({"active_shift": active})


@shifts_bp.route("/shifts/history", methods=["GET"])
def shift_history():
    location_id = (request.args.get("location_id") or DEFAULT_LOCATION_ID).strip()
    include_active = request.args.get("include_active", "false").lower() == "true"
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", request.args.get("limit", 20)))
    except (TypeError, ValueError):
        per_page = 20

    search_term = (request.args.get("q") or "").strip()

    result = query_shift_history(
        location_id=location_id,
        page=page,
        per_page=per_page,
        include_active=include_active,
        search_term=search_term,
    )

    return jsonify(result)


@shifts_bp.route("/shifts/time-in", methods=["POST"])
def time_in():
    data = request.get_json() or {}
    employee_id = str(data.get("employee_id") or "").strip()
    pin = str(data.get("pin") or "").strip()
    confirm_handover = bool(data.get("confirm_handover"))
    location_id = _location_id_from_payload(data)

    if not employee_id:
        return jsonify({"error": "employee_id is required"}), 400
    if not verify_employee_pin(employee_id, pin):
        return jsonify({"error": "Invalid employee credentials"}), 401

    active = get_active_shift(location_id)
    if active and active["employee_id"] != employee_id:
        if not confirm_handover:
            return jsonify({
                "error": "Active shift exists",
                "requires_handover_confirm": True,
                "active_shift": active,
            }), 409
        end_active_shift(location_id, reason="handover")

    if active and active["employee_id"] == employee_id:
        return jsonify({"status": "ok", "shift": active, "note": "Employee already timed in"})

    shift_id = start_shift(employee_id, location_id)
    shift = get_active_shift(location_id)
    return jsonify({"status": "ok", "shift_id": shift_id, "shift": shift}), 201


@shifts_bp.route("/shifts/time-out", methods=["POST"])
def time_out():
    data = request.get_json() or {}
    location_id = _location_id_from_payload(data)
    shift_id = str(data.get("shift_id") or "").strip()

    if shift_id:
        end_shift(shift_id, reason="logout")
        return jsonify({"status": "ok", "shift_id": shift_id})

    active = get_active_shift(location_id)
    if not active:
        return jsonify({"error": "No active shift"}), 404

    end_shift(active["id"], reason="logout")
    return jsonify({"status": "ok", "shift_id": active["id"]})
