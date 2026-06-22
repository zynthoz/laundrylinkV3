import re

with open("routes/dashboard.py", "r") as f:
    content = f.read()

# Add imports
imports_to_add = "    list_promos,\n    create_promo,\n    update_promo,\n    delete_promo,\n"
content = content.replace("    update_machine_status,\n", "    update_machine_status,\n" + imports_to_add)

# Add promo API routes
promos_routes = """
@dashboard_bp.route("/promos", methods=["GET"])
@require_auth
def dashboard_list_promos():
    return jsonify({"promos": list_promos(active_only=False)})

@dashboard_bp.route("/promo", methods=["POST"])
@require_auth
def dashboard_create_or_update_promo():
    data = request.get_json() or {}
    promo_id = str(data.get("id") or "").strip()
    name = str(data.get("name") or "").strip()
    price = int(data.get("price") or 0)
    wash_qty = int(data.get("wash_qty") or 0)
    dry_qty = int(data.get("dry_qty") or 0)
    product_qty = int(data.get("product_qty") or 0)
    service_qty = int(data.get("service_qty") or 0)
    is_active = int(data.get("is_active", 1))

    if not name:
        return jsonify({"error": "Promo name is required"}), 400

    if promo_id:
        success = update_promo(promo_id, name, price, wash_qty, dry_qty, product_qty, service_qty, is_active)
        if not success:
            return jsonify({"error": "Failed to update promo"}), 500
        return jsonify({"status": "ok", "promo_id": promo_id})
    else:
        new_id = create_promo(name, price, wash_qty, dry_qty, product_qty, service_qty)
        return jsonify({"status": "ok", "promo_id": new_id})

@dashboard_bp.route("/promo/delete", methods=["POST"])
@require_auth
def dashboard_delete_promo():
    data = request.get_json() or {}
    promo_id = str(data.get("id") or "").strip()
    if not promo_id:
        return jsonify({"error": "Promo ID is required"}), 400
    success = delete_promo(promo_id)
    if not success:
        return jsonify({"error": "Failed to delete promo"}), 500
    return jsonify({"status": "ok"})
"""

# Insert before @dashboard_bp.route("/customers", methods=["GET"])
pattern = r"@dashboard_bp\.route\(\"/customers\", methods=\[\"GET\"\]\)"
match = re.search(pattern, content)
if match:
    content = content[:match.start()] + promos_routes + "\n" + content[match.start():]
    print("Added promo routes")
else:
    print("Could not find /customers route")

with open("routes/dashboard.py", "w") as f:
    f.write(content)

