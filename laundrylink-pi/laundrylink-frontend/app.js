// app.js
// LaundryLink — Standalone Core App Controller

const TABS = {
  machines: () => typeof renderMachinesPage === 'function' && renderMachinesPage(),
  orders: () => typeof renderOrdersPage === 'function' && renderOrdersPage(),
  reports: () => typeof renderReportsPage === 'function' && renderReportsPage(),
  more: () => typeof renderMorePage === 'function' && renderMorePage(),
};

let currentTab = "machines";
let globalShiftState = null;

// Clock tick
function initClock() {
  const timeEl = document.getElementById("top-bar-time");
  if (!timeEl) return;
  function tick() {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true
    });
  }
  tick();
  setInterval(tick, 1000);
}

// Shift Indicator updater
async function loadShiftIndicator() {
  const el = document.getElementById("shift-indicator");
  const textEl = el.querySelector(".indicator-text");
  
  try {
    const res = await fetch(`${CONFIG.PI_BASE_URL}/shifts/active`);
    const data = await res.json();
    
    if (data.active_shift) {
      globalShiftState = data.active_shift;
      el.className = "shift-indicator active";
      textEl.textContent = `● Active: ${data.active_shift.display_name}`;
    } else {
      globalShiftState = null;
      el.className = "shift-indicator inactive";
      textEl.textContent = "○ No Active Shift";
    }
  } catch (err) {
    globalShiftState = null;
    el.className = "shift-indicator inactive";
    textEl.textContent = "○ Connection Offline";
  }
}

// Custom Notification Toast System
function showNotification(title, message, type = "success") {
  const container = document.getElementById("notification-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `notification ${type}`;
  
  // Icon selection
  let iconSvg = '';
  if (type === 'success') {
    iconSvg = `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
  } else if (type === 'error') {
    iconSvg = `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
  } else {
    iconSvg = `<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
  }

  toast.innerHTML = `
    <div class="notification-icon">${iconSvg}</div>
    <div class="notification-content">
      <div class="notification-title">${title}</div>
      <div class="notification-desc">${message}</div>
    </div>
    <button class="notification-close">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"></path></svg>
    </button>
  `;

  // Dismiss button action
  toast.querySelector(".notification-close").addEventListener("click", () => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-10px)";
    setTimeout(() => toast.remove(), 200);
  });

  container.appendChild(toast);

  // Auto-dismiss after 4 seconds
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-10px)";
      setTimeout(() => toast.remove(), 200);
    }
  }, 4000);
}

// Global API Fetch helper
async function apiFetch(path, options = {}) {
  const url = `${CONFIG.PI_BASE_URL}${path}`;
  const defaultHeaders = {
    "Content-Type": "application/json",
  };
  
  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    }
  };

  try {
    const res = await fetch(url, config);
    if (!res.ok) {
      let errData = {};
      try { errData = await res.json(); } catch(e) {}
      throw new Error(errData.error || `HTTP request failed: ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    console.error("API Fetch Error:", err);
    showNotification("API Connection Error", err.message || "Failed to reach backend server.", "error");
    throw err;
  }
}

// Tab routing logic
function showTab(tab) {
  // Update nav highlight
  document.querySelectorAll(".bottom-nav .tab-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`tab-${tab}`);
  if (activeBtn) activeBtn.classList.add("active");

  // Clean intervals from active pages
  if (typeof clearMachinesIntervals === 'function') {
    clearMachinesIntervals();
  }

  currentTab = tab;
  
  // Render views
  if (TABS[tab]) {
    TABS[tab]();
  }
}

// App Initialization
document.addEventListener("DOMContentLoaded", () => {
  // Set store name
  const nameEl = document.getElementById("shop-name");
  if (nameEl) nameEl.textContent = CONFIG.SHOP_NAME;

  initClock();
  loadShiftIndicator();
  
  // Start auto shift polling
  setInterval(loadShiftIndicator, 15000);

  // Load standard machines view
  showTab("machines");
});
