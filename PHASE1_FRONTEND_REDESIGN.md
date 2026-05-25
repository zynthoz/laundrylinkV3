# LaundryLink — Phase 1: Frontend Separation + Full Redesign
## Combined Implementation Plan

---

## What This Phase Accomplishes

Two things happening at once because it's more efficient:

1. **Separation** — Pull the dashboard out of the Pi's Flask app into a standalone deployable frontend
2. **Redesign** — Rebuild the UI from scratch optimized for the actual use case: counter staff on a tablet, mid-transaction, needing fast interactions

Doing both together means you only touch the HTML/CSS/JS once instead of twice.

---

## Understanding the Current UI Problems

Before redesigning, here's what's wrong with the current dashboard for this use case:

| Problem | Why It Matters |
|---|---|
| Machine cards are small, equally weighted with other content | Operators need to see and tap machines instantly — they're the #1 action |
| Sidebar navigation is desktop-first | Counter staff on a tablet can't easily use a collapsible sidebar |
| Dashboard page has 4 major cards before you even see machines | Low stock warnings, quick print, post-cycle payment — all competing for attention |
| Stats and analytics mixed with operational controls | Operators don't need revenue stats mid-shift — that's a manager view |
| All pages have equal visual weight | Job orders, settings, inventory all feel the same as the machine panel |
| No clear operator vs manager separation | Both roles see everything, which creates clutter for each |

---

## Design Direction

### Core Principle: Operator First
The person using this most is a **counter attendant** who needs to:
1. See which machines are free/busy at a glance
2. Start a machine in 1-2 taps
3. Log a payment or job order quickly
4. Everything else is secondary

### Layout: Bottom Tab Bar (Mobile/Tablet First)
Replace the sidebar with a **bottom navigation bar** — the standard for tablet/mobile apps used at a counter.

```
┌─────────────────────────────────┐
│         LaundryLink             │  ← top bar (shop name, shift status, time)
├─────────────────────────────────┤
│                                 │
│         MAIN CONTENT            │
│         (active page)           │
│                                 │
│                                 │
├─────────────────────────────────┤
│  🖥 Machines │ 📋 Orders │ 📊 Reports │ ⚙ More  │  ← bottom tabs
└─────────────────────────────────┘
```

### Visual Hierarchy
- **Machines page** = the home screen, full width, big cards
- **Machine cards** = large, tappable, status-first design
- **Action buttons** = full-width, high contrast, finger-friendly (min 48px touch targets)
- **Everything else** = accessible but not in the way

### Color System (keep the existing palette, refine usage)
The current design tokens are good. The issue is how they're applied, not the colors themselves.

```css
/* Keep these from the current design */
--accent: #2563EB;        /* primary action */
--status-running: #1E40AF on #DBEAFE;   /* busy machine */
--status-idle: #5A5F72 on #F0F2F7;      /* idle machine */
--status-offline: #991B1B on #FEE2E2;   /* offline machine */
```

---

## New Page Structure

Replace the current 10+ pages with 4 focused tabs:

### Tab 1 — Machines (Home)
The most important screen. Full focus on machine status and control.

```
┌─────────────────────────────────────────┐
│ ● Shift Active    LaundryLink    10:42  │
├─────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│ │ WASHER 1 │ │ WASHER 2 │ │ DRYER 1  │ │
│ │          │ │          │ │          │ │
│ │  [icon]  │ │  [icon]  │ │  [icon]  │ │
│ │          │ │          │ │          │ │
│ │  IDLE    │ │ RUNNING  │ │  IDLE    │ │
│ │          │ │  04:23   │ │          │ │
│ │ [START]  │ │ [STOP]   │ │ [START]  │ │
│ │ [QUICK]  │ │          │ │ [QUICK]  │ │
│ └──────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────┤
│  🖥 Machines  │ 📋 Orders │ 📊 Reports │ ⚙ More  │
└─────────────────────────────────────────┘
```

### Tab 2 — Orders
Job orders + post-cycle payment logging. Clean form-focused layout.

### Tab 3 — Reports
Shift summary, daily summary, analytics, print actions. Manager-oriented.

### Tab 4 — More
Inventory, services, settings, shifts, admin — everything else in a list menu.

---

## File Structure for the New Frontend

```
laundrylink-frontend/
├── index.html          ← main app shell (tabs, routing, shared layout)
├── config.js           ← PI_BASE_URL and LOCATION_ID per shop
├── style.css           ← all styles (extracted from current dashboard.html)
├── app.js              ← all JavaScript (extracted + rewritten)
├── pages/
│   ├── machines.js     ← machines tab logic
│   ├── orders.js       ← job orders + post-cycle payment logic
│   ├── reports.js      ← reports + print logic
│   └── more.js         ← settings, inventory, services, shifts, admin logic
└── receipt.html        ← standalone receipt print page
```

