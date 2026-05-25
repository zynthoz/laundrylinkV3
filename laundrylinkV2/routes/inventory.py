import os
from sqlite3 import IntegrityError

from flask import Blueprint, jsonify, request

from database import (
    adjust_product_boxes,
    adjust_product_stock,
    create_product,
    create_service,
    deactivate_product,
    deactivate_service,
    get_active_shift,
    list_low_stock_products,
    list_products,
    list_services,
    update_product,
    update_service,
)
from routes.security import require_admin_pin

inventory_bp = Blueprint("inventory", __name__)
DEFAULT_LOCATION_ID = os.environ.get("LOCATION_ID", "local")


@inventory_bp.route("/catalog/products", methods=["GET"])
def get_products():
    active_only = (request.args.get("active_only", "true").lower() == "true")
    return jsonify({"products": list_products(active_only=active_only)})


@inventory_bp.route("/catalog/products", methods=["POST"])
def add_product():
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    unit_price = data.get("unit_price")
    unit_cost = data.get("unit_cost", 0)
    stock_on_hand = data.get("stock_on_hand", 0)
    boxes_on_hand = data.get("boxes_on_hand", 0)
    low_stock_threshold = data.get("low_stock_threshold", 20)
    low_box_threshold = data.get("low_box_threshold", 5)

    if not name:
        return jsonify({"error": "name is required"}), 400
    if unit_price is None:
        return jsonify({"error": "unit_price is required"}), 400

    try:
        product_id = create_product(
            name=name,
            unit_price=int(unit_price),
            unit_cost=int(unit_cost),
            stock_on_hand=int(stock_on_hand),
            boxes_on_hand=int(boxes_on_hand),
            low_stock_threshold=int(low_stock_threshold),
            low_box_threshold=int(low_box_threshold),
        )
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numeric fields"}), 400
    except IntegrityError:
        return jsonify({"error": "Product name already exists"}), 409

    return jsonify({"status": "ok", "product_id": product_id}), 201


@inventory_bp.route("/catalog/products/<product_id>", methods=["PUT"])
def edit_product(product_id):
    data = request.get_json() or {}
    try:
        updated = update_product(
            product_id=product_id,
            name=data.get("name"),
            unit_price=(int(data["unit_price"]) if "unit_price" in data else None),
            unit_cost=(int(data["unit_cost"]) if "unit_cost" in data else None),
            stock_on_hand=(int(data["stock_on_hand"]) if "stock_on_hand" in data else None),
            boxes_on_hand=(int(data["boxes_on_hand"]) if "boxes_on_hand" in data else None),
            low_stock_threshold=(int(data["low_stock_threshold"]) if "low_stock_threshold" in data else None),
            low_box_threshold=(int(data["low_box_threshold"]) if "low_box_threshold" in data else None),
        )
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numeric fields"}), 400
    except IntegrityError:
        return jsonify({"error": "Product name already exists"}), 409

    if not updated:
        return jsonify({"error": "Product not found"}), 404
    return jsonify({"status": "ok"})


@inventory_bp.route("/catalog/products/<product_id>/stock", methods=["POST"])
def restock_product(product_id):
    data = request.get_json() or {}
    location_id = str(data.get("location_id") or DEFAULT_LOCATION_ID).strip()

    try:
        quantity = int(data.get("quantity") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be a valid number"}), 400

    if quantity <= 0:
        return jsonify({"error": "quantity must be at least 1"}), 400

    active_shift = get_active_shift(location_id)
    if not active_shift:
        return jsonify({"error": "No active employee shift. Please time in first."}), 400

    result = adjust_product_stock(product_id, quantity, reason="employee_restock")
    if not result:
        return jsonify({"error": "Product not found"}), 404

    return jsonify({
        "status": "ok",
        "product_id": product_id,
        "product_name": result["product_name"],
        "added_qty": result["delta_qty"],
        "stock_on_hand": result["stock_after"],
        "boxes_on_hand": result["boxes_after"],
    })


@inventory_bp.route("/catalog/products/<product_id>/boxes", methods=["POST"])
def restock_product_boxes(product_id):
    data = request.get_json() or {}
    location_id = str(data.get("location_id") or DEFAULT_LOCATION_ID).strip()

    try:
        quantity = int(data.get("quantity") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be a valid number"}), 400

    if quantity <= 0:
        return jsonify({"error": "quantity must be at least 1"}), 400

    active_shift = get_active_shift(location_id)
    if not active_shift:
        return jsonify({"error": "No active employee shift. Please time in first."}), 400

    result = adjust_product_boxes(product_id, quantity)
    if not result:
        return jsonify({"error": "Product not found"}), 404

    return jsonify({
        "status": "ok",
        "product_id": product_id,
        "product_name": result["product_name"],
        "added_boxes": result["delta_boxes"],
        "boxes_on_hand": result["boxes_after"],
    })


@inventory_bp.route("/catalog/products/<product_id>", methods=["DELETE"])
def remove_product(product_id):
    guard = require_admin_pin()
    if guard:
        return guard

    deactivate_product(product_id)
    return jsonify({"status": "ok"})


@inventory_bp.route("/catalog/services", methods=["GET"])
def get_services():
    active_only = (request.args.get("active_only", "true").lower() == "true")
    return jsonify({"services": list_services(active_only=active_only)})


@inventory_bp.route("/catalog/services", methods=["POST"])
def add_service():
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    unit_price = data.get("unit_price")
    bonus_pulses = data.get("bonus_pulses", 1)

    if not name:
        return jsonify({"error": "name is required"}), 400
    if unit_price is None:
        return jsonify({"error": "unit_price is required"}), 400

    try:
        bonus_pulses = int(bonus_pulses)
        if bonus_pulses < 1:
            return jsonify({"error": "bonus_pulses must be at least 1"}), 400
        service_id = create_service(name=name, unit_price=int(unit_price), bonus_pulses=bonus_pulses)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid unit_price or bonus_pulses"}), 400
    except IntegrityError:
        return jsonify({"error": "Service name already exists"}), 409

    return jsonify({"status": "ok", "service_id": service_id}), 201


@inventory_bp.route("/catalog/services/<service_id>", methods=["PUT"])
def edit_service(service_id):
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json() or {}
    try:
        bonus_pulses = (int(data["bonus_pulses"]) if "bonus_pulses" in data else None)
        if bonus_pulses is not None and bonus_pulses < 1:
            return jsonify({"error": "bonus_pulses must be at least 1"}), 400
        updated = update_service(
            service_id=service_id,
            name=data.get("name"),
            unit_price=(int(data["unit_price"]) if "unit_price" in data else None),
            bonus_pulses=bonus_pulses,
        )
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid unit_price or bonus_pulses"}), 400
    except IntegrityError:
        return jsonify({"error": "Service name already exists"}), 409

    if not updated:
        return jsonify({"error": "Service not found"}), 404
    return jsonify({"status": "ok"})


@inventory_bp.route("/catalog/services/<service_id>", methods=["DELETE"])
def remove_service(service_id):
    guard = require_admin_pin()
    if guard:
        return guard

    deactivate_service(service_id)
    return jsonify({"status": "ok"})


@inventory_bp.route("/inventory/low-stock", methods=["GET"])
def low_stock():
    return jsonify({"items": list_low_stock_products()})
