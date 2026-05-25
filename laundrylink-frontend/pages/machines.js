// pages/machines.js
// LaundryLink — Machines Tab View Controller

let machinesList = [];
let machinesPollInterval = null;
let countdownInterval = null;
let selectedMachines = new Set(); // For bulk selections

function clearMachinesIntervals() {
  clearInterval(machinesPollInterval);
  clearInterval(countdownInterval);
}

function renderMachinesPage() {
  document.getElementById("content").innerHTML = `
    <div class="open-orders-header">
      <h2 class="page-title">Machine Control Panel</h2>
      <div class="filter-buttons">
        <button class="btn btn-secondary" onclick="runBulkLifeCheck()">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
          Life Check
        </button>
        <button class="btn btn-primary" onclick="loadMachinesGrid(true)">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89H18v3H4"></path></svg>
          Refresh Grid
        </button>
      </div>
    </div>

    <!-- Machine Categories and Grids -->
    <div class="list-group" id="machine-grids-container">
      <div class="initial-loader">
        <div class="spinner"></div>
        <p>Polling operational nodes...</p>
      </div>
    </div>
  `;
  
  loadMachinesGrid();
  
  // Set auto poll status every 20 seconds
  clearMachinesIntervals();
  machinesPollInterval = setInterval(() => loadMachinesGrid(false), 20000);
}

async function loadMachinesGrid(showLoader = false) {
  const container = document.getElementById("machine-grids-container");
  if (showLoader && container) {
    container.innerHTML = `
      <div class="initial-loader">
        <div class="spinner"></div>
        <p>Refreshing machine grid...</p>
      </div>
    `;
  }

  try {
    const data = await apiFetch("/machines");
    machinesList = data || [];
    renderGrids();
  } catch (err) {
    if (container) {
      container.innerHTML = `
        <div class="card" style="text-align: center; padding: 2rem;">
          <svg width="48" height="48" fill="none" stroke="oklch(0.60 0.15 20)" stroke-width="2" viewBox="0 0 24 24" style="margin: 0 auto 1rem;"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
          <h3 class="card-title">Failed to load machines</h3>
          <p style="color: var(--text-secondary); margin: 0.5rem 0 1.5rem;">Could not establish connection to Raspberry Pi.</p>
          <button class="btn btn-primary" onclick="loadMachinesGrid(true)">Retry Connection</button>
        </div>
      `;
    }
  }
}

