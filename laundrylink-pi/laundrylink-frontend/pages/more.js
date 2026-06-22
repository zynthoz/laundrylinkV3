// pages/more.js
// LaundryLink — More Tab (Shifts, Inventory & Admin Settings)

let employeesList = [];
let productsList = [];
let servicesList = [];
let isAdminUnlocked = false;

function renderMorePage() {
  document.getElementById("content").innerHTML = `
    <div class="split-layout-admin">
      
      <!-- LEFT COLUMN: SHIFTS & CLOCKING -->
      <div class="list-group">
        
        <!-- Employee Clocking Card -->
        <div class="machine-card-shell" id="shift-clock-card">
          <div class="machine-card-inner" style="min-height: auto;">
            <div class="card-header-row">
              <h3 class="card-title">Attendant Shift Manager</h3>
            </div>
            
            <div id="shift-manager-content">
              <div class="initial-loader"><div class="spinner"></div></div>
            </div>
          </div>
        </div>

        <!-- Inventory List Card -->
        <div class="machine-card-shell">
          <div class="machine-card-inner" style="min-height: auto;">
            <div class="card-header-row">
              <h3 class="card-title">Inventory Catalog</h3>
              <span class="badge badge-idle" id="inv-stock-badge">0 Items</span>
            </div>
            
            <div class="table-container" style="max-height: 380px;">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Stock</th>
                    <th>Boxes</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody id="inventory-table-body">
                  <tr>
                    <td colspan="4" style="text-align: center; color: var(--text-muted);">Loading catalog...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </div>

      <!-- RIGHT COLUMN: ADMIN CONTROLS (PIN LOCKED) -->
      <div class="machine-card-shell" id="admin-settings-card">
        <div class="machine-card-inner" style="min-height: auto;">
          <div class="card-header-row">
            <h3 class="card-title">System Administration</h3>
            <span class="badge badge-offline" id="admin-lock-status">LOCKED</span>
          </div>

          <div id="admin-panel-content">
            <!-- Lock screen form -->
            <form id="admin-lock-form" onsubmit="unlockAdminPanel(event)" style="padding: 1.5rem 0; text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%;">
              <svg width="40" height="40" fill="none" stroke="var(--text-muted)" stroke-width="2" viewBox="0 0 24 24" style="margin-bottom: 1rem;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
              <div class="form-group" style="max-width: 240px; margin: 0 auto 1.5rem; width: 100%;">
                <label class="form-label" for="adm-pin">Enter Admin Access PIN</label>
                <input type="password" id="adm-pin" maxlength="6" required placeholder="••••" style="text-align: center; font-size: 1.5rem; letter-spacing: 0.2em; min-height: 48px; border-radius: 12px;">
              </div>
              <button class="btn btn-primary" type="submit" style="min-width: 160px;">
                <span>Unlock Settings</span>
                <span class="btn-icon-circle">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </span>
              </button>
            </form>
          </div>
        </div>
      </div>

    </div>
  `;

  renderShiftControls();
  loadInventoryCatalog();
  
  if (isAdminUnlocked) {
    renderAdminFeatures();
  }
}

