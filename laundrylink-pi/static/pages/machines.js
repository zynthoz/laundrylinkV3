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

let currentFilter = 'all';

function renderMachinesPage() {
  const isAdmin = !!sessionStorage.getItem("adm_pin");

  document.getElementById("content").innerHTML = `
    <!-- Top Statistics Summary Ribbon -->
    <div class="stats-ribbon" id="stats-ribbon-container">
      ${isAdmin ? `
      <div class="stat-pill">
        <div class="stat-pill-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        </div>
        <div class="stat-pill-meta">
          <span class="stat-pill-label">Revenue Stream</span>
          <span class="stat-pill-value" id="stats-revenue">₱0.00 Active</span>
        </div>
      </div>
      ` : ''}
      <div class="stat-pill">
        <div class="stat-pill-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/></svg>
        </div>
        <div class="stat-pill-meta">
          <span class="stat-pill-label">Washers Idle</span>
          <span class="stat-pill-value" id="stats-washers-idle">0 Nodes</span>
        </div>
      </div>
      <div class="stat-pill">
        <div class="stat-pill-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
        </div>
        <div class="stat-pill-meta">
          <span class="stat-pill-label">Dryers Idle</span>
          <span class="stat-pill-value" id="stats-dryers-idle">0 Nodes</span>
        </div>
      </div>
      <div class="stat-pill">
        <div class="stat-pill-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4L12 14.01l-3-3"/></svg>
        </div>
        <div class="stat-pill-meta">
          <span class="stat-pill-label">Active Cycles</span>
          <span class="stat-pill-value" id="stats-active-cycles">0 Running</span>
        </div>
      </div>
    </div>

    <!-- Filters & Bulk Controls Bar -->
    <div class="machines-control-bar">
      <div class="filter-pills">
        <button class="filter-pill ${currentFilter === 'all' ? 'active' : ''}" onclick="setMachineFilter('all')">All Nodes</button>
        <button class="filter-pill ${currentFilter === 'washers' ? 'active' : ''}" onclick="setMachineFilter('washers')">Washers</button>
        <button class="filter-pill ${currentFilter === 'dryers' ? 'active' : ''}" onclick="setMachineFilter('dryers')">Dryers</button>
        <button class="filter-pill ${currentFilter === 'active' ? 'active' : ''}" onclick="setMachineFilter('active')">Active</button>
        <button class="filter-pill ${currentFilter === 'idle' ? 'active' : ''}" onclick="setMachineFilter('idle')">Idle</button>
      </div>
      <div class="filter-buttons">
        <button class="btn btn-primary" onclick="loadMachinesGrid(true)">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.72 2.78L21 8"></path><path d="M21 3v5h-5"></path></svg>
          Refresh Grid
        </button>
      </div>
    </div>

    <!-- Machine Grids Container -->
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

function setMachineFilter(filterValue) {
  currentFilter = filterValue;
  document.querySelectorAll('.filter-pill').forEach(btn => {
    btn.classList.remove('active');
    if (btn.getAttribute('onclick').includes(filterValue)) {
      btn.classList.add('active');
    }
  });
  renderGrids();
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
        <div class="machine-card-shell" style="width: 100%;">
          <div class="machine-card-inner" style="text-align: center; padding: 2.5rem; min-height: auto;">
            <svg width="48" height="48" fill="none" stroke="oklch(0.60 0.15 20)" stroke-width="2" viewBox="0 0 24 24" style="margin: 0 auto 1rem;"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
            <h3 class="machine-name" style="font-size: var(--text-lg); margin-bottom: 0.5rem;">Failed to load machines</h3>
            <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Could not establish connection to local API server.</p>
            <button class="btn btn-primary" onclick="loadMachinesGrid(true)">Retry Connection</button>
          </div>
        </div>
      `;
    }
  }
}