This is still **plain HTML/CSS/JS** — no build tools, no npm, no React. Keeps it simple and deployable anywhere.

---

## Step-by-Step Build Instructions

---

### Step 1 — Set Up the New Repo

Create a new GitHub repo called `laundrylink-frontend`. Do not copy `dashboard.html` into it — start fresh. You will reference the old file for logic, not copy it wholesale.

```
mkdir laundrylink-frontend
cd laundrylink-frontend
git init
touch index.html config.js style.css app.js
mkdir pages
touch pages/machines.js pages/orders.js pages/reports.js pages/more.js
```

---

### Step 2 — Create `config.js`

This file is the only thing that changes between shop deployments.

```javascript
// config.js
// Edit this file for each shop deployment
const CONFIG = {
  PI_BASE_URL: "https://shop-a.yourdomain.com",  // Cloudflare Tunnel URL
  LOCATION_ID: "shop_a",
  SHOP_NAME: "LaundryLink — Shop A",
};
```

---

### Step 3 — Build `index.html` (App Shell)

The shell contains the top bar, the content area, and the bottom tab bar. Pages are injected into the content area by JavaScript.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>LaundryLink</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
  <script src="config.js"></script>
</head>
<body>

  <!-- TOP BAR -->
  <header class="top-bar">
    <div class="shift-indicator" id="shift-indicator">Loading...</div>
    <div class="shop-name" id="shop-name"></div>
    <div class="top-bar-time" id="top-bar-time"></div>
  </header>

  <!-- PAGE CONTENT -->
  <main class="content" id="content">
    <!-- Injected by pages/*.js -->
  </main>

  <!-- BOTTOM TABS -->
  <nav class="bottom-nav">
    <button class="tab-btn active" id="tab-machines" onclick="showTab('machines')">
      <svg><!-- washer icon --></svg>
      <span>Machines</span>
    </button>
    <button class="tab-btn" id="tab-orders" onclick="showTab('orders')">
      <svg><!-- clipboard icon --></svg>
      <span>Orders</span>
    </button>
    <button class="tab-btn" id="tab-reports" onclick="showTab('reports')">
      <svg><!-- chart icon --></svg>
      <span>Reports</span>
    </button>
    <button class="tab-btn" id="tab-more" onclick="showTab('more')">
      <svg><!-- menu icon --></svg>
      <span>More</span>
    </button>
  </nav>

  <script src="app.js"></script>
  <script src="pages/machines.js"></script>
  <script src="pages/orders.js"></script>
  <script src="pages/reports.js"></script>
  <script src="pages/more.js"></script>

</body>
</html>
```

---

### Step 4 — Build `style.css`

Copy the CSS custom properties (design tokens) from the current `dashboard.html` — they're good. Then write new layout CSS from scratch.

**Key new CSS to write:**

```css
/* === LAYOUT === */
body {
  display: flex;
  flex-direction: column;
  height: 100dvh;         /* dynamic viewport height — important for mobile */
  overflow: hidden;
}

.top-bar {
  height: 56px;
  background: var(--sidebar-bg);
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  flex-shrink: 0;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  padding-bottom: 80px;   /* space for bottom nav */
}

.bottom-nav {
  height: 64px;
  background: var(--card);
  border-top: 1px solid var(--border);
  display: flex;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
}

.tab-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  border: none;
  background: none;
  cursor: pointer;
}

.tab-btn.active {
  color: var(--accent);
}

/* === MACHINE CARDS === */
.machine-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.machine-card {
  background: var(--card);
  border: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 220px;    /* large enough to tap comfortably */
  transition: border-color 0.2s;
}

.machine-card.running {
  border-color: var(--accent);
  background: #EEF2FF;
}

.machine-card.offline {
  border-color: var(--status-offline-text);
  opacity: 0.6;
}