// 1. SHIFT CONTROLS
async function renderShiftControls() {
  const container = document.getElementById("shift-manager-content");
  if (!container) return;

  try {
    const activeRes = await fetch(`${CONFIG.PI_BASE_URL}/shifts/active`);
    const activeData = await activeRes.json();
    const activeShift = activeData.active_shift;

    if (activeShift) {
      container.innerHTML = `
        <div style="background: var(--accent-subtle); padding: 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-light); margin-bottom: 1rem;">
          <p style="font-weight: 700; color: var(--accent); margin-bottom: 2px;">Clocked In Attendant:</p>
          <p style="font-size: 1.1rem; font-weight: 800;">${activeShift.display_name}</p>
          <p style="font-size: var(--text-xs); color: var(--text-secondary); margin-top: 4px;">Time In: ${activeShift.started_at}</p>
        </div>
        
        <form onsubmit="clockOutEmployee(event)">
          <button class="btn btn-danger" type="submit" style="width: 100%;">
            Time-Out / Close Shift
          </button>
        </form>
      `;
    } else {
      // Load list of active employees
      const empRes = await fetch(`${CONFIG.PI_BASE_URL}/employees?active_only=true`);
      const empData = await empRes.json();
      employeesList = empData.employees || [];

      container.innerHTML = `
        <form id="clockin-form" onsubmit="clockInEmployee(event)">
          <div class="form-group">
            <label class="form-label" for="select-employee">Select Attendant</label>
            <select id="select-employee" required>
              <option value="">-- Choose Name --</option>
              ${employeesList.map(e => `<option value="${e.id}">${e.display_name}</option>`).join('')}
            </select>
          </div>
          
          <div class="form-group">
            <label class="form-label" for="emp-pin">Credentials PIN</label>
            <input type="password" id="emp-pin" required maxlength="6" placeholder="••••" style="text-align: center; letter-spacing: 0.1em;">
          </div>
          
          <button class="btn btn-success" type="submit" style="width: 100%;">
            Time-In / Open Shift
          </button>
        </form>
      `;
    }
  } catch (err) {
    container.innerHTML = `<p style="color: var(--text-secondary); text-align: center;">Connection offline.</p>`;
  }
}

async function clockInEmployee(e) {
  e.preventDefault();
  
  const empId = document.getElementById("select-employee").value;
  const pin = document.getElementById("emp-pin").value;

  try {
    const res = await apiFetch("/shifts/time-in", {
      method: "POST",
      body: JSON.stringify({
        employee_id: empId,
        pin: pin,
        confirm_handover: true,
        location_id: CONFIG.LOCATION_ID
      })
    });

    if (res.status === "ok") {
      showNotification("Clocked In", `Shift opened for ${res.shift.display_name}.`, "success");
      loadShiftIndicator(); // Update top bar
      renderShiftControls();
    }
  } catch(err) {}
}

async function clockOutEmployee(e) {
  e.preventDefault();
  
  if (!confirm("Are you sure you want to clock out and close your operational shift?")) {
    return;
  }

  try {
    const res = await apiFetch("/shifts/time-out", {
      method: "POST",
      body: JSON.stringify({
        location_id: CONFIG.LOCATION_ID
      })
    });

    if (res.status === "ok") {
      showNotification("Clocked Out", "Shift closed successfully.", "success");
      loadShiftIndicator();
      renderShiftControls();
    }
  } catch(err) {}
}

