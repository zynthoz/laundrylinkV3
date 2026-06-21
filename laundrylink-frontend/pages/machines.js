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
  document.getElementById("content").innerHTML = `
    <!-- Top Statistics Summary Ribbon -->
    <div class="stats-ribbon" id="stats-ribbon-container">
      <div class="stat-pill">
        <div class="stat-pill-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        </div>
        <div class="stat-pill-meta">
          <span class="stat-pill-label">Revenue Stream</span>
          <span class="stat-pill-value" id="stats-revenue">₱0.00 Active</span>
        </div>
      </div>
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
        <button class="btn btn-secondary" onclick="runBulkLifeCheck()">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
          Life Check
        </button>
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
  const isBusy = m.status === 'BUSY';
  const isOffline = m.status === 'OFFLINE';
  
  const statusBadge = isBusy 
    ? '<span class="badge badge-busy">RUNNING</span>' 
    : isOffline 
      ? '<span class="badge badge-offline">OFFLINE</span>' 
      : '<span class="badge badge-idle">IDLE</span>';

  const iconClass = m.type === 'washer' ? 'washer' : 'dryer';
  const isSelected = selectedMachines.has(m.id) ? 'selected' : '';

  // Icon SVG
  const machineIcon = m.type === 'washer' 
    ? `<svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle><rect x="3" y="3" width="18" height="18" rx="3" ry="3"></rect></svg>`
    : `<svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"></circle><path d="M12 9v6l4 2"></path></svg>`;

  let actionsHtml = '';
  if (isOffline) {
    actionsHtml = `
      <button class="btn btn-secondary" onclick="lifeCheckSingle('${m.id}', this)">
        <span>Reconnect</span>
        <span class="btn-icon-circle">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l.73-.72"/></svg>
        </span>
      </button>`;
  } else if (isBusy) {
    actionsHtml = `
      <button class="btn btn-danger" onclick="stopMachineCycle('${m.id}', this)">
        <span>STOP CYCLE</span>
        <span class="btn-icon-circle">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/></svg>
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

  return `
    <div class="machine-card-shell ${isBusy ? 'running' : ''} ${isOffline ? 'offline' : ''} ${isSelected}" id="machine-card-${m.id}" data-id="${m.id}">
      <div class="machine-card-inner">
        <div class="machine-card-header">
          <div class="machine-name-block">
            <span class="machine-name">${m.name}</span>
            <span class="machine-type">${m.type} — ${m.machine_function || 'standard'}</span>
          </div>
          <div class="machine-icon-wrapper ${iconClass}">
            ${machineIcon}
          </div>
        </div>
        
        <div class="machine-card-status-row">
          ${statusBadge}
          <span style="font-size: 10px; font-weight: 700; color: var(--text-muted); font-family: monospace;">${m.esp32_ip}</span>
        </div>

        <div class="progress-bar-container">
          <div class="progress-bar-fill" id="progress-fill-${m.id}" style="width: ${progressPct}%"></div>
        </div>

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
