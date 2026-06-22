// pages/orders.js
// LaundryLink — Job Orders Tab View Controller

let openOrdersList = [];
let customerList = [];

function renderOrdersPage() {
  document.getElementById("content").innerHTML = `
    <div class="split-layout-orders">
      
      <!-- LEFT COLUMN: OPEN ORDERS LIST -->
      <div class="machine-card-shell" style="height: 100%; display: flex; flex-direction: column;">
        <div class="machine-card-inner" style="flex: 1; min-height: auto; display: flex; flex-direction: column; justify-content: flex-start;">
          <div class="card-header-row">
            <h3 class="card-title">Active Job Orders</h3>
            <span class="badge badge-busy" id="open-orders-count">0 Open</span>
          </div>
          
          <div class="filter-bar">
            <div class="search-input-wrapper">
              <svg class="search-input-icon" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
              <input type="text" id="order-search" placeholder="Search by customer name..." oninput="filterOpenOrders()">
            </div>
            <button class="btn btn-secondary" onclick="loadOpenOrders()" style="min-height: 48px; padding: 0 14px;">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89H18v3H4"></path></svg>
            </button>
          </div>
          
          <div class="list-group" id="open-orders-container" style="overflow-y: auto; max-height: 520px; flex: 1;">
            <div class="initial-loader">
              <div class="spinner"></div>
              <p>Loading open transactions...</p>
            </div>
          </div>
        </div>
      </div>
      
      <!-- RIGHT COLUMN: CREATE NEW ORDER -->
      <div class="machine-card-shell" style="align-self: start;">
        <div class="machine-card-inner" style="min-height: auto;">
          <div class="card-header-row">
            <h3 class="card-title">New Job Order</h3>
          </div>
          
          <form id="new-order-form" onsubmit="createNewJobOrder(event)">
            <div class="form-group">
              <label class="form-label" for="order-cust-name">Customer Name *</label>
              <input type="text" id="order-cust-name" required placeholder="John Doe" list="customer-datalist">
              <datalist id="customer-datalist"></datalist>
            </div>
            
            <div class="form-group">
              <label class="form-label" for="order-cust-phone">Phone Number</label>
              <input type="tel" id="order-cust-phone" placeholder="09171234567" pattern="^09\\d{9}$" title="Must be a valid PH mobile number (e.g. 09171234567)">
            </div>
  
            <div class="grid-cols-2" style="gap: 12px; margin-bottom: 0;">
              <div class="form-group">
                <label class="form-label" for="order-wash-qty">Washes (Qty)</label>
                <input type="number" id="order-wash-qty" value="0" min="0" onchange="calculateOrderTotal()">
              </div>
              <div class="form-group">
                <label class="form-label" for="order-dry-qty">Dries (Qty)</label>
                <input type="number" id="order-dry-qty" value="0" min="0" onchange="calculateOrderTotal()">
              </div>
            </div>
            
            <div class="grid-cols-2" style="gap: 12px; margin-bottom: 0;">
              <div class="form-group">
                <label class="form-label" for="order-wash-mode">Wash Setting</label>
                <select id="order-wash-mode" onchange="calculateOrderTotal()">
                  <option value="normal">Standard Wash (₱60)</option>
                  <option value="quick">Quick Wash (₱50)</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label" for="order-dry-mode">Dry Setting</label>
                <select id="order-dry-mode" onchange="calculateOrderTotal()">
                  <option value="normal">Standard Dry (₱60)</option>
                  <option value="quick">Quick Dry (₱50)</option>
                </select>
              </div>
            </div>
  
            <div class="grid-cols-2" style="gap: 12px; margin-bottom: 0;">
              <div class="form-group">
                <label class="form-label" for="order-product-amount">Add-on Products (₱)</label>
                <input type="number" id="order-product-amount" value="0" min="0" onchange="calculateOrderTotal()" placeholder="Detergent, etc.">
              </div>
              <div class="form-group">
                <label class="form-label" for="order-service-amount">Add-on Services (₱)</label>
                <input type="number" id="order-service-amount" value="0" min="0" onchange="calculateOrderTotal()" placeholder="Folding, etc.">
              </div>
            </div>
  
            <div class="form-group">
              <label class="form-label">Payment Method</label>
              <div class="grid-cols-2" style="gap: var(--space-sm);">
                <label class="btn btn-secondary" style="padding: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;">
                  <input type="radio" name="order-payment" value="cash" checked style="width: auto; min-height: auto;" onchange="updatePaymentSelectUI()"> Cash
                </label>
                <label class="btn btn-secondary" style="padding: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;">
                  <input type="radio" name="order-payment" value="gcash" style="width: auto; min-height: auto;" onchange="updatePaymentSelectUI()"> GCash
                </label>
              </div>
            </div>
  
            <div class="calc-box" style="margin-top: 1rem; padding: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm);">
              <div style="display: flex; justify-content: space-between; font-weight: 700;">
                <span>Total Est. Price:</span>
                <span id="order-total-price" style="color: var(--accent); font-size: 1.15rem;">₱0.00</span>
              </div>
            </div>
  
            <button class="btn btn-primary" type="submit" style="width: 100%; margin-top: 1rem;">
              <span>Create & Print Receipt</span>
              <span class="btn-icon-circle">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              </span>
            </button>
          </form>
        </div>
      </div>
    </div>
  `;
  
  loadOpenOrders();
  loadCustomersList();
}

