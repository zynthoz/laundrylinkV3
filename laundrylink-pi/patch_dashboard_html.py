import re

with open("templates/dashboard.html", "r") as f:
    content = f.read()

# 1. Add Promo dropdown and Print Receipt toggle to the UI
ui_to_add = """
              <div style="grid-column: 1 / -1;">
                <div class="machine-type-label" style="margin-bottom:4px">Promo Package</div>
                <select id="dashboard-jo-promo" class="search-input" onchange="onDashboardJoPromoChange()">
                  <option value="">No Promo</option>
                </select>
              </div>
"""
# Insert after Customer Phone div
phone_div = """              <div>
                <div class="machine-type-label" style="margin-bottom:4px">Phone
(optional)</div>
                <input id="dashboard-jo-customer-phone" class="search-input" typ
e="text" placeholder="10 to 11 digits" oninput="onDashboardJobOrderPhoneInput()"
>
              </div>"""

# Wait, finding exact HTML via python replace can be brittle. I'll use regex.
pattern_customer = r"(<input id=\"dashboard-jo-customer-phone\".*?</div>\s*</div>)"
match = re.search(pattern_customer, content, re.DOTALL)
if match:
    content = content[:match.end()] + ui_to_add + content[match.end():]
    print("Added Promo Dropdown")

toggle_to_add = """
            <label style="display:inline-flex;align-items:center;gap:8px;margin-top:10px;font-size:13px;color:var(--text-secondary)">
              <input id="dashboard-jo-print-receipt" type="checkbox" checked>
              Print Receipt
            </label>
"""
pattern_gcash = r"(<label style=\"display:inline-flex;align-items:center;gap:8px;margin-\s*top:10px;font-size:13px;color:var\(--text-secondary\)\\">\s*<input id=\"dashboard-jo-paid-by-gcash\".*?</label>)"
match = re.search(pattern_gcash, content, re.DOTALL)
if match:
    content = content[:match.end()] + toggle_to_add + content[match.end():]
    print("Added Print Receipt toggle")

# 2. Add Admin Promos Card. It belongs in the Settings / Admin Panel.
admin_card = """
          <div class="card" id="admin-promos-card">
            <div class="card-header">
              <h2 class="card-title">Promos</h2>
            </div>
            <div id="admin-promos-list" class="selection-list" style="margin-top:16px;max-height:300px;overflow-y:auto"></div>
            <button class="btn-mini" style="margin-top:12px" onclick="openAdminPromoModal()">Add Promo</button>
          </div>
"""
# Find a place in Admin Panel. Maybe after Products card.
pattern_products_card = r"(<div class=\"card\" id=\"admin-products-card\">.*?</button>\s*</div>)"
match = re.search(pattern_products_card, content, re.DOTALL)
if match:
    content = content[:match.end()] + admin_card + content[match.end():]
    print("Added Admin Promos Card")

with open("templates/dashboard.html", "w") as f:
    f.write(content)

