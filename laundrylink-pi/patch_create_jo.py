import re

with open("templates/dashboard.html", "r") as f:
    content = f.read()

def replace_func(func_name, new_code):
    global content
    pattern = r"function " + func_name + r"\(\)\s*\{.*?(?=\n\s*function |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_code + "\n\n" + content[match.end():]
        print(f"Replaced {func_name}")
    else:
        print(f"Could not find {func_name}")

new_create_func = """async function createDashboardJobOrder() {
      const payload = buildDashboardJobOrderPayload();
      if (!payload) return;

      const fb = document.getElementById('dashboard-jo-feedback');
      if (fb) { fb.textContent = 'Creating job order...'; fb.style.color = ''; }

      try {
        const res = await fetch('/dashboard/job-orders', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          if (fb) { fb.textContent = 'Job order created successfully.'; fb.style.color = 'var(--accent)'; }
          
          if (payload.print_receipt) {
              if (data.job_orders && data.job_orders.length) {
                  for (let order of data.job_orders) {
                      await fetch(`/printer/print/job-order/${order.id}`, { method: 'POST' });
                  }
              } else if (data.job_order) {
                  await fetch(`/printer/print/job-order/${data.job_order.id}`, { method: 'POST' });
              }
          }

          resetDashboardJobOrderForm();
          loadOpenJobOrders();
        } else {
          if (fb) { fb.textContent = 'Error: ' + (data.error || 'Failed to create job order'); fb.style.color = '#e74c3c'; }
          alert(data.error || 'Failed to create job order');
        }
      } catch (err) {
        if (fb) { fb.textContent = 'Error creating job order.'; fb.style.color = '#e74c3c'; }
        console.error(err);
      }
    }"""

replace_func("createDashboardJobOrder", new_create_func)

with open("templates/dashboard.html", "w") as f:
    f.write(content)

