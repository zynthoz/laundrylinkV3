import os

from flask import jsonify, request


ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")


def _extract_admin_pin():
    header_pin = request.headers.get("X-Admin-Pin")
    if header_pin:
        return str(header_pin)

    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get("admin_pin") is not None:
        return str(payload.get("admin_pin"))

    return ""


def require_admin_pin():
    provided = _extract_admin_pin()
    if provided != ADMIN_PIN:
        return jsonify({"error": "Invalid admin PIN"}), 403
    return None
