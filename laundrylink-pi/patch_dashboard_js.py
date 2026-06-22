import re

with open("templates/dashboard.html", "r") as f:
    content = f.read()

# 1. Append Promo JS logic
promo_js = """
// === PROMO LOGIC ===
let dashboardPromos = [];

async function loadPromos() {
  try {
    const res = await fetch('/catalog/promos');
    const data = await res.json();
    if (res.ok) {
      dashboardPromos = data.promos || [];
      renderPromoTable();
      populatePromoDropdown();
    }
  } catch (e) {
    console.error('Failed to load promos:', e);
  }
}

function renderPromoTable() {
  const tbody = document.getElementById('promo-table-body');
  if (!tbody) return;
  if (!dashboardPromos.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No promos yet</td></tr>';
    return;
  }
  tbody.innerHTML = dashboardPromos.map(p => `
    <tr>
      <td>${p.name}</td>
      <td>&#8369;${p.price}</td>
      <td>W:${p.wash_qty} / D:${p.dry_qty}</td>
      <td>P:${p.product_qty} / S:${p.service_qty}</td>
      <td>
        <button class="btn-mini" onclick="deletePromo('${p.id}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

function populatePromoDropdown() {
  const sel = document.getElementById('dashboard-jo-promo');
  if (!sel) return;
  const currentVal = sel.value;
  sel.innerHTML = '<option value="">No Promo</option>' + dashboardPromos.map(p => 
    `<option value="${p.id}">${p.name} (&#8369;${p.price})</option>`
  ).join('');
  sel.value = currentVal;
}

function onDashboardJoPromoChange() {
  const promoId = document.getElementById('dashboard-jo-promo').value;
  const promo = dashboardPromos.find(p => p.id === promoId);
  const wQty = document.getElementById('dashboard-jo-wash-qty');
  const dQty = document.getElementById('dashboard-jo-dry-qty');
  
  if (promo) {
    wQty.value = promo.wash_qty;
    dQty.value = promo.dry_qty;
    wQty.disabled = true;
    dQty.disabled = true;
  } else {
    wQty.disabled = false;
    dQty.disabled = false;
  }
  updateDashboardJobOrderCostPreview();
}

async function deletePromo(id) {
  if (!confirm('Are you sure you want to delete this promo?')) return;
  try {
    const res = await fetch(`/catalog/promos/${id}`, { method: 'DELETE' });
    if (res.ok) {
      loadPromos();
    } else {
      alert('Failed to delete promo.');
    }
  } catch (e) {
    console.error(e);
  }
}

function openAdminPromoModal() {
  const name = prompt('Promo Name:');
  if (!name) return;
  const price = prompt('Fixed Price:');
  const washQty = prompt('Wash Quantity:', '0');
  const dryQty = prompt('Dry Quantity:', '0');
  const productQty = prompt('Total Product Items (sum of quantities):', '0');
  const serviceQty = prompt('Total Service Items (sum of quantities):', '0');
  
  if (!price) return;

  fetch('/catalog/promos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: name,
      price: parseInt(price, 10),
      wash_qty: parseInt(washQty, 10) || 0,
      dry_qty: parseInt(dryQty, 10) || 0,
      product_qty: parseInt(productQty, 10) || 0,
      service_qty: parseInt(serviceQty, 10) || 0
    })
  }).then(res => res.json()).then(data => {
    if (data.error) alert(data.error);
    else loadPromos();
  });
}

// Intercept initDashboard to load promos
const oldInitDashboard = window.initDashboard;
window.initDashboard = async function() {
  if (oldInitDashboard) await oldInitDashboard();
  loadPromos();
};
"""

# Insert the promo_js before </script>
pattern = r"(</script>\s*</body>)"
match = re.search(pattern, content)
if match:
    content = content[:match.start()] + promo_js + "\n" + content[match.start():]
    print("Added Promo JS")

with open("templates/dashboard.html", "w") as f:
    f.write(content)