function renderGrids() {
  const container = document.getElementById("machine-grids-container");
  if (!container) return;

  // Calculate dynamic stats
  const totalCount = machinesList.length;
  const activeCount = machinesList.filter(m => m.status === 'BUSY').length;
  const idleWashers = machinesList.filter(m => m.type === 'washer' && m.status === 'IDLE').length;
  const idleDryers = machinesList.filter(m => m.type === 'dryer' && m.status === 'IDLE').length;

  // Render stats summary text
  const revElement = document.getElementById("stats-revenue");
  if (revElement) {
    const runningRevenue = machinesList.filter(m => m.status === 'BUSY').reduce((acc, curr) => acc + (curr.vend_price || 0), 0);
    revElement.textContent = `₱${runningRevenue}.00 Active`;
  }
  const washersIdleEl = document.getElementById("stats-washers-idle");
  if (washersIdleEl) washersIdleEl.textContent = `${idleWashers} Idle`;
  const dryersIdleEl = document.getElementById("stats-dryers-idle");
  if (dryersIdleEl) dryersIdleEl.textContent = `${idleDryers} Idle`;
  const activeCyclesEl = document.getElementById("stats-active-cycles");
  if (activeCyclesEl) activeCyclesEl.textContent = `${activeCount} Running`;

  if (totalCount === 0) {
    container.innerHTML = `
      <div class="machine-card-shell" style="width: 100%;">
        <div class="machine-card-inner" style="text-align: center; padding: 3rem;">
          <p style="color: var(--text-secondary);">No machines registered in the local network.</p>
        </div>
      </div>
    `;
    return;
  }

  // Filter based on selected filter pill
  let filteredList = [...machinesList];
  if (currentFilter === 'washers') {
    filteredList = filteredList.filter(m => m.type === 'washer');
  } else if (currentFilter === 'dryers') {
    filteredList = filteredList.filter(m => m.type === 'dryer');
  } else if (currentFilter === 'active') {
    filteredList = filteredList.filter(m => m.status === 'BUSY');
  } else if (currentFilter === 'idle') {
    filteredList = filteredList.filter(m => m.status === 'IDLE');
  }

  // Filter into washers and dryers for visual categorization
  const washers = filteredList.filter(m => m.type === 'washer');
  const dryers = filteredList.filter(m => m.type === 'dryer');

  let htmlContent = '';

  if (washers.length > 0) {
    htmlContent += `
      <div class="card" style="border: none; background: transparent; padding: 0; box-shadow: none; margin-bottom: var(--space-xl);">
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
      <div class="card" style="border: none; background: transparent; padding: 0; box-shadow: none; margin-bottom: var(--space-xl);">
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

  if (filteredList.length === 0) {
    htmlContent = `
      <div class="machine-card-shell" style="width: 100%;">
        <div class="machine-card-inner" style="text-align: center; padding: 3rem;">
          <p style="color: var(--text-secondary);">No machines match the selected filter.</p>
        </div>
      </div>
    `;
  }

  container.innerHTML = htmlContent;
  
  // Initialize dynamic active countdowns
  initCountdowns();
}

function getMachineCardHtml(m) {
  const isAdmin = !!sessionStorage.getItem("adm_pin");
  const isBusy = m.status === 'BUSY';
  const isOffline = m.status === 'OFFLINE';
  
  const statusBadge = isBusy 
    ? '<span class="badge badge-busy">RUNNING</span>' 
    : isOffline 
      ? '<span class="badge badge-offline">OFFLINE</span>' 
      : '<span class="badge badge-idle">IDLE</span>';

  const iconClass = m.type === 'washer' ? 'washer' : 'dryer';
  const isSelected = selectedMachines.has(m.id) ? 'selected' : '';
  const adminGear = isAdmin ? `<button onclick="openEditMachineModal('${m.id}')" style="background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 4px;"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg></button>` : '';

  // Icon SVG
  const machineIcon = m.type === 'washer' 
    ? `<svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle><rect x="3" y="3" width="18" height="18" rx="3" ry="3"></rect></svg>`
    : `<svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3" ry="3"></rect><circle cx="12" cy="13" r="5"></circle><line x1="6" y1="7" x2="10" y2="7" stroke-linecap="round"></line><circle cx="16" cy="7" r="1" fill="currentColor"></circle></svg>`;
  let actionsHtml = '';
  if (isOffline) {
    if (isAdmin) {
      actionsHtml = `
        <button class="btn btn-secondary" onclick="lifeCheckSingle('${m.id}', this)">
          <span>Reconnect</span>
          <span class="btn-icon-circle">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l.73-.72"/></svg>
          </span>
        </button>`;
    } else {
      actionsHtml = '';
    }
  } else if (isBusy) {
    actionsHtml = `
      <button class="btn btn-danger" onclick="stopMachineCycle('${m.id}', this)">
        <span>STOP CYCLE</span>
        <span class="btn-icon-circle">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16"/></svg>
        </span>
      </button>`;
  } else {
    const stdLabel = m.type === 'washer' ? 'STD Wash (₱60)' : 'STD Dry (₱70)';
    const qkLabel = m.type === 'washer' ? 'Quick (₱50)' : 'Add Time (₱15)';
    
    actionsHtml = `
      <button class="btn btn-primary" onclick="startMachineDirect('${m.id}', 'standard', this)">
        <span>${stdLabel}</span>
        <span class="btn-icon-circle">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </span>
      </button>
      <button class="btn btn-secondary" onclick="startMachineDirect('${m.id}', 'quick', this)">
        <span>${qkLabel}</span>
        <span class="btn-icon-circle">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M12 5v14M5 12h14"/></svg>
        </span>
      </button>
    `;
  }

  // Calculate remaining seconds & progress percentage if busy
  let remainingTimeStr = '';
  let progressPct = 0;
  if (isBusy && m.run_ends_at) {
    const ends = new Date(m.run_ends_at.replace(' ', 'T')).getTime();
    const starts = m.run_started_at ? new Date(m.run_started_at.replace(' ', 'T')).getTime() : ends - (35 * 60 * 1000); // fallback 35 min
    const now = new Date().getTime();
    const diff = Math.max(0, Math.floor((ends - now) / 1000));
    
    if (diff > 0) {
      const mins = Math.floor(diff / 60).toString().padStart(2, '0');
      const secs = (diff % 60).toString().padStart(2, '0');
      remainingTimeStr = `${mins}:${secs}`;
      
      const total = ends - starts;
      const elapsed = now - starts;
      if (total > 0) {
        progressPct = Math.min(100, Math.max(0, Math.floor((elapsed / total) * 100)));
      }
    }
  }

  const progressHtml = `
    <div class="progress-bar-container" id="progress-container-${m.id}" style="${isBusy ? 'display: block;' : 'display: none;'}">
      <div class="progress-bar-fill" id="progress-fill-${m.id}" style="width: ${progressPct}%;"></div>
    </div>
  `;

  return `
    <div class="machine-card-shell ${isBusy ? 'running' : ''} ${isOffline ? 'offline' : ''} ${isSelected}" id="machine-card-${m.id}" data-id="${m.id}">
      <div class="machine-card-inner">
        <div class="machine-card-header">
          <div class="machine-name-block">
            <span class="machine-name">
              ${m.name}
              ${adminGear}
            </span>
          </div>
          <div class="machine-icon-wrapper ${iconClass}">
            ${machineIcon}
          </div>
        </div>
        
        <div class="machine-card-status-row">
          ${isAdmin ? `
          <button class="btn-link" onclick="toggleTechInfo('${m.id}', event)" style="margin-left: auto; display: flex; align-items: center; color: var(--text-muted); cursor: pointer; min-height: auto; padding: 4px;" title="Technician Details">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          </button>
          ` : ''}
        </div>

        ${isAdmin ? `
        <div class="machine-details" id="tech-details-${m.id}" style="display: none; border-top: 1px dashed var(--border-light); margin-top: 8px; padding-top: 8px;">
          <div class="detail-row">
            <span class="detail-label">Network IP</span>
            <span class="detail-value" style="font-family: monospace; font-size: 11px;">${m.esp32_ip || 'Unassigned'}</span>
          </div>
          <div class="detail-row" style="margin-top: 4px;">
            <span class="detail-label">Pulse Parameters</span>
            <span class="detail-value" style="font-size: 11px;">${m.pulse_count || 0}x @ ${m.pulse_on || 0}ms</span>
          </div>
        </div>
        ` : ''}

        ${progressHtml}

        <div class="machine-countdown" id="countdown-${m.id}" data-ends="${m.run_ends_at || ''}" data-starts="${m.run_started_at || ''}">
          ${remainingTimeStr}
        </div>

        <div class="machine-card-actions">
          ${actionsHtml}
        </div>
      </div>
    </div>
  `;
}

function toggleTechInfo(machineId, event) {
  event.stopPropagation();
  const detailsEl = document.getElementById(`tech-details-${machineId}`);
  if (detailsEl) {
    if (detailsEl.style.display === "none") {
      detailsEl.style.display = "block";
    } else {
      detailsEl.style.display = "none";
    }
  }
}

function initCountdowns() {
  clearInterval(countdownInterval);
  countdownInterval = setInterval(() => {
    document.querySelectorAll(".machine-countdown").forEach(el => {
      const endsStr = el.getAttribute("data-ends");
      const startsStr = el.getAttribute("data-starts");
      if (!endsStr) return;

      const ends = new Date(endsStr.replace(' ', 'T')).getTime();
      const starts = startsStr ? new Date(startsStr.replace(' ', 'T')).getTime() : ends - (35 * 60 * 1000);
      const now = new Date().getTime();
      const diff = Math.max(0, Math.floor((ends - now) / 1000));

      const machineId = el.id.replace("countdown-", "");
      const progressFill = document.getElementById(`progress-fill-${machineId}`);

      if (diff > 0) {
        const mins = Math.floor(diff / 60).toString().padStart(2, '0');
        const secs = (diff % 60).toString().padStart(2, '0');
        el.textContent = `${mins}:${secs}`;
        
        if (progressFill) {
          const total = ends - starts;
          const elapsed = now - starts;
          if (total > 0) {
            const pct = Math.min(100, Math.max(0, Math.floor((elapsed / total) * 100)));
            progressFill.style.width = `${pct}%`;
          }
        }
      } else {
        el.textContent = "";
        if (progressFill) progressFill.style.width = "100%";
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

// ----------------------------------------------------
// Admin Node Management Modal
// ----------------------------------------------------
function openRegisterMachineModal() {
  const container = document.getElementById("notification-container");
  const modal = document.createElement("div");
  modal.style.position = "fixed";
  modal.style.top = "0"; modal.style.left = "0"; modal.style.width = "100%"; modal.style.height = "100%";
  modal.style.backgroundColor = "rgba(0,0,0,0.5)"; modal.style.zIndex = "9999";
  modal.style.display = "flex"; modal.style.alignItems = "center"; modal.style.justifyContent = "center";
  modal.id = "machine-modal-overlay";
  
  modal.innerHTML = `
    <div style="background: var(--bg); padding: 24px; border-radius: var(--radius-md); width: 400px; max-width: 90%; max-height: 90vh; overflow-y: auto;">
      <h3 style="margin-bottom: 16px;">Register New Hardware Node</h3>
      <form onsubmit="submitRegisterMachine(event)">
        <div class="form-group">
          <label class="form-label">Hardware ID (e.g. Washer-01)</label>
          <input type="text" id="reg-mac-id" required>
        </div>
        <div class="form-group">
          <label class="form-label">IP Address</label>
          <input type="text" id="reg-mac-ip" placeholder="192.168.x.x" required>
        </div>
        <div class="grid-cols-2" style="gap: 12px; margin-bottom: 0;">
          <div class="form-group">
            <label class="form-label">Type</label>
            <select id="reg-mac-type" required>
              <option value="washer">Washer</option>
              <option value="dryer">Dryer</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Vend Price (₱)</label>
            <input type="number" id="reg-mac-price" value="60" required>
          </div>
        </div>
        <div class="grid-cols-2" style="gap: 12px;">
          <button class="btn btn-primary" type="submit">Register</button>
          <button class="btn btn-secondary" type="button" onclick="document.getElementById('machine-modal-overlay').remove()">Cancel</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(modal);
}

async function submitRegisterMachine(e) {
  e.preventDefault();
  const pin = sessionStorage.getItem("adm_pin") || "";
  const id = document.getElementById("reg-mac-id").value;
  const ip = document.getElementById("reg-mac-ip").value;
  const type = document.getElementById("reg-mac-type").value;
  const price = document.getElementById("reg-mac-price").value;

  try {
    const res = await apiFetch("/machines", {
      method: "POST",
      headers: { "X-Admin-Pin": pin },
      body: JSON.stringify({
        id: id, ip_address: ip, type: type, vend_price: price, alias: id, location_id: CONFIG.LOCATION_ID
      })
    });
    if (res.status === "ok") {
      document.getElementById("machine-modal-overlay").remove();
      showNotification("Success", "Machine registered.", "success");
      loadMachinesGrid(true);
    }
  } catch(err) {}
}

async function openEditMachineModal(machineId) {
  const m = machinesList.find(x => x.id === machineId);
  if (!m) return;
  
  const modal = document.createElement("div");
  modal.style.position = "fixed";
  modal.style.top = "0"; modal.style.left = "0"; modal.style.width = "100%"; modal.style.height = "100%";
  modal.style.backgroundColor = "rgba(0,0,0,0.5)"; modal.style.zIndex = "9999";
  modal.style.display = "flex"; modal.style.alignItems = "center"; modal.style.justifyContent = "center";
  modal.id = "edit-machine-modal-overlay";
  
  modal.innerHTML = `
    <div style="background: var(--bg); padding: 24px; border-radius: var(--radius-md); width: 400px; max-width: 90%; max-height: 90vh; overflow-y: auto;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <h3 style="margin:0;">Edit Node ${m.id}</h3>
        <button class="btn btn-danger" type="button" onclick="deleteMachine('${m.id}')" style="min-height: 30px; padding: 4px 8px; font-size: 11px;">DELETE</button>
      </div>
      <form onsubmit="submitEditMachine(event, '${m.id}')">
        <div class="form-group">
          <label class="form-label">Alias / Display Name</label>
          <input type="text" id="edit-mac-alias" value="${m.alias || m.id}" required>
        </div>
        <div class="form-group">
          <label class="form-label">IP Address</label>
          <input type="text" id="edit-mac-ip" value="${m.ip_address || m.esp32_ip || ''}" required>
        </div>
        <div class="grid-cols-2" style="gap: 12px; margin-bottom: 0;">
          <div class="form-group">
            <label class="form-label">Type</label>
            <select id="edit-mac-type" required>
              <option value="washer" ${m.type === 'washer' ? 'selected' : ''}>Washer</option>
              <option value="dryer" ${m.type === 'dryer' ? 'selected' : ''}>Dryer</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Vend Price (₱)</label>
            <input type="number" id="edit-mac-price" value="${m.vend_price || 60}" required>
          </div>
        </div>
        <div class="grid-cols-2" style="gap: 12px;">
          <button class="btn btn-primary" type="submit">Save</button>
          <button class="btn btn-secondary" type="button" onclick="document.getElementById('edit-machine-modal-overlay').remove()">Cancel</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(modal);
}

async function submitEditMachine(e, id) {
  e.preventDefault();
  const pin = sessionStorage.getItem("adm_pin") || "";
  const alias = document.getElementById("edit-mac-alias").value;
  const ip = document.getElementById("edit-mac-ip").value;
  const type = document.getElementById("edit-mac-type").value;
  const price = document.getElementById("edit-mac-price").value;

  try {
    const res = await apiFetch("/machines/" + id, {
      method: "PUT",
      headers: { "X-Admin-Pin": pin },
      body: JSON.stringify({
        alias: alias, ip_address: ip, type: type, vend_price: price
      })
    });
    if (res.status === "ok") {
      document.getElementById("edit-machine-modal-overlay").remove();
      showNotification("Success", "Machine updated.", "success");
      loadMachinesGrid(true);
    }
  } catch(err) {}
}

async function deleteMachine(id) {
  if (!confirm("Are you sure you want to delete node " + id + "?")) return;
  const pin = sessionStorage.getItem("adm_pin") || "";
  try {
    const res = await apiFetch("/machines/" + id, {
      method: "DELETE",
      headers: { "X-Admin-Pin": pin }
    });
    if (res.status === "ok") {
      document.getElementById("edit-machine-modal-overlay").remove();
      showNotification("Deleted", "Machine removed from registry.", "success");
      loadMachinesGrid(true);
    }
  } catch(err) {}
}
