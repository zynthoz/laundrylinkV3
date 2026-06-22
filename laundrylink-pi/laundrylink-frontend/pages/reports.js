// pages/reports.js
// LaundryLink — Reports and Financial Analytics Tab

let reportsSummaryData = null;
let transactionList = [];
let currentReportType = "shift"; // "shift" or "day"
let selectedReportDate = new Date().toISOString().split('T')[0];
let activeAdjustmentTab = "expense"; // "expense" or "gcash"

function renderReportsPage() {
  document.getElementById("content").innerHTML = `
    <!-- Top Filter Bar -->
    <div class="open-orders-header" style="flex-wrap: wrap; gap: 12px; margin-bottom: var(--space-md);">
      <h2 class="page-title">Sales & Financials</h2>
      
      <div class="filter-bar" style="margin-bottom: 0;">
        <div class="grid-cols-2" style="display: inline-flex; gap: 4px;">
          <button class="btn btn-secondary ${currentReportType === 'shift' ? 'btn-primary' : ''}" id="btn-report-shift" onclick="setReportType('shift')" style="padding: 0 16px; min-height: 44px;">
            Current Shift
          </button>
          <button class="btn btn-secondary ${currentReportType === 'day' ? 'btn-primary' : ''}" id="btn-report-day" onclick="setReportType('day')" style="padding: 0 16px; min-height: 44px;">
            Day Summary
          </button>
        </div>
        
        <input type="date" id="report-date-picker" value="${selectedReportDate}" onchange="setReportDate(this.value)" style="width: auto; min-height: 44px; padding: 6px 12px;">
        
        <button class="btn btn-secondary" onclick="printReportPrompt()" style="min-height: 44px; padding: 0 14px;">
          <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h2m2 4h10a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2zm8-12V5a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v4h10z"></path></svg>
        </button>
      </div>
    </div>

    <!-- Analytics Dashboard Metrics -->
    <div class="analytics-summary-row" id="reports-metrics-grid">
      <div class="stat-card">
        <span class="stat-card-label">Gross Collected</span>
        <span class="stat-card-value" id="rep-gross">₱0.00</span>
      </div>
      <div class="stat-card">
        <span class="stat-card-label">Net Sales</span>
        <span class="stat-card-value" id="rep-net" style="color: var(--accent);">₱0.00</span>
      </div>
      <div class="stat-card">
        <span class="stat-card-label">Total Expenses</span>
        <span class="stat-card-value" id="rep-expenses" style="color: oklch(0.60 0.15 20);">₱0.00</span>
      </div>
      <div class="stat-card">
        <span class="stat-card-label">Cash In Drawer</span>
        <span class="stat-card-value" id="rep-cash">₱0.00</span>
      </div>
      <div class="stat-card">
        <span class="stat-card-label">GCash Revenue</span>
        <span class="stat-card-value" id="rep-gcash" style="color: oklch(0.62 0.17 145);">₱0.00</span>
      </div>
    </div>

    <!-- Two Column Breakdown -->
    <div class="split-layout-reports">
      
      <!-- LEFT COLUMN: Transactions Log Card -->
      <div class="machine-card-shell" style="height: 100%; display: flex; flex-direction: column;">
        <div class="machine-card-inner" style="flex: 1; min-height: auto; display: flex; flex-direction: column; justify-content: flex-start; padding: var(--space-md);">
          <div class="card-header-row" style="margin-bottom: var(--space-md);">
            <h3 class="card-title">Recent Transactions Log</h3>
            <span class="badge badge-idle" id="rep-tx-count">0 Sales</span>
          </div>
          
          <div class="table-container" style="flex: 1; overflow: auto; min-height: 380px;">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Machine</th>
                  <th>Customer</th>
                  <th>Method</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody id="reports-transactions-body">
                <tr>
                  <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">No sales recorded yet.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- RIGHT COLUMN: Compact Unified Log Adjustments Card -->
      <div class="machine-card-shell" style="height: 100%; display: flex; flex-direction: column;">
        <div class="machine-card-inner" style="flex: 1; min-height: auto; display: flex; flex-direction: column; justify-content: flex-start; padding: var(--space-md);">
          <div class="tab-header" style="width: 100%;">
            <button class="tab-link active" id="tab-adj-expense" onclick="switchAdjustmentTab('expense')">Log Expense</button>
            <button class="tab-link" id="tab-adj-gcash" onclick="switchAdjustmentTab('gcash')">Log GCash</button>
          </div>
          
          <div style="flex: 1; display: flex; flex-direction: column; justify-content: center; width: 100%;">
            <!-- Tab 1: Expense Form -->
            <form id="expense-logging-form" onsubmit="logManualExpense(event)" style="display: flex; flex-direction: column; gap: var(--space-sm);">
              <div class="form-group" style="margin-bottom: var(--space-sm);">
                <label class="form-label" for="exp-name">Expense Item/Vendor *</label>
                <input type="text" id="exp-name" required placeholder="Water refill, soap, box tags, etc.">
              </div>
              
              <div class="grid-cols-2" style="gap: 12px; margin-bottom: var(--space-sm);">
                <div class="form-group" style="margin-bottom: 0;">
                  <label class="form-label" for="exp-amount">Total Cost (₱) *</label>
                  <input type="number" id="exp-amount" required min="1" placeholder="150">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                  <label class="form-label" for="exp-qty">Quantity</label>
                  <input type="number" id="exp-qty" min="1" placeholder="1">
                </div>
              </div>
              
              <button class="btn btn-danger" type="submit" style="width: 100%; margin-top: var(--space-sm);">
                <span>Record Shift Expense</span>
                <span class="btn-icon-circle">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </span>
              </button>
            </form>
            
            <!-- Tab 2: GCash Form (hidden by default) -->
            <form id="postcycle-logging-form" onsubmit="logPostCycleGcashTransfer(event)" style="display: none; flex-direction: column; gap: var(--space-sm);">
              <div class="form-group" style="margin-bottom: var(--space-sm);">
                <label class="form-label" for="pc-amount">GCash Transfer Amount (₱) *</label>
                <input type="number" id="pc-amount" required min="1" placeholder="60">
              </div>
              
              <div class="form-group" style="margin-bottom: var(--space-sm);">
                <label class="form-label" for="pc-note">Reference/Note *</label>
                <input type="text" id="pc-note" required placeholder="GCash received for Washer 2 standard">
              </div>
              
              <button class="btn btn-primary" type="submit" style="width: 100%; margin-top: var(--space-sm);">
                <span>Record GCash Adjustment</span>
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

  loadReportsSummary();
}

function switchAdjustmentTab(tab) {
  activeAdjustmentTab = tab;
  
  // Set tab active state classes
  document.getElementById("tab-adj-expense").classList.toggle("active", tab === "expense");
  document.getElementById("tab-adj-gcash").classList.toggle("active", tab === "gcash");

  // Show/Hide forms
  document.getElementById("expense-logging-form").style.display = tab === "expense" ? "flex" : "none";
  document.getElementById("postcycle-logging-form").style.display = tab === "gcash" ? "flex" : "none";
}

async function loadReportsSummary() {
  let endpoint = "/dashboard/summary/shift";
  if (currentReportType === "day") {
    endpoint = `/dashboard/summary/day?date=${selectedReportDate}`;
  } else if (CONFIG.LOCATION_ID) {
    endpoint += `?location_id=${CONFIG.LOCATION_ID}`;
  }

  try {
    const data = await apiFetch(endpoint);
    reportsSummaryData = data || {};
    updateReportsUI();
  } catch (err) {}
}

function updateReportsUI() {
  if (!reportsSummaryData) return;

  // Set metric widgets
  document.getElementById("rep-gross").textContent = `₱${(reportsSummaryData.gross_collected || 0).toFixed(2)}`;
  document.getElementById("rep-net").textContent = `₱${(reportsSummaryData.net_sales || 0).toFixed(2)}`;
  document.getElementById("rep-expenses").textContent = `₱${(reportsSummaryData.total_expenses || 0).toFixed(2)}`;
  document.getElementById("rep-cash").textContent = `₱${(reportsSummaryData.cash_collected || reportsSummaryData.cash_revenue || 0).toFixed(2)}`;
  document.getElementById("rep-gcash").textContent = `₱${(reportsSummaryData.gcash_revenue || reportsSummaryData.gcash_collected || 0).toFixed(2)}`;

  // Load Transactions Table
  const tableBody = document.getElementById("reports-transactions-body");
  const countBadge = document.getElementById("rep-tx-count");
  
  if (tableBody) {
    // Get transactions list
    const txList = reportsSummaryData.active_shift_transactions || reportsSummaryData.transactions || [];
    countBadge.textContent = `${txList.length} Sales`;

    if (txList.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2.5rem;">No sales recorded yet.</td></tr>`;
    } else {
      tableBody.innerHTML = txList.map(tx => {
        const dateObj = new Date(tx.started_at.replace(' ', 'T'));
        const timeStr = dateObj.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
        const isGcash = parseInt(tx.paid_by_gcash || 0) === 1;

        return `
          <tr>
            <td style="font-variant-numeric: tabular-nums;">${timeStr}</td>
            <td style="font-weight: 700;">${tx.machine_id}</td>
            <td>${tx.customer_name || 'Walk-in'}</td>
            <td>
              <span class="badge ${isGcash ? 'badge-simulated' : 'badge-idle'}">${isGcash ? 'GCash' : 'Cash'}</span>
            </td>
            <td style="font-weight: 700; font-variant-numeric: tabular-nums;">₱${parseFloat(tx.amount || 0).toFixed(2)}</td>
          </tr>
        `;
      }).join('');
    }
  }
}