/* === BUTTONS === */
.btn-start {
  width: 100%;
  padding: 14px;        /* large touch target */
  font-size: 14px;
  font-weight: 600;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.btn-stop {
  width: 100%;
  padding: 14px;
  font-size: 14px;
  font-weight: 600;
  background: #DC2626;
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

/* Minimum touch target size — accessibility requirement */
button { min-height: 44px; }
```

---

### Step 5 — Build `pages/machines.js`

This replaces the Jinja2 machine loop and all machine-related JS from `dashboard.html`.

```javascript
// pages/machines.js

function renderMachinesPage() {
  document.getElementById("content").innerHTML = `
    <div class="machine-grid" id="machine-grid">
      <div class="loading-state">Loading machines...</div>
    </div>
  `;
  loadMachines();
}

async function loadMachines() {
  try {
    const res = await fetch(`${CONFIG.PI_BASE_URL}/dashboard/summary/shift`);
    const data = await res.json();
    renderMachineCards(data.machines || []);
  } catch (err) {
    document.getElementById("machine-grid").innerHTML = `
      <div class="error-state">Could not reach the Pi. Check connection.</div>
    `;
  }
}

function renderMachineCards(machines) {
  if (!machines.length) {
    document.getElementById("machine-grid").innerHTML = `
      <div class="empty-state">No machines registered yet.</div>
    `;
    return;
  }

  document.getElementById("machine-grid").innerHTML = machines.map(m => `
    <div class="machine-card ${m.status === 'BUSY' ? 'running' : ''} ${m.status === 'OFFLINE' ? 'offline' : ''}"
         id="machine-card-${m.id}">

      <div class="machine-card-header">
        <div>
          <div class="machine-name">${m.name}</div>
          <div class="machine-type">${m.type}</div>
        </div>
        ${getMachineIcon(m.type, m.status)}
      </div>

      <div class="machine-status-badge status-${m.status.toLowerCase()}">
        ${m.status}
      </div>

      <div class="machine-countdown" id="countdown-${m.id}">
        ${m.status === 'BUSY' ? '--:--' : ''}
      </div>

      <div class="machine-actions">
        ${getMachineButtons(m)}
      </div>
    </div>
  `).join("");
}

function getMachineButtons(m) {
  if (m.status === 'OFFLINE') {
    return `<button class="btn-start" disabled>Offline</button>`;
  }
  if (m.status === 'BUSY') {
    return `<button class="btn-stop" onclick="stopMachine('${m.id}', '${m.location_id}', this)">STOP</button>`;
  }
  const startLabel = m.type === 'washer' ? 'STANDARD WASH' : 'STANDARD DRY';
  const quickLabel = m.type === 'washer' ? 'QUICK WASH' : 'ADDITIONAL DRY';
  return `
    <button class="btn-start" onclick="startMachine('${m.id}', '${m.location_id}', this, 'standard')">${startLabel}</button>
    <button class="btn-quick" onclick="startMachine('${m.id}', '${m.location_id}', this, 'quick')">${quickLabel}</button>
  `;
}

// Port startMachine, stopMachine, lifeCheckMachine logic from dashboard.html
// Replace all relative fetch() paths with CONFIG.PI_BASE_URL + path
async function startMachine(machineId, locationId, btn, mode) {
  btn.disabled = true;
  btn.textContent = "Starting...";
  try {
    const res = await fetch(`${CONFIG.PI_BASE_URL}/dashboard/machine/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ machine_id: machineId, location_id: locationId, mode }),
    });
    const data = await res.json();
    if (data.ok) loadMachines();   // refresh cards
    else alert(data.error || "Failed to start machine");
  } catch {
    alert("Could not reach the Pi");
  } finally {
    btn.disabled = false;
  }
}

async function stopMachine(machineId, locationId, btn) {
  btn.disabled = true;
  btn.textContent = "Stopping...";
  try {
    const res = await fetch(`${CONFIG.PI_BASE_URL}/dashboard/machine/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ machine_id: machineId, location_id: locationId }),
    });
    const data = await res.json();
    if (data.ok) loadMachines();
    else alert(data.error || "Failed to stop machine");
  } catch {
    alert("Could not reach the Pi");
  }
}

// Auto-refresh machine status every 30 seconds
let machineRefreshInterval;
function startMachineAutoRefresh() {
  clearInterval(machineRefreshInterval);
  machineRefreshInterval = setInterval(loadMachines, 30000);
}
```

---

### Step 6 — Build `app.js` (Core App Logic)

```javascript
// app.js

// Tab routing
const TABS = {
  machines: renderMachinesPage,
  orders: renderOrdersPage,
  reports: renderReportsPage,
  more: renderMorePage,
};

let currentTab = "machines";

function showTab(tab) {
  // Update active tab button
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.getElementById(`tab-${tab}`).classList.add("active");

  // Stop any running intervals from previous tab
  clearInterval(machineRefreshInterval);

  // Render the page
  currentTab = tab;
  TABS[tab]();

  // Start auto-refresh if on machines tab
  if (tab === "machines") startMachineAutoRefresh();
}

