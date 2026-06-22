import re

with open("routes/dashboard.py", "r") as f:
    content = f.read()

def replace_func(func_name, new_code):
    global content
    pattern = r"@dashboard_bp\.route\(\"/dashboard/job-orders\", methods=\[\"POST\"\]\)\s*def " + func_name + r"\(.*?(?=\n@dashboard_bp\.route|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_code + "\n\n" + content[match.end():]
        print(f"Replaced {func_name}")
    else:
        print(f"Could not find {func_name}")

new_jo_func = """@dashboard_bp.route("/dashboard/job-orders", methods=["POST"])
def dashboard_create_job_order():
    data = request.get_json(silent=True) or {}
    location_id = data.get("location_id") or DEFAULT_LOCATION_ID

    machine_orders_payload = data.get("machine_orders") if isinstance(data.get("machine_orders"), list) else None

    active_shift = get_active_shift(location_id)
    if not active_shift:
        return jsonify({"error": "No active employee shift. Please time in first."}), 400
    try:
        customer = _resolve_customer_payload(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    wash_qty = 0
    dry_qty = 0
    product_qty = 0
    service_qty = 0
    product_amount = 0
    service_amount = 0
    paid_by_gcash = False
    wash_mode = "normal"
    dry_mode = "normal"
    promo_id = None
    promo_name = None
    print_receipt = 1
    items = []

    if not machine_orders_payload:
        try:
            wash_qty = int(data.get("wash_qty", 0))
            dry_qty = int(data.get("dry_qty", 0))
            product_qty = int(data.get("product_qty", 0))
            service_qty = int(data.get("service_qty", 0))
            product_amount = int(data.get("product_amount", 0))
            service_amount = int(data.get("service_amount", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "wash_qty, dry_qty, product_qty, service_qty, product_amount, and service_amount must be whole numbers"}), 400

        paid_by_gcash = bool(data.get("paid_by_gcash"))
        wash_mode = _normalize_job_order_mode(data.get("wash_mode"))
        dry_mode = _normalize_job_order_mode(data.get("dry_mode"))
        promo_id = str(data.get("promo_id") or "").strip() or None
        promo_name = str(data.get("promo_name") or "").strip() or None
        print_receipt = 1 if data.get("print_receipt", True) else 0
        items = data.get("items") or []

        if wash_qty < 0 or dry_qty < 0 or product_qty < 0 or service_qty < 0 or product_amount < 0 or service_amount < 0:
            return jsonify({"error": "wash_qty, dry_qty, product_qty, service_qty, product_amount, and service_amount cannot be negative"}), 400
        if wash_qty == 0 and dry_qty == 0:
            return jsonify({"error": "At least one of wash_qty or dry_qty must be greater than zero"}), 400

    try:
        if machine_orders_payload:
            normalized_orders = []
            for entry in machine_orders_payload:
                machine_id = str((entry or {}).get("machine_id") or "").strip()
                machine_type = str((entry or {}).get("machine_type") or "").strip().lower()

                machine = None
                if machine_id:
                    machine = get_machine(machine_id)
                    if not machine:
                        return jsonify({"error": f"Machine not found: {machine_id}"}), 404
                    machine_type = str(machine.get("type") or "").strip().lower()
                elif machine_type not in ("washer", "dryer"):
                    return jsonify({"error": "Each machine order requires machine_id or valid machine_type (washer/dryer)"}), 400

                try:
                    entry_wash_qty = int((entry or {}).get("wash_qty", 0))
                    entry_dry_qty = int((entry or {}).get("dry_qty", 0))
                    entry_product_qty = int((entry or {}).get("product_qty", 0))
                    entry_service_qty = int((entry or {}).get("service_qty", 0))
                    entry_product_amount = int((entry or {}).get("product_amount", 0))
                    entry_service_amount = int((entry or {}).get("service_amount", 0))
                except (TypeError, ValueError):
                    return jsonify({"error": "machine_orders wash_qty, dry_qty, product_qty, service_qty, product_amount, and service_amount must be whole numbers"}), 400

                paid_by_gcash = paid_by_gcash or bool((entry or {}).get("paid_by_gcash"))
                entry_wash_mode = _normalize_job_order_mode((entry or {}).get("wash_mode"))
                entry_dry_mode = _normalize_job_order_mode((entry or {}).get("dry_mode"))
                entry_promo_id = str((entry or {}).get("promo_id") or "").strip() or None
                entry_promo_name = str((entry or {}).get("promo_name") or "").strip() or None
                entry_print = 1 if (entry or {}).get("print_receipt", True) else 0
                entry_items = (entry or {}).get("items") or []

                if entry_wash_qty < 0 or entry_dry_qty < 0 or entry_product_qty < 0 or entry_service_qty < 0 or entry_product_amount < 0 or entry_service_amount < 0:
                    return jsonify({"error": "machine_orders wash_qty, dry_qty, product_qty, service_qty, product_amount, and service_amount cannot be negative"}), 400
                if entry_wash_qty == 0 and entry_dry_qty == 0:
                    return jsonify({"error": "machine_orders entries must include wash_qty or dry_qty"}), 400

                wash_unit_price = _price_by_machine_type("washer", entry_wash_mode, machine) if entry_wash_qty > 0 else _price_by_machine_type("washer", "standard")
                dry_unit_price = _price_by_machine_type("dryer", entry_dry_mode, machine) if entry_dry_qty > 0 else _price_by_machine_type("dryer", "standard")

                normalized_orders.append({
                    "machine_id": machine_id or ("any-washer" if machine_type == "washer" else "any-dryer"),
                    "machine_name": str((machine or {}).get("name") or ("Any Washer" if machine_type == "washer" else "Any Dryer")),
                    "machine_type": machine_type,
                    "wash_mode": entry_wash_mode,
                    "dry_mode": entry_dry_mode,
                    "wash_qty": entry_wash_qty,
                    "dry_qty": entry_dry_qty,
                    "product_qty": entry_product_qty,
                    "service_qty": entry_service_qty,
                    "product_amount": entry_product_amount,
                    "service_amount": entry_service_amount,
                    "paid_by_gcash": paid_by_gcash or bool((entry or {}).get("paid_by_gcash")),
                    "wash_unit_price": wash_unit_price,
                    "dry_unit_price": dry_unit_price,
                    "promo_id": entry_promo_id,
                    "promo_name": entry_promo_name,
                    "print_receipt": entry_print,
                    "items": entry_items,
                })

            created_orders = create_job_orders_bulk(
                customer_id=customer["customer_id"],
                customer_name=customer["name"],
                customer_phone=customer.get("phone"),
                machine_orders=normalized_orders,
                created_by_shift_id=active_shift.get("id"),
                created_by_employee_id=active_shift.get("employee_id"),
                created_by_employee_name=active_shift.get("display_name"),
            )
            return jsonify({"status": "ok", "job_orders": created_orders, "created_count": len(created_orders)}), 201

        machine_id = str(data.get("machine_id") or "").strip()
        machine = get_machine(machine_id) if machine_id else None

        machine_type = "mixed" if wash_qty > 0 and dry_qty > 0 else ("washer" if wash_qty > 0 else "dryer")
        machine_name = "Grouped Washer + Dryer" if machine_type == "mixed" else (
            "Any Washer" if machine_type == "washer" else "Any Dryer"
        )
        if machine:
            machine_type = str(machine.get("type") or "").strip().lower()
            machine_name = str(machine.get("name") or machine_id)
        elif machine_id:
            return jsonify({"error": "Machine not found"}), 404

        wash_unit_price = _price_by_machine_type("washer", wash_mode, machine) if wash_qty > 0 else _price_by_machine_type("washer", "standard")
        dry_unit_price = _price_by_machine_type("dryer", dry_mode, machine) if dry_qty > 0 else _price_by_machine_type("dryer", "standard")

        order = create_job_order(
            customer_id=customer["customer_id"],
            customer_name=customer["name"],
            customer_phone=customer.get("phone"),
            machine_id=(machine_id if machine_id else ("any-mixed" if machine_type == "mixed" else ("any-washer" if machine_type == "washer" else "any-dryer"))),
            machine_name=machine_name,
            machine_type=machine_type,
            wash_mode=wash_mode,
            dry_mode=dry_mode,
            wash_qty=wash_qty,
            dry_qty=dry_qty,
            wash_unit_price=wash_unit_price,
            dry_unit_price=dry_unit_price,
            product_qty=product_qty,
            service_qty=service_qty,
            product_amount=product_amount,
            service_amount=service_amount,
            paid_by_gcash=paid_by_gcash,
            created_by_shift_id=active_shift.get("id"),
            created_by_employee_id=active_shift.get("employee_id"),
            created_by_employee_name=active_shift.get("display_name"),
            promo_id=promo_id,
            promo_name=promo_name,
            print_receipt=print_receipt,
            items=items,
        )
        return jsonify({"status": "ok", "job_order": order}), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Failed to create job order"}), 500"""

replace_func("dashboard_create_job_order", new_jo_func)

with open("routes/dashboard.py", "w") as f:
    f.write(content)