function setReportType(type) {
  currentReportType = type;
  document.getElementById("btn-report-shift").className = `btn btn-secondary ${type === 'shift' ? 'btn-primary' : ''}`;
  document.getElementById("btn-report-day").className = `btn btn-secondary ${type === 'day' ? 'btn-primary' : ''}`;
  loadReportsSummary();
}

function setReportDate(date) {
  selectedReportDate = date;
  loadReportsSummary();
}

async function logManualExpense(event) {
  event.preventDefault();

  if (!globalShiftState) {
    showNotification("Shift Closed", "Must clock-in before logging expenses.", "error");
    return;
  }

  const name = document.getElementById("exp-name").value.trim();
  const amount = parseInt(document.getElementById("exp-amount").value || 0);
  const qty = parseInt(document.getElementById("exp-qty").value || 0) || null;

  try {
    const res = await apiFetch("/expenses/manual", {
      method: "POST",
      body: JSON.stringify({
        expense_name: name,
        amount: amount,
        quantity: qty,
        shift_id: globalShiftState.id,
        employee_id: globalShiftState.employee_id
      })
    });

    if (res.status === "ok") {
      showNotification("Expense Logged", `Logged ₱${amount} for ${name}.`, "success");
      document.getElementById("expense-logging-form").reset();
      loadReportsSummary();
    }
  } catch (err) {}
}