function renderGrids() {
  const container = document.getElementById("machine-grids-container");
  if (!container) return;

  if (machinesList.length === 0) {
    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 3rem;">
        <p style="color: var(--text-secondary);">No machines registered in the local network.</p>
      </div>
    `;
    return;
  }

  // Filter into washers and dryers
  const washers = machinesList.filter(m => m.type === 'washer');
  const dryers = machinesList.filter(m => m.type === 'dryer');

  let htmlContent = '';

  if (washers.length > 0) {
    htmlContent += `
      <div class="card">
        <div class="card-header-row">
          <h3 class="card-title">Washers</h3>
          <span class="badge badge-idle">${washers.length} Nodes</span>
        </div>
        <div class="machine-grid">
          ${washers.map(m => getMachineCardHtml(m)).join('')}
        </div>
      </div>
    `;
  }

  if (dryers.length > 0) {
    htmlContent += `
      <div class="card">
        <div class="card-header-row">
          <h3 class="card-title">Dryers</h3>
          <span class="badge badge-idle">${dryers.length} Nodes</span>
        </div>
        <div class="machine-grid">
          ${dryers.map(m => getMachineCardHtml(m)).join('')}
        </div>
      </div>
    `;
  }

  container.innerHTML = htmlContent;
  
  // Initialize dynamic active countdowns
  initCountdowns();
}

function getMachineCardHtml(m) {
  const isBusy = m.status === 'BUSY';
  const isOffline = m.status === 'OFFLINE';
  
  const statusBadge = isBusy 
    ? '<span class="badge badge-busy">RUNNING</span>' 
    : isOffline 
      ? '<span class="badge badge-offline">OFFLINE</span>' 
      : '<span class="badge badge-idle">IDLE</span>';

  const iconClass = m.type === 'washer' ? 'washer' : 'dryer';
  const iconPulse = isBusy ? 'busy-pulse' : '';
  const isSelected = selectedMachines.has(m.id) ? 'selected' : '';

  // Icon SVG
  const machineIcon = m.type === 'washer' 
    ? `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>`
    : `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"></circle><path d="M12 9v6l4 2"></path></svg>`;

  let actionsHtml = '';
  if (isOffline) {
    actionsHtml = `<button class="btn btn-secondary" onclick="lifeCheckSingle('${m.id}', this)">Reconnect</button>`;
  } else if (isBusy) {
    actionsHtml = `<button class="btn btn-danger" onclick="stopMachineCycle('${m.id}', this)">STOP CYCLE</button>`;
  } else {
    const stdLabel = m.type === 'washer' ? 'STD Wash (₱60)' : 'STD Dry (₱60)';
    const qkLabel = m.type === 'washer' ? 'Quick (₱50)' : 'Add Time (₱15)';
    
    actionsHtml = `
      <button class="btn btn-primary" onclick="startMachineDirect('${m.id}', 'standard', this)">${stdLabel}</button>
      <button class="btn btn-secondary" onclick="startMachineDirect('${m.id}', 'quick', this)">${qkLabel}</button>
    `;
  }

  // Calculate remaining seconds if busy
  let remainingTimeStr = '';
  if (isBusy && m.run_ends_at) {
    const ends = new Date(m.run_ends_at.replace(' ', 'T')).getTime();
    const now = new Date().getTime();
    const diff = Math.max(0, Math.floor((ends - now) / 1000));
    
    if (diff > 0) {
      const mins = Math.floor(diff / 60).toString().padStart(2, '0');
      const secs = (diff % 60).toString().padStart(2, '0');
      remainingTimeStr = `${mins}:${secs}`;
    }
  }

  return `
    <div class="machine-card ${isBusy ? 'running' : ''} ${isOffline ? 'offline' : ''} ${isSelected}" id="machine-card-${m.id}" data-id="${m.id}">
      <div class="machine-card-header">
        <div class="machine-name-block">
          <span class="machine-name">${m.name}</span>
          <span class="machine-type">${m.type} — ${m.machine_function || 'standard'}</span>
        </div>
        <div class="machine-icon-wrapper ${iconClass} ${iconPulse}">
          ${machineIcon}
        </div>
      </div>
      
      <div class="machine-card-status-row">
        ${statusBadge}
      </div>

      <div class="machine-countdown" id="countdown-${m.id}" data-ends="${m.run_ends_at || ''}">
        ${remainingTimeStr}
      </div>

      <div class="machine-card-actions">
        ${actionsHtml}
      </div>
    </div>
  `;
}

function initCountdowns() {
  clearInterval(countdownInterval);
  countdownInterval = setInterval(() => {
    document.querySelectorAll(".machine-countdown").forEach(el => {
      const endsStr = el.getAttribute("data-ends");
      if (!endsStr) return;

      const ends = new Date(endsStr.replace(' ', 'T')).getTime();
      const now = new Date().getTime();
      const diff = Math.max(0, Math.floor((ends - now) / 1000));

      if (diff > 0) {
        const mins = Math.floor(diff / 60).toString().padStart(2, '0');
        const secs = (diff % 60).toString().padStart(2, '0');
        el.textContent = `${mins}:${secs}`;
      } else {
        el.textContent = "";
        // Auto poll grid to clear finished state
        if (el.textContent === "00:01") {
          setTimeout(() => loadMachinesGrid(false), 2000);
        }
      }
    });
  }, 1000);
}

// Single Action: Start machine
async function startMachineDirect(machineId, mode, btn) {
  if (!globalShiftState) {
    showNotification("Shift Closed", "Attendant must time-in before starting machines.", "error");
    return;
  }

  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Pulse...";

  try {
    const res = await apiFetch("/dashboard/machine/start", {
      method: "POST",
      body: JSON.stringify({
        machine_id: machineId,
        location_id: CONFIG.LOCATION_ID,
        activation_mode: mode,
        paid_by_gcash: false // Direct physical cash transactions default
      })
    });

    if (res.status === "COMPLETED" || res.status === "SIMULATED") {
      showNotification("Activated Successfully", `Machine ${res.machine || machineId} has started.`, "success");
      loadMachinesGrid(false);
    } else {
      showNotification("Failure", res.error || "Failed to start machine.", "error");
    }
  } catch (err) {
    // Error is handled by apiFetch wrapper notification
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// Single Action: Stop machine
async function stopMachineCycle(machineId, btn) {
  if (!confirm("Are you absolutely sure you want to STOP this machine? This clears the active run window.")) {
    return;
  }

  btn.disabled = true;
  btn.textContent = "Stopping...";

  try {
    const res = await apiFetch(`/machines/${machineId}/stop`, {
      method: "POST",
      body: JSON.stringify({
        location_id: CONFIG.LOCATION_ID
      })
    });

    if (res.status === "STOPPED") {
      showNotification("Machine Stopped", `Stopped ${res.machine || machineId}.`, "success");
      loadMachinesGrid(false);
    } else {
      showNotification("Failure", res.error || "Failed to stop machine.", "error");
    }
  } catch (err) {
    // Errors handled in fetch
  } finally {
    btn.disabled = false;
  }
}

// Reconnect/Lifecheck single machine
async function lifeCheckSingle(machineId, btn) {
  btn.disabled = true;
  btn.textContent = "Checking...";

  try {
    const res = await apiFetch(`/machines/${machineId}/life`, {
      method: "POST"
    });

    if (res.status === "ALIVE") {
      showNotification("Online", `${res.machine} is active: ${res.message || 'Ready'}`, "success");
      loadMachinesGrid(false);
    } else {
      showNotification("Offline Node", res.error || "Machine unreachable.", "error");
    }
  } catch (err) {
    // Handled by fetch
  } finally {
    btn.disabled = false;
  }
}

// Bulk Actions: Reconnect all offline nodes
async function runBulkLifeCheck() {
  showNotification("System Scan", "Initiating bulk ping to all registered node IPs...", "info");
  
  const offlineList = machinesList.filter(m => m.status === 'OFFLINE');
  if (offlineList.length === 0) {
    showNotification("Status Clear", "All machines currently online.", "success");
    return;
  }

  let successCount = 0;
  for (const m of offlineList) {
    try {
      const res = await fetch(`${CONFIG.PI_BASE_URL}/machines/${m.id}/life`, { method: "POST" });
      const data = await res.json();
      if (data.status === "ALIVE") successCount++;
    } catch (e) {}
  }

  showNotification("Scan Complete", `Successfully reconnected ${successCount}/${offlineList.length} offline nodes.`, "success");
  loadMachinesGrid(false);
}
