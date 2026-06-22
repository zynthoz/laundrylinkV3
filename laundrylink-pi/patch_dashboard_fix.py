import re

with open("templates/dashboard.html", "r") as f:
    content = f.read()

# 1. Extract Promos Card
promo_card_pattern = r"(<div class=\"card\">\s*<h3 style=\"font-weight:600;color:var\(--text-primary\);margin-bottom:var\(--space-md\);font-size:0\.875rem\">Promos</h3>.*?</div>\s*</section>)"
match = re.search(promo_card_pattern, content, re.DOTALL)
if match:
    promo_card_html = match.group(1).replace("</section>", "").strip()
    content = content[:match.start()] + "</section>" + content[match.end():]
    print("Extracted Promos Card")
    
    # Insert at end of page-admin
    admin_end_pattern = r"(</section>\s*<!-- ===== PAGE: MACHINE TWEAKING ===== -->)"
    match_admin = re.search(admin_end_pattern, content, re.DOTALL)
    if match_admin:
        content = content[:match_admin.start()] + promo_card_html + "\n      " + content[match_admin.start():]
        print("Inserted Promos Card into Admin Page")
    else:
        print("Could not find end of page-admin")
else:
    print("Could not find Promos card")

# 2. Fix UI in Job Order Settings
# Currently: <div class="filter-bar" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:end">
# Change to: <div class="filter-bar" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));gap:8px;align-items:end">
# And remove style="grid-column: 1 / -1;" from Promo Package div.

old_filter_bar = '<div class="filter-bar" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:end">'
new_filter_bar = '<div class="filter-bar" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));gap:10px;align-items:end">'

content = content.replace(old_filter_bar, new_filter_bar)

# Remove grid-column: 1 / -1;
promo_div_old = '<div style="grid-column: 1 / -1;">\\n                <div class="machine-type-label" style="margin-bottom:4px">Promo Package</div>'
# Wait, let's just use regex for the promo div
pattern_promo = r'<div style="grid-column: 1 / -1;">(\s*<div class="machine-type-label" style="margin-bottom:4px">Promo Package)'
content = re.sub(pattern_promo, r'<div>\1', content)

with open("templates/dashboard.html", "w") as f:
    f.write(content)