async function logPostCycleGcashTransfer(event) {
  event.preventDefault();

  if (!globalShiftState) {
    showNotification("Shift Closed", "Must clock-in before logging adjustments.", "error");
    return;
  }

  const amount = parseInt(document.getElementById("pc-amount").value || 0);
  const note = document.getElementById("pc-note").value.trim();

  try {
    const res = await apiFetch("/dashboard/post-cycle-payment/log", {
      method: "POST",
      body: JSON.stringify({
        gcash_amount: amount,
        note: note,
        location_id: CONFIG.LOCATION_ID
      })
    });

    if (res.status === "ok") {
      showNotification("Adjustment Logged", res.message || "GCash payment recorded successfully.", "success");
      document.getElementById("postcycle-logging-form").reset();
      loadReportsSummary();
    }
  } catch(err) {}
}

// Print report direct dispatch
async function printReportPrompt() {
  if (currentReportType === "shift") {
    if (!globalShiftState) {
      showNotification("Print Error", "No active shift report to print.", "error");
      return;
    }
    
    showNotification("Printing", "Sending shift sales summary to printer queue...", "info");
    
    try {
      const res = await apiFetch(`/reports/shift/${globalShiftState.id}/print`, {
        method: "POST",
        body: JSON.stringify({
          printed_by: globalShiftState.display_name
        })
      });
      if (res.status === "ok") {
        showNotification("Success", "Receipt dispatched to physical node printer.", "success");
      }
    } catch(e) {}
  } else {
    showNotification("Printing", `Sending daily summary receipt for ${selectedReportDate}...`, "info");
    try {
      const res = await apiFetch(`/reports/day/${selectedReportDate}/print`, {
        method: "POST",
        body: JSON.stringify({
          printed_by: globalShiftState ? globalShiftState.display_name : "Admin"
        })
      });
      if (res.status === "ok") {
        showNotification("Success", "Daily summary dispatch completed.", "success");
      }
    } catch(e) {}
  }
}
