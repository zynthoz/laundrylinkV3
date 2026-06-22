import re

with open("database.py", "r") as f:
    content = f.read()

# We need to replace delete_job_order entirely
old_delete_job_order = """def delete_job_order(job_order_id):
    normalized = str(job_order_id or "").strip()
    if not normalized:
        return False

    conn = get_connection()
    cursor = conn.execute(
        \"\"\"
        DELETE FROM job_orders
        WHERE id = ? AND status = 'OPEN'
        \"\"\",
        (normalized,),
    )
    conn.commit()
    deleted = int(cursor.rowcount or 0) == 1
    conn.close()
    return deleted"""

new_delete_job_order = """def delete_job_order(job_order_id):
    normalized = str(job_order_id or "").strip()
    if not normalized:
        return False

    def _work(conn):
        row = conn.execute("SELECT id FROM job_orders WHERE id = ? AND status = 'OPEN'", (normalized,)).fetchone()
        if not row:
            return False
            
        items = conn.execute("SELECT item_type, item_id, quantity FROM job_order_items WHERE job_order_id = ?", (normalized,)).fetchall()
        for item in items:
            if item["item_type"] == "product":
                conn.execute(
                    "UPDATE products SET stock_on_hand = stock_on_hand + ?, updated_at = ? WHERE id = ?",
                    (item["quantity"], _now_str(), item["item_id"])
                )
                
        conn.execute("DELETE FROM job_order_items WHERE job_order_id = ?", (normalized,))
        conn.execute("DELETE FROM job_orders WHERE id = ?", (normalized,))
        return True

    return _run_write_transaction(_work)"""

if old_delete_job_order in content:
    content = content.replace(old_delete_job_order, new_delete_job_order)
else:
    print("Could not find old_delete_job_order")

with open("database.py", "w") as f:
    f.write(content)

