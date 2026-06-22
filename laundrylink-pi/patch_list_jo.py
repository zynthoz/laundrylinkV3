import re

with open("database.py", "r") as f:
    content = f.read()

def replace_func(func_name, new_code):
    global content
    pattern = r"def " + func_name + r"\(.*?(?=\ndef |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_code + "\n\n" + content[match.end():]
        print(f"Replaced {func_name}")
    else:
        print(f"Could not find {func_name}")

new_list_open_job_orders = """def list_open_job_orders(customer_id=None, machine_id=None, machine_type=None, limit=100):
    lim = max(1, min(int(limit or 100), 500))
    where_parts = ["status = 'OPEN'"]
    params = []

    normalized_customer_id = str(customer_id or "").strip()
    if normalized_customer_id:
        where_parts.append("customer_id = ?")
        params.append(normalized_customer_id)

    normalized_machine_id = str(machine_id or "").strip()
    if normalized_machine_id:
        where_parts.append("machine_id = ?")
        params.append(normalized_machine_id)

    normalized_machine_type = str(machine_type or "").strip().lower()
    if normalized_machine_type in ("washer", "dryer"):
        where_parts.append("machine_type = ?")
        params.append(normalized_machine_type)

    where_sql = " AND ".join(where_parts)

    conn = get_connection()
    rows = conn.execute(
        f\"\"\"
        SELECT *
        FROM job_orders
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
        \"\"\",
        [*params, lim],
    ).fetchall()
    
    orders = [dict(r) for r in rows]
    for o in orders:
        items = conn.execute("SELECT * FROM job_order_items WHERE job_order_id = ?", (o["id"],)).fetchall()
        o["items"] = [dict(i) for i in items]
    conn.close()
    return orders"""

replace_func("list_open_job_orders", new_list_open_job_orders)

with open("database.py", "w") as f:
    f.write(content)

