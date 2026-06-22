import re

with open("routes/inventory.py", "r") as f:
    content = f.read()

# Add imports
imports_to_add = "    list_promos,\n    create_promo,\n    update_promo,\n    delete_promo,\n"
content = content.replace("    update_service,\n", "    update_service,\n" + imports_to_add)

# Add promo API routes
promos_routes = """
@inventory_bp.route("/catalog/promos", methods=["GET"])
@require_auth
def get_promos():
    return jsonify({"promos": list_promos(active_only=False)})

@inventory_bp.route("/catalog/promos", methods=["POST"])
@require_auth
def add_promo():
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    price = int(data.get("price") or 0)
    wash_qty = int(data.get("wash_qty") or 0)
    dry_qty = int(data.get("dry_qty") or 0)
    product_qty = int(data.get("product_qty") or 0)
    service_qty = int(data.get("service_qty") or 0)
    if not name:
        return jsonify({"error": "Promo name is required"}), 400
    try:
        new_id = create_promo(name, price, wash_qty, dry_qty, product_qty, service_qty)
        return jsonify({"status": "ok", "promo_id": new_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Promo with this name already exists"}), 400

@inventory_bp.route("/catalog/promos/<promo_id>", methods=["PUT"])
@require_auth
def edit_promo(promo_id):
    data = request.get_json() or {}
    success = update_promo(
        promo_id=promo_id,
        name=data.get("name"),
        price=data.get("price"),
        wash_qty=data.get("wash_qty"),
        dry_qty=data.get("dry_qty"),
        product_qty=data.get("product_qty"),
        service_qty=data.get("service_qty"),
        is_active=data.get("is_active")
    )
    if not success:
        return jsonify({"error": "Promo not found"}), 404
    return jsonify({"status": "ok"})

@inventory_bp.route("/catalog/promos/<promo_id>", methods=["DELETE"])
@require_auth
def remove_promo(promo_id):
    success = delete_promo(promo_id)
    return jsonify({"status": "ok" if success else "error"}), 200
"""

# Append to the end of the file
content = content + "\n" + promos_routes

with open("routes/inventory.py", "w") as f:
    f.write(content)