// Top bar clock
function startClock() {
  function tick() {
    const now = new Date();
    document.getElementById("top-bar-time").textContent =
      now.toLocaleTimeString("en-PH", { hour: "2-digit", minute: "2-digit" });
  }
  tick();
  setInterval(tick, 1000);
}

// Shift status indicator
async function loadShiftStatus() {
  try {
    const res = await fetch(`${CONFIG.PI_BASE_URL}/shifts/active`);
    const data = await res.json();
    const el = document.getElementById("shift-indicator");
    if (data.active_shift) {
      el.textContent = "● Shift Active";
      el.style.color = "#4ADE80";
    } else {
      el.textContent = "○ No Active Shift";
      el.style.color = "#F87171";
    }
  } catch {
    document.getElementById("shift-indicator").textContent = "○ Offline";
  }
}

// Shared fetch helper — all requests go through here
async function apiFetch(path, options = {}) {
  const url = `${CONFIG.PI_BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Init
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("shop-name").textContent = CONFIG.SHOP_NAME;
  startClock();
  loadShiftStatus();
  showTab("machines");
});
```

---

### Step 7 — Port Remaining Logic from `dashboard.html`

Go through `dashboard.html` section by section and port each piece to the right `pages/*.js` file:

| Original section in `dashboard.html` | Goes into |
|---|---|
| Machine status + start/stop/life check | `pages/machines.js` ✅ (done in Step 5) |
| Job orders form + table | `pages/orders.js` |
| Post-cycle payment logging | `pages/orders.js` |
| Shift summary, day summary, print buttons | `pages/reports.js` |
| Analytics, calendar | `pages/reports.js` |
| Transactions table | `pages/reports.js` |
| Inventory | `pages/more.js` |
| Services/catalog | `pages/more.js` |
| Settings | `pages/more.js` |
| Shifts (time-in/time-out) | `pages/more.js` |
| Admin panel | `pages/more.js` |
| Locations | `pages/more.js` |

**For each section, the process is:**
1. Find the HTML structure in `dashboard.html`
2. Convert it to a JavaScript string template in the `render___Page()` function
3. Find all `fetch()` calls related to that section
4. Replace relative paths with `apiFetch()` or `CONFIG.PI_BASE_URL + path`
5. Remove all `{{ jinja }}` variables — replace with JS that populates them after fetch

---

### Step 8 — Update the Pi: Remove HTML, Add CORS

**In `routes/dashboard.py`:**

Find the `render_template` call (line ~1129) and replace with:
```python
@dashboard_bp.route("/")
def index():
    return jsonify({"service": "LaundryLink Pi", "status": "ok"})
```

Delete `templates/dashboard.html` and `templates/receipt_print.html` from the Pi repo.

**In `requirements.txt` add:**
```
flask-cors==4.0.*
```

**In `app.py`:**
```python
from flask_cors import CORS

def create_app():
    init_db()
    app = Flask(__name__)
    CORS(app, origins=["https://your-vercel-url.vercel.app"])
    # ... rest unchanged
```

---

### Step 9 — Deploy to Vercel

1. Push `laundrylink-frontend` to GitHub
2. Go to vercel.com → New Project → Import that repo
3. Framework preset: **Other** (plain HTML)
4. Deploy
5. Update `CORS(app, origins=[...])` on the Pi with the Vercel URL
6. Test: open the Vercel URL, confirm machine cards load from the Pi

---

## Definition of Done

- [ ] `laundrylink-frontend` repo exists with `index.html`, `config.js`, `style.css`, `app.js`, `pages/*.js`
- [ ] Bottom tab navigation works: Machines, Orders, Reports, More
- [ ] Machine cards load dynamically from Pi API — no Jinja2
- [ ] Start/Stop buttons work from the deployed frontend
- [ ] All `fetch()` calls use `CONFIG.PI_BASE_URL` — no hardcoded localhost or relative paths
- [ ] CORS enabled on the Pi
- [ ] Pi's `/` route returns JSON, not HTML
- [ ] `templates/` folder deleted from Pi repo
- [ ] Frontend deployed and accessible on Vercel
- [ ] Works on a tablet browser in landscape and portrait
- [ ] Machine status auto-refreshes every 30 seconds

---

## What Does NOT Change on the Pi

Everything in the Pi repo stays the same except:
- `routes/dashboard.py` — remove `render_template`, keep all JSON routes
- `app.py` — add CORS
- `requirements.txt` — add flask-cors
- `templates/` — delete the folder

---

*Next phase: Cloudflare Tunnel setup + per-shop deployment + auth layer.*
