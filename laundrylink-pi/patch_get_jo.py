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

new_get_job_order = """def get_job_order(job_order_id):
    normalized = str(job_order_id or "").strip()
    if not normalized:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM job_orders WHERE id = ? LIMIT 1", (normalized,)).fetchone()
    if not row:
        conn.close()
        return None
    
    order_dict = dict(row)
    items = conn.execute("SELECT * FROM job_order_items WHERE job_order_id = ?", (normalized,)).fetchall()
    order_dict["items"] = [dict(i) for i in items]
    conn.close()
    return order_dict"""

replace_func("get_job_order", new_get_job_order)

with open("database.py", "w") as f:
    f.write(content)

