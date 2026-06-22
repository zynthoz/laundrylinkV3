import re

with open("templates/dashboard.html", "r") as f:
    content = f.read()

# Add UI to prestart-modal
ui_to_insert = """
            <div class="card" style="padding:12px;margin-bottom:10px;background:var(--bg);">
              <div class="machine-type-label" style="margin-bottom:4px;font-weight:600;">Link to Open Job Order (Optional)</div>
              <input id="prestart-jo-search" class="search-input" type="text" placeholder="Search by Job Order No or Customer" oninput="filterPrestartJobOrders()" style="margin-bottom:8px">
              <div class="catalog-table-wrap" style="max-height:120px;overflow-y:auto">
                <table class="catalog-table" id="prestart-jo-table" style="font-size:12px">
                  <thead>
                    <tr>
                      <th>JO #</th>
                      <th>Customer</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody id="prestart-jo-table-body">
                    <tr><td colspan="3" class="empty-state">Loading...</td></tr>
                  </tbody>
                </table>
              </div>
              <div class="machine-type-label" id="prestart-jo-selected-meta" style="margin-top:8px;color:var(--accent);display:none;"></div>
            </div>
"""

# Insert into prestart-modal after <div class="machine-type-label" id="prestart-machine-meta" style="margin-bottom:8px">Select a machine action to begin.</div>
pattern = r"(<div class=\"machine-type-label\" id=\"prestart-machine-meta\" style=\"margin-bottom:8px\">Select a machine action to begin\.</div>)"
match = re.search(pattern, content)
if match:
    content = content[:match.end()] + ui_to_insert + content[match.end():]
    print("Added Job Order selection to Prestart Modal")

# Append JS logic for prestart job orders
js_to_append = """
// === PRESTART JOB ORDER SELECTION ===
let prestartOpenJobOrders = [];
let selectedPrestartJobOrder = null;

async function loadPrestartJobOrders() {
  try {
    const res = await fetch('/job-orders/open');
    if (res.ok) {
      prestartOpenJobOrders = await res.json();
      renderPrestartJobOrders();
    }
  } catch (e) { console.error(e); }
}

function renderPrestartJobOrders(filterText = '') {
  const tbody = document.getElementById('prestart-jo-table-body');
  if (!tbody) return;
  const filtered = prestartOpenJobOrders.filter(jo => {
    const text = `${jo.job_order_no} ${jo.customer_name}`.toLowerCase();
    return text.includes(filterText.toLowerCase());
  });
  
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No open job orders found</td></tr>';
    return;
  }
  
  tbody.innerHTML = filtered.map(jo => `
    <tr>
      <td>${jo.job_order_no}</td>
      <td>${jo.customer_name}</td>
      <td><button class="btn-mini" onclick="selectPrestartJobOrder('${jo.id}')">Select</button></td>
    </tr>
  `).join('');
}

function filterPrestartJobOrders() {
  const input = document.getElementById('prestart-jo-search');
  if (input) renderPrestartJobOrders(input.value);
}

function selectPrestartJobOrder(id) {
  selectedPrestartJobOrder = prestartOpenJobOrders.find(jo => jo.id === id);
  if (!selectedPrestartJobOrder) return;
  
  // Fill customer details
  const nameEl = document.getElementById('prestart-customer-name');
  const phoneEl = document.getElementById('prestart-customer-phone');
  if (nameEl) nameEl.value = selectedPrestartJobOrder.customer_name;
  if (phoneEl) phoneEl.value = selectedPrestartJobOrder.customer_phone || '';
  
  onPrestartCustomerNameInput(); // trigger meta updates
  
  const metaEl = document.getElementById('prestart-jo-selected-meta');
  if (metaEl) {
    metaEl.style.display = 'block';
    metaEl.textContent = `Linked to JO #${selectedPrestartJobOrder.job_order_no} (Products/Services will NOT be deducted again)`;
  }
}

// Hook into openPrestartAction
const oldOpenPrestartAction = window.openPrestartAction;
window.openPrestartAction = function(machineId, locationId, activationMode, btn) {
  selectedPrestartJobOrder = null;
  const metaEl = document.getElementById('prestart-jo-selected-meta');
  if (metaEl) metaEl.style.display = 'none';
  const searchEl = document.getElementById('prestart-jo-search');
  if (searchEl) searchEl.value = '';
  
  loadPrestartJobOrders();
  if (oldOpenPrestartAction) oldOpenPrestartAction(machineId, locationId, activationMode, btn);
};

// Hook into confirmPrestartAndStart
const oldConfirmPrestartAndStart = window.confirmPrestartAndStart;
window.confirmPrestartAndStart = function() {
  // If we selected a JO, we should pass it to the executeStart or the endpoint.
  // Actually, wait, prestart flow sends the customer name and items to /machine/<id>/activate.
  // We need to inject `job_order_id` into the payload if selected.
  
  if (prestartPending) {
    prestartPending.job_order_id = selectedPrestartJobOrder ? selectedPrestartJobOrder.id : null;
  }
  
  if (oldConfirmPrestartAndStart) oldConfirmPrestartAndStart();
};

// Hook into executeStart
const oldExecuteStart = window.executeStart;
window.executeStart = async function(machineId, locationId, btn, saleItems) {
  const payload = {
    customer: {
      name: (document.getElementById('prestart-customer-name') || {}).value || 'Walk-in',
      phone: (document.getElementById('prestart-customer-phone') || {}).value || null
    },
    paid_by_gcash: !!(prestartPending && prestartPending.paidByGcash),
    print_receipt: !!(prestartPending && prestartPending.printReceipt),
    items: saleItems || [],
    job_order_id: prestartPending ? prestartPending.job_order_id : null
  };
  
  if (btn) { btn.disabled = true; btn.textContent = 'Wait...'; }

  try {
    const actMode = (prestartPending && prestartPending.activationMode) ? prestartPending.activationMode : 'standard';
    const res = await fetch(`/machine/${machineId}/activate?mode=${actMode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      if (btn) { btn.textContent = 'Started'; setTimeout(() => { btn.disabled = false; btn.textContent = prestartPending ? (prestartPending.restoreLabel || 'START') : 'START'; }, 2000); }
      closePrestartModal(false);
      loadDashboardState();
      
      // If we linked a JO, we should mark the machine order as used? 
      // The backend /machine/<id>/activate will handle updating the JO if job_order_id is passed.
    } else {
      if (btn) { btn.disabled = false; btn.textContent = prestartPending ? (prestartPending.restoreLabel || 'START') : 'START'; }
      alert('Failed to start: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = prestartPending ? (prestartPending.restoreLabel || 'START') : 'START'; }
    alert('Error starting machine.');
  }
};
"""

# Insert JS before </body>
pattern_body = r"(</script>\s*</body>)"
match_body = re.search(pattern_body, content)
if match_body:
    content = content[:match_body.start()] + js_to_append + "\n" + content[match_body.start():]
    print("Added Prestart JO logic")
else:
    # We found earlier that </script> is at line 8978
    pattern_body2 = r"(</script>\s*</html>)"
    match_body2 = re.search(pattern_body2, content)
    if match_body2:
        content = content[:match_body2.start()] + js_to_append + "\n" + content[match_body2.start():]
        print("Added Prestart JO logic")

with open("templates/dashboard.html", "w") as f:
    f.write(content)