async function loadOpenOrders() {
  const container = document.getElementById("open-orders-container");
  if (!container) return;

  try {
    const res = await apiFetch("/dashboard/job-orders/open");
    openOrdersList = res.job_orders || [];
    document.getElementById("open-orders-count").textContent = `${openOrdersList.length} Open`;
    renderOpenOrders();
  } catch (err) {
    container.innerHTML = `<p style="color: var(--text-secondary); text-align: center; padding: 1rem;">Failed to fetch active orders.</p>`;
  }
}

async function loadCustomersList() {
  try {
    const res = await apiFetch("/dashboard/customers?limit=100");
    customerList = res.customers || [];
    const datalist = document.getElementById("customer-datalist");
    if (datalist) {
      datalist.innerHTML = customerList.map(c => `<option value="${c.name}">${c.phone || ''}</option>`).join('');
    }
  } catch (e) {}
}

function renderOpenOrders() {
  const container = document.getElementById("open-orders-container");
  if (!container) return;

  if (openOrdersList.length === 0) {
    container.innerHTML = `<p style="color: var(--text-secondary); text-align: center; padding: 2rem;">No open orders found.</p>`;
    return;
  }

  container.innerHTML = openOrdersList.map(order => {
    const remainingWashes = parseInt(order.wash_qty || 0);
    const remainingDries = parseInt(order.dry_qty || 0);
    const totalWashes = parseInt(order.total_wash_qty || remainingWashes);
    const totalDries = parseInt(order.total_dry_qty || remainingDries);

    const washStatus = `${totalWashes - remainingWashes}/${totalWashes} Wash`;
    const dryStatus = `${totalDries - remainingDries}/${totalDries} Dry`;

    // Filter available machines to suggest activation
    const claimActions = [];
    if (remainingWashes > 0) {
      claimActions.push(`
        <button class="btn btn-primary" onclick="claimOrderCyclePrompt('${order.id}', 'washer')" style="padding: 6px 12px; min-height: 38px; font-size: 11px;">
          Start Wash (${remainingWashes})
        </button>
      `);
    }
    if (remainingDries > 0) {
      claimActions.push(`
        <button class="btn btn-success" onclick="claimOrderCyclePrompt('${order.id}', 'dryer')" style="padding: 6px 12px; min-height: 38px; font-size: 11px;">
          Start Dry (${remainingDries})
        </button>
      `);
    }

    return `
      <div class="list-item" id="order-card-${order.id}">
        <div class="list-item-meta" style="flex: 1;">
          <span class="list-item-title">${order.customer_name}</span>
          <span class="list-item-desc">
            JO #${order.job_order_no} | ${order.customer_phone || 'No Phone'}
          </span>
          <div style="display: flex; gap: 8px; margin-top: 6px;">
            <span class="badge badge-idle">${washStatus}</span>
            <span class="badge badge-idle">${dryStatus}</span>
            <span class="badge badge-simulated">${order.paid_by_gcash ? 'GCash' : 'Cash'}</span>
          </div>
        </div>
        
        <div style="display: flex; gap: 6px; align-items: center;">
          ${claimActions.join('')}
          <button class="btn btn-secondary" onclick="deleteJobOrder('${order.id}')" style="padding: 8px; min-height: 38px; color: oklch(0.60 0.15 20);">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function filterOpenOrders() {
  const query = document.getElementById("order-search").value.toLowerCase();
  document.querySelectorAll("#open-orders-container .list-item").forEach(item => {
    const text = item.textContent.toLowerCase();
    item.style.display = text.includes(query) ? "flex" : "none";
  });
}

function calculateOrderTotal() {
  const wQty = parseInt(document.getElementById("order-wash-qty").value || 0);
  const dQty = parseInt(document.getElementById("order-dry-qty").value || 0);
  const wMode = document.getElementById("order-wash-mode").value;
  const dMode = document.getElementById("order-dry-mode").value;
  const pAmt = parseFloat(document.getElementById("order-product-amount").value || 0);
  const sAmt = parseFloat(document.getElementById("order-service-amount").value || 0);

  const washPrice = wMode === 'quick' ? 50 : 60;
  const dryPrice = dMode === 'quick' ? 50 : 60;

  const total = (wQty * washPrice) + (dQty * dryPrice) + pAmt + sAmt;
  document.getElementById("order-total-price").textContent = `₱${total.toFixed(2)}`;
}

function updatePaymentSelectUI() {
  // Can be used to change container classes if needed for committed visual focus
}

async function createNewJobOrder(event) {
  event.preventDefault();
  
  if (!globalShiftState) {
    showNotification("Shift Closed", "You must clock-in before taking new orders.", "error");
    return;
  }

  const name = document.getElementById("order-cust-name").value.trim();
  const phone = document.getElementById("order-cust-phone").value.trim() || null;
  const wQty = parseInt(document.getElementById("order-wash-qty").value || 0);
  const dQty = parseInt(document.getElementById("order-dry-qty").value || 0);
  const wMode = document.getElementById("order-wash-mode").value;
  const dMode = document.getElementById("order-dry-mode").value;
  const pAmt = parseInt(document.getElementById("order-product-amount").value || 0);
  const sAmt = parseInt(document.getElementById("order-service-amount").value || 0);
  const payment = document.querySelector('input[name="order-payment"]:checked').value;

  if (wQty === 0 && dQty === 0) {
    showNotification("Input Error", "Please add at least one Wash or Dry cycle.", "error");
    return;
  }

  try {
    const res = await apiFetch("/dashboard/job-orders", {
      method: "POST",
      body: JSON.stringify({
        customer: { name, phone },
        location_id: CONFIG.LOCATION_ID,
        wash_qty: wQty,
        dry_qty: dQty,
        wash_mode: wMode,
        dry_mode: dMode,
        product_qty: pAmt > 0 ? 1 : 0,
        service_qty: sAmt > 0 ? 1 : 0,
        product_amount: pAmt,
        service_amount: sAmt,
        paid_by_gcash: payment === "gcash"
      })
    });

    if (res.status === "ok") {
      showNotification("Order Logged", `Job Order successfully recorded.`, "success");
      
      // Auto-trigger receipt printing
      const orderId = res.job_order ? res.job_order.id : '';
      if (orderId) {
        printThermalReceipt(orderId);
      }
      
      document.getElementById("new-order-form").reset();
      calculateOrderTotal();
      loadOpenOrders();
      loadCustomersList();
    }
  } catch (err) {}
}

async function deleteJobOrder(orderId) {
  if (!confirm("Are you sure you want to delete this open job order? This action cannot be undone.")) {
    return;
  }

  try {
    const res = await apiFetch(`/dashboard/job-orders/${orderId}`, {
      method: "DELETE"
    });

    if (res.status === "ok") {
      showNotification("Order Removed", "Order deleted from system database.", "success");
      loadOpenOrders();
    }
  } catch (e) {}
}

// Interactive activation handler: asks which machine to claim
async function claimOrderCyclePrompt(orderId, type) {
  // Fetch active machines of the correct type that are IDLE
  try {
    const machinesData = await apiFetch("/machines");
    const available = machinesData.filter(m => m.type === type && m.status === 'IDLE');

    if (available.length === 0) {
      showNotification("Busy Nodes", `No idle ${type}s available in the network.`, "error");
      return;
    }

    // Inline selection overlay to prevent traditional modular blocking dialogs
    const targetCard = document.getElementById(`order-card-${orderId}`);
    if (!targetCard) return;

    const originalControls = targetCard.innerHTML;
    
    targetCard.innerHTML = `
      <div style="width: 100%; display: flex; flex-direction: column; gap: 8px;">
        <span class="form-label" style="color: var(--accent);">Select ${type}:</span>
        <div style="display: flex; gap: 4px; flex-wrap: wrap;">
          ${available.map(m => `
            <button class="btn btn-secondary" onclick="executeClaimCycle('${orderId}', '${m.id}')" style="padding: 6px 12px; min-height: 38px; font-size: 11px;">
              ${m.name}
            </button>
          `).join('')}
          <button class="btn btn-danger" onclick="cancelClaimPrompt('${orderId}')" style="padding: 6px 12px; min-height: 38px; font-size: 11px;">
            Cancel
          </button>
        </div>
      </div>
    `;

    // Cache the original controls locally to restore on cancel
    targetCard.setAttribute("data-restore", encodeURIComponent(originalControls));
  } catch(e) {}
}

function cancelClaimPrompt(orderId) {
  const targetCard = document.getElementById(`order-card-${orderId}`);
  if (!targetCard) return;
  const original = decodeURIComponent(targetCard.getAttribute("data-restore") || "");
  if (original) {
    targetCard.innerHTML = original;
    targetCard.removeAttribute("data-restore");
  }
}

async function executeClaimCycle(orderId, machineId) {
  try {
    const res = await apiFetch(`/machines/${machineId}/start`, {
      method: "POST",
      body: JSON.stringify({
        job_order_id: orderId,
        location_id: CONFIG.LOCATION_ID
      })
    });

    if (res.status === "COMPLETED" || res.status === "SIMULATED") {
      showNotification("Cycle Started", `Activated ${res.machine || machineId} successfully.`, "success");
      loadOpenOrders();
    }
  } catch(e) {}
}

// Print Thermal receipt action
function printThermalReceipt(orderId) {
  const printUrl = `receipt.html?order_id=${orderId}`;
  const printWindow = window.open(printUrl, "_blank", "width=320,height=600");
  if (printWindow) {
    // Focus and print happens inside receipt.html
  } else {
    showNotification("Popup Blocked", "Please allow popups to automatically print receipts.", "error");
  }
}