// 2. INVENTORY CATALOG
async function loadInventoryCatalog() {
  const tableBody = document.getElementById("inventory-table-body");
  const badge = document.getElementById("inv-stock-badge");
  if (!tableBody) return;

  try {
    const res = await apiFetch("/catalog/products?active_only=true");
    productsList = res.products || [];
    badge.textContent = `${productsList.length} Items`;

    if (productsList.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No products in catalog.</td></tr>`;
      return;
    }

    tableBody.innerHTML = productsList.map(p => {
      const isLow = p.stock_on_hand <= p.low_stock_threshold;
      const stockColor = isLow ? "oklch(0.60 0.15 20)" : "inherit";

      return `
        <tr>
          <td>
            <div style="font-weight: 700;">${p.name}</div>
            <div style="font-size: 11px; color: var(--text-muted);">₱${p.unit_price} / unit</div>
          </td>
          <td style="font-weight: 700; color: ${stockColor}; font-variant-numeric: tabular-nums;">
            ${p.stock_on_hand}
          </td>
          <td style="font-variant-numeric: tabular-nums;">
            ${p.boxes_on_hand || 0}
          </td>
          <td>
            <button class="btn btn-secondary" onclick="triggerRestockPrompt('${p.id}', '${p.name}')" style="min-height: 36px; padding: 4px 8px; font-size: 11px;">
              Restock
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {}
}

function triggerRestockPrompt(productId, name) {
  const qty = prompt(`Enter restock unit quantity to ADD for ${name}:`, "20");
  if (qty === null) return;
  
  const parsed = parseInt(qty);
  if (isNaN(parsed) || parsed <= 0) {
    showNotification("Input Error", "Please enter a valid positive number.", "error");
    return;
  }

  executeRestock(productId, parsed);
}

async function executeRestock(productId, quantity) {
  if (!globalShiftState) {
    showNotification("Shift Closed", "Attendant must time-in before inventory modifications.", "error");
    return;
  }

  try {
    const res = await apiFetch(`/catalog/products/${productId}/stock`, {
      method: "POST",
      body: JSON.stringify({
        quantity: quantity,
        location_id: CONFIG.LOCATION_ID
      })
    });

    if (res.status === "ok") {
      showNotification("Restock Logged", `Added ${quantity} units to ${res.product_name}.`, "success");
      loadInventoryCatalog();
    }
  } catch(e) {}
}

// 3. ADMIN ACCESS & SETTINGS
async function unlockAdminPanel(e) {
  e.preventDefault();
  const pin = document.getElementById("adm-pin").value;

  try {
    // Call the verify pin route using standard apiFetch
    const res = await apiFetch("/dashboard/admin/verify-pin", {
      method: "POST",
      headers: {
        "X-Admin-Pin": pin // Send inside header matching route rules
      }
    });

    if (res.status === "ok") {
      isAdminUnlocked = true;
      sessionStorage.setItem("adm_pin", pin);
      
      const badge = document.getElementById("admin-lock-status");
      badge.textContent = "UNLOCKED";
      badge.className = "badge badge-success";
      
      showNotification("Access Granted", "Admin privilege successfully authenticated.", "success");
      renderAdminFeatures();
    }
  } catch (err) {
    showNotification("Access Denied", "Incorrect Admin Authorization PIN.", "error");
  }
}

function renderAdminFeatures() {
  const container = document.getElementById("admin-panel-content");
  if (!container) return;

  const savedPin = sessionStorage.getItem("adm_pin") || "";

  container.innerHTML = `
    <!-- Settings options tabs -->
    <div style="display: flex; flex-direction: column; gap: var(--space-md);">
      
      <!-- Bulk Pricing form -->
      <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-light);">
        <h4 style="font-weight: 700; margin-bottom: var(--space-sm);">Bulk Pricing Manager</h4>
        <form onsubmit="executeBulkPricing(event)">
          <div class="grid-cols-2" style="gap: 12px; margin-bottom: 0;">
            <div class="form-group">
              <label class="form-label" for="bulk-type">Node Type</label>
              <select id="bulk-type">
                <option value="all">All Machines</option>
                <option value="washer">Washers Only</option>
                <option value="dryer">Dryers Only</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label" for="bulk-price">New Price (₱)</label>
              <input type="number" id="bulk-price" min="0" required placeholder="60">
            </div>
          </div>
          <button class="btn btn-primary" type="submit" style="width: 100%;">
            Apply Price Adjustment
          </button>
        </form>
      </div>

      <!-- Employee PIN Rotation manager -->
      <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-light);">
        <h4 style="font-weight: 700; margin-bottom: var(--space-sm);">Receipt Template Customizer</h4>
        <p style="font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: var(--space-sm);">
          Reorder/Format the operational printing block outputs from physical nodes.
        </p>
        <button class="btn btn-secondary" onclick="openReceiptFormatter()" style="width: 100%;">
          Open Receipt Customizer Form
        </button>
      </div>

      <!-- Lock back settings button -->
      <button class="btn btn-danger" onclick="lockAdminPanel()" style="width: 100%; min-height: 44px; margin-top: var(--space-sm);">
        Lock Admin Session
      </button>

    </div>
  `;
}

function lockAdminPanel() {
  isAdminUnlocked = false;
  sessionStorage.removeItem("adm_pin");
  renderMorePage();
}

async function executeBulkPricing(e) {
  e.preventDefault();
  
  const type = document.getElementById("bulk-type").value;
  const price = parseInt(document.getElementById("bulk-price").value || 0);
  const pin = sessionStorage.getItem("adm_pin") || "";

  try {
    const res = await apiFetch("/machines/pricing/bulk", {
      method: "POST",
      headers: {
        "X-Admin-Pin": pin
      },
      body: JSON.stringify({
        machine_type: type,
        vend_price: price
      })
    });

    if (res.status === "ok") {
      showNotification("Success", `Pricing updated for all ${type}s to ₱${price}.`, "success");
    }
  } catch(err) {}
}

// Visual receipt configuration
async function openReceiptFormatter() {
  const pin = sessionStorage.getItem("adm_pin") || "";
  
  try {
    // Fetch active print format config
    const res = await apiFetch("/dashboard/settings/receipt-format", {
      method: "GET",
      headers: {
        "X-Admin-Pin": pin
      }
    });
    
    // Render custom formatter modal beautifully inline inside the panel content
    const container = document.getElementById("admin-panel-content");
    if (!container) return;

    container.innerHTML = `
      <div style="background: var(--bg); padding: 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-light);">
        <h4 style="font-weight: 700; margin-bottom: var(--space-sm);">Receipt Sections Customizer</h4>
        
        <form onsubmit="saveReceiptFormatter(event)">
          <div class="form-group">
            <label class="form-label" for="cfg-shop-name">Receipt Shop Header Name</label>
            <input type="text" id="cfg-shop-name" value="${res.shop_name || 'LaundryLink'}" required>
          </div>
          
          <div class="form-group">
            <label class="form-label">Active Printed Sections</label>
            <div style="display: flex; flex-direction: column; gap: 8px; margin: 0.5rem 0;">
              <label style="display: flex; align-items: center; gap: 8px; font-size: var(--text-sm);">
                <input type="checkbox" id="cfg-show-header" ${res["job_order.header_section"] !== false ? 'checked' : ''} style="width: auto; min-height: auto;"> Show Header & Slips Number
              </label>
              <label style="display: flex; align-items: center; gap: 8px; font-size: var(--text-sm);">
                <input type="checkbox" id="cfg-show-cust" ${res["job_order.customer_section"] !== false ? 'checked' : ''} style="width: auto; min-height: auto;"> Show Customer Metadata
              </label>
              <label style="display: flex; align-items: center; gap: 8px; font-size: var(--text-sm);">
                <input type="checkbox" id="cfg-show-unit" ${res["job_order.unit_price_section"] !== false ? 'checked' : ''} style="width: auto; min-height: auto;"> Show Unit Price Lines
              </label>
            </div>
          </div>
          
          <div class="grid-cols-2" style="gap: 8px;">
            <button class="btn btn-primary" type="submit">Save Template</button>
            <button class="btn btn-secondary" onclick="renderAdminFeatures()" type="button">Back</button>
          </div>
        </form>
      </div>
    `;
  } catch(e) {}
}

async function saveReceiptFormatter(e) {
  e.preventDefault();
  const pin = sessionStorage.getItem("adm_pin") || "";
  const shopName = document.getElementById("cfg-shop-name").value.trim();
  const showHeader = document.getElementById("cfg-show-header").checked;
  const showCust = document.getElementById("cfg-show-cust").checked;
  const showUnit = document.getElementById("cfg-show-unit").checked;

  try {
    const res = await apiFetch("/dashboard/settings/receipt-format", {
      method: "POST",
      headers: {
        "X-Admin-Pin": pin
      },
      body: JSON.stringify({
        shop_name: shopName,
        "job_order.header_section": showHeader,
        "job_order.customer_section": showCust,
        "job_order.unit_price_section": showUnit
      })
    });

    if (res.status === "ok") {
      showNotification("Success", "Thermal print format templates saved.", "success");
      renderAdminFeatures();
    }
  } catch(e) {}
}
