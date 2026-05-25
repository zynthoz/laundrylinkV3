#if defined(ARDUINO_ARCH_ESP32)

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

// ─── Hardcoded Network Config ─────────────────────────────────────────────────
const char* WIFI_SSID     = "pi-test";
const char* WIFI_PASSWORD = "12345678";

// Phone hotspots usually assign a dynamic subnet, so DHCP is safer by default.
const bool USE_STATIC_IP = false;
bool useStaticIp = USE_STATIC_IP;

IPAddress local_IP(10, 57, 126, 123);
IPAddress gateway(10, 57, 126, 118);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(8, 8, 8, 8);
bool pendingNetworkApply = false;
// ─────────────────────────────────────────────────────────────────────────────

#define SW_PIN 32

// ─── # of Pulses Per Machine ─────────
// Dryer  - 4 pulses
// Washer - 2 pulses
// ─────────────────────────────────────

// ─── Pulse Config (overridden by UI) ─
int pulseOnMs  = 500;
int pulseOffMs = 500;
int numPulses  = 3;
// ─────────────────────────────────────

void activateSwitch();
WebServer server(80);
bool machineState = false;

bool parseIpArg(const String& value, IPAddress& out) {
  IPAddress parsed;
  if (!parsed.fromString(value)) {
    return false;
  }
  out = parsed;
  return true;
}

void connectWithCurrentNetworkConfig() {
  Serial.printf("[CFG] APPLY_MODE: %s\n", useStaticIp ? "STATIC" : "DHCP");
  if (useStaticIp) {
    if (!WiFi.config(local_IP, gateway, subnet, primaryDNS)) {
      Serial.println("[WARN] Runtime static IP config failed - keeping DHCP behavior");
    }
  } else {
    IPAddress zero(0, 0, 0, 0);
    WiFi.config(zero, zero, zero);
  }

  WiFi.disconnect();
  delay(200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(250);
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[NET] Connected with IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.printf("[NET] Reconnect failed. Status=%d\n", WiFi.status());
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// HTML Page
// ─────────────────────────────────────────────────────────────────────────────

const char* htmlPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <title>LaundryLink</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0d0d0f;
      --card: #141418;
      --border: #2a2a32;
      --accent: #00e5ff;
      --accent2: #7c3aed;
      --text: #e8e8f0;
      --muted: #555568;
      --on: #00c853;
      --off: #ff1744;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'DM Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background-image: radial-gradient(ellipse at 20% 50%, rgba(124,58,237,0.08) 0%, transparent 60%),
                        radial-gradient(ellipse at 80% 20%, rgba(0,229,255,0.06) 0%, transparent 50%);
    }
    .header { text-align: center; margin-bottom: 32px; }
    .header h1 {
      font-family: 'Space Mono', monospace;
      font-size: 2.2em;
      letter-spacing: -1px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .header p {
      color: var(--muted);
      font-size: 0.85em;
      margin-top: 6px;
      font-family: 'Space Mono', monospace;
      letter-spacing: 1px;
      text-transform: uppercase;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 28px;
      width: 100%;
      max-width: 380px;
      box-shadow: 0 0 40px rgba(0,0,0,0.4);
    }
    .status-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    .status-label {
      font-size: 0.78em;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      font-family: 'Space Mono', monospace;
    }
    .status-badge {
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 0.85em;
      font-weight: 700;
      font-family: 'Space Mono', monospace;
      letter-spacing: 1px;
    }
    .badge-on      { background: rgba(0,200,83,0.12);  color: var(--on);     border: 1px solid rgba(0,200,83,0.3); }
    .badge-off     { background: rgba(255,23,68,0.10); color: var(--off);    border: 1px solid rgba(255,23,68,0.25); }
    .badge-sending { background: rgba(0,229,255,0.10); color: var(--accent); border: 1px solid rgba(0,229,255,0.25); }
    .sliders { margin-bottom: 24px; }
    .slider-row { margin-bottom: 18px; }
    .slider-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .slider-name {
      font-size: 0.78em;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--muted);
      font-family: 'Space Mono', monospace;
    }
    .slider-value {
      font-size: 0.9em;
      font-family: 'Space Mono', monospace;
      color: var(--accent);
      font-weight: 700;
      min-width: 60px;
      text-align: right;
    }
    input[type=range] {
      width: 100%;
      height: 4px;
      -webkit-appearance: none;
      appearance: none;
      background: var(--border);
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      cursor: pointer;
      box-shadow: 0 0 8px rgba(0,229,255,0.4);
      transition: transform 0.15s;
    }
    input[type=range]::-webkit-slider-thumb:hover { transform: scale(1.2); }
    input[type=range]::-moz-range-thumb {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      cursor: pointer;
      border: none;
    }
    .divider { height: 1px; background: var(--border); margin: 20px 0; }
    .btn-start {
      display: block;
      width: 100%;
      padding: 18px;
      font-size: 1em;
      font-weight: 700;
      font-family: 'Space Mono', monospace;
      letter-spacing: 2px;
      text-transform: uppercase;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #0d0d0f;
      transition: opacity 0.2s, transform 0.15s;
    }
    .btn-start:hover    { opacity: 0.9; transform: translateY(-1px); }
    .btn-start:active   { transform: translateY(1px); opacity: 0.8; }
    .btn-start:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
    .config-summary {
      margin-top: 20px;
      padding: 14px;
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--border);
      border-radius: 10px;
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px;
      text-align: center;
    }
    .config-item span:first-child {
      display: block;
      font-size: 0.65em;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      font-family: 'Space Mono', monospace;
      margin-bottom: 4px;
    }
    .config-item span:last-child {
      font-size: 1em;
      font-weight: 700;
      font-family: 'Space Mono', monospace;
      color: var(--text);
    }
    .footer {
      margin-top: 24px;
      color: var(--muted);
      font-size: 0.75em;
      font-family: 'Space Mono', monospace;
      letter-spacing: 1px;
    }
    .network-box {
      margin-top: 16px;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      background: rgba(255,255,255,0.02);
    }
    .network-title {
      font-size: 0.7em;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      color: var(--muted);
      font-family: 'Space Mono', monospace;
      margin-bottom: 10px;
    }
    .network-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .network-grid input,
    .network-grid select {
      width: 100%;
      background: #0f0f13;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      padding: 8px;
      font-size: 0.75em;
      font-family: 'Space Mono', monospace;
    }
    .network-actions {
      margin-top: 10px;
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .btn-network {
      flex: 1;
      border: 1px solid rgba(0,229,255,0.3);
      background: rgba(0,229,255,0.12);
      color: var(--accent);
      border-radius: 8px;
      padding: 10px;
      font-size: 0.75em;
      font-family: 'Space Mono', monospace;
      font-weight: 700;
      cursor: pointer;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .network-hint {
      font-size: 0.68em;
      color: var(--muted);
      font-family: 'Space Mono', monospace;
      margin-top: 8px;
      line-height: 1.4;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>LaundryLink</h1>
    <p>Washing Machine Controller</p>
  </div>

  <div class="card">
    <div class="status-row">
      <span class="status-label">Status</span>
      <span class="status-badge badge-off" id="badge">IDLE</span>
    </div>

    <div class="sliders">
      <div class="slider-row">
        <div class="slider-header">
          <span class="slider-name">Pulse ON Duration</span>
          <span class="slider-value" id="onVal">500ms</span>
        </div>
        <input type="range" id="pulseOn" min="50" max="3000" step="50" value="500"
          oninput="document.getElementById('onVal').textContent = this.value + 'ms'; updateSummary()">
      </div>

      <div class="slider-row">
        <div class="slider-header">
          <span class="slider-name">Pulse OFF Duration</span>
          <span class="slider-value" id="offVal">500ms</span>
        </div>
        <input type="range" id="pulseOff" min="50" max="3000" step="50" value="500"
          oninput="document.getElementById('offVal').textContent = this.value + 'ms'; updateSummary()">
      </div>

      <div class="slider-row">
        <div class="slider-header">
          <span class="slider-name">Number of Pulses</span>
          <span class="slider-value" id="pulseCountVal">2</span>
        </div>
        <input type="range" id="pulseCount" min="1" max="20" step="1" value="2"
          oninput="document.getElementById('pulseCountVal').textContent = this.value; updateSummary()">
      </div>
    </div>

    <div class="config-summary">
      <div class="config-item"><span>ON</span><span id="sumOn">500ms</span></div>
      <div class="config-item"><span>OFF</span><span id="sumOff">500ms</span></div>
      <div class="config-item"><span>PULSES</span><span id="sumCount">2</span></div>
    </div>

    <div class="divider"></div>

    <div class="network-box">
      <div class="network-title">Network Settings</div>
      <div class="network-grid">
        <select id="ipMode" onchange="toggleIpInputs()">
          <option value="dhcp">DHCP</option>
          <option value="static">Static</option>
        </select>
        <input id="ipAddr" type="text" placeholder="IP (192.168.1.50)">
        <input id="gwAddr" type="text" placeholder="Gateway">
        <input id="subnetAddr" type="text" placeholder="Subnet (255.255.255.0)">
        <input id="dnsAddr" type="text" placeholder="DNS (8.8.8.8)">
      </div>
      <div class="network-actions">
        <button class="btn-network" onclick="applyNetworkConfig()">Apply Network</button>
      </div>
      <div class="network-hint" id="networkCurrent">Current IP: --</div>
      <div class="network-hint">If you change to a new static IP, reopen the UI at the new address.</div>
    </div>

    <button class="btn-start" id="startBtn" onclick="startMachine()">
      ▶ START MACHINE
    </button>
  </div>

  <div class="footer">LaundryLink v1.0 — Debug Mode</div>

  <script>
    function updateSummary() {
      document.getElementById('sumOn').textContent    = document.getElementById('pulseOn').value + 'ms';
      document.getElementById('sumOff').textContent   = document.getElementById('pulseOff').value + 'ms';
      document.getElementById('sumCount').textContent = document.getElementById('pulseCount').value;
    }

    function startMachine() {
      const on    = document.getElementById('pulseOn').value;
      const off   = document.getElementById('pulseOff').value;
      const count = document.getElementById('pulseCount').value;
      const btn   = document.getElementById('startBtn');
      const badge = document.getElementById('badge');

      btn.disabled = true;
      badge.textContent = 'SENDING';
      badge.className   = 'status-badge badge-sending';

      fetch(`/control?on=${on}&off=${off}&count=${count}`)
        .then(r => r.text())
        .then(() => {
          badge.textContent = 'DONE';
          badge.className   = 'status-badge badge-on';
          btn.disabled = false;
          setTimeout(() => {
            badge.textContent = 'IDLE';
            badge.className   = 'status-badge badge-off';
          }, 3000);
        })
        .catch(() => {
          badge.textContent = 'ERROR';
          badge.className   = 'status-badge badge-off';
          btn.disabled = false;
        });
    }

    function getStatus() {
      fetch('/status')
        .then(r => r.text())
        .then(s => {
          if (s !== 'BUSY') {
            document.getElementById('badge').textContent = 'IDLE';
            document.getElementById('badge').className   = 'status-badge badge-off';
          }
        })
        .catch(() => {});
    }

    function toggleIpInputs() {
      const isStatic = document.getElementById('ipMode').value === 'static';
      ['ipAddr', 'gwAddr', 'subnetAddr', 'dnsAddr'].forEach(id => {
        document.getElementById(id).disabled = !isStatic;
      });
    }

    function loadNetworkInfo() {
      fetch('/network/info')
        .then(r => r.json())
        .then(data => {
          document.getElementById('ipMode').value = data.mode || 'dhcp';
          document.getElementById('ipAddr').value = data.local_ip || '';
          document.getElementById('gwAddr').value = data.gateway || '';
          document.getElementById('subnetAddr').value = data.subnet || '';
          document.getElementById('dnsAddr').value = data.dns || '';
          document.getElementById('networkCurrent').textContent = 'Current IP: ' + (data.current_ip || '--');
          toggleIpInputs();
        })
        .catch(() => {
          document.getElementById('networkCurrent').textContent = 'Current IP: unavailable';
        });
    }

    function applyNetworkConfig() {
      const mode = document.getElementById('ipMode').value;
      const params = new URLSearchParams({ mode });

      if (mode === 'static') {
        params.set('ip', document.getElementById('ipAddr').value.trim());
        params.set('gateway', document.getElementById('gwAddr').value.trim());
        params.set('subnet', document.getElementById('subnetAddr').value.trim());
        params.set('dns', document.getElementById('dnsAddr').value.trim());
      }

      fetch('/network/config?' + params.toString())
        .then(r => r.json())
        .then(data => {
          if (!data.ok) {
            alert(data.error || 'Failed to apply network settings');
            return;
          }
          alert('Network settings queued. If IP changed, reconnect to: ' + (data.target_ip || 'DHCP-assigned address'));
          setTimeout(loadNetworkInfo, 1200);
        })
        .catch(() => alert('Failed to apply network settings'));
    }

    setInterval(getStatus, 3000);
    updateSummary();
    loadNetworkInfo();
  </script>
</body>
</html>
)rawliteral";

// ─────────────────────────────────────────────────────────────────────────────
// Route handlers
// ─────────────────────────────────────────────────────────────────────────────

void handleRoot() {
  server.send(200, "text/html", htmlPage);
}

void handleControl() {
  if (server.hasArg("on"))    pulseOnMs  = server.arg("on").toInt();
  if (server.hasArg("off"))   pulseOffMs = server.arg("off").toInt();
  if (server.hasArg("count")) numPulses  = server.arg("count").toInt();

  Serial.printf("Config → ON:%dms  OFF:%dms  PULSES:%d\n", pulseOnMs, pulseOffMs, numPulses);

  machineState = true;
  activateSwitch();
  machineState = false;

  server.send(200, "text/plain", "DONE");
}

void handleStatus() {
  server.send(200, "text/plain", machineState ? "BUSY" : "IDLE");
}

void handleNetworkInfo() {
  String body = "{";
  body += "\"mode\":\"" + String(useStaticIp ? "static" : "dhcp") + "\",";
  body += "\"local_ip\":\"" + local_IP.toString() + "\",";
  body += "\"gateway\":\"" + gateway.toString() + "\",";
  body += "\"subnet\":\"" + subnet.toString() + "\",";
  body += "\"dns\":\"" + primaryDNS.toString() + "\",";
  body += "\"current_ip\":\"" + WiFi.localIP().toString() + "\"";
  body += "}";
  server.send(200, "application/json", body);
}

void handleNetworkConfig() {
  if (!server.hasArg("mode")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Missing mode\"}");
    return;
  }

  String mode = server.arg("mode");
  mode.toLowerCase();

  if (mode == "dhcp") {
    useStaticIp = false;
    pendingNetworkApply = true;
    server.send(200, "application/json", "{\"ok\":true,\"target_ip\":\"DHCP\"}");
    return;
  }

  if (mode != "static") {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Invalid mode\"}");
    return;
  }

  IPAddress newIp;
  IPAddress newGateway;
  IPAddress newSubnet;
  IPAddress newDns;

  if (!server.hasArg("ip") || !parseIpArg(server.arg("ip"), newIp)) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Invalid IP\"}");
    return;
  }
  if (!server.hasArg("gateway") || !parseIpArg(server.arg("gateway"), newGateway)) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Invalid gateway\"}");
    return;
  }
  if (!server.hasArg("subnet") || !parseIpArg(server.arg("subnet"), newSubnet)) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"Invalid subnet\"}");
    return;
  }
  if (server.hasArg("dns") && !server.arg("dns").isEmpty()) {
    if (!parseIpArg(server.arg("dns"), newDns)) {
      server.send(400, "application/json", "{\"ok\":false,\"error\":\"Invalid DNS\"}");
      return;
    }
  } else {
    newDns = primaryDNS;
  }

  local_IP = newIp;
  gateway = newGateway;
  subnet = newSubnet;
  primaryDNS = newDns;
  useStaticIp = true;
  pendingNetworkApply = true;

  String body = "{\"ok\":true,\"target_ip\":\"" + newIp.toString() + "\"}";
  server.send(200, "application/json", body);
}

void handleNotFound() {
  server.send(404, "text/plain", "Not found");
}

// ─────────────────────────────────────────────────────────────────────────────
// Setup
// ─────────────────────────────────────────────────────────────────────────────

void setup() {
  delay(8000);
  Serial.begin(115200);
  Serial.println("Booting...");

  pinMode(SW_PIN, OUTPUT);
  digitalWrite(SW_PIN, LOW);

  // ── Debug dump ────────────────────────────────────────────────────────────
  Serial.printf("[CFG] SSID:      %s\n", WIFI_SSID);
  Serial.printf("[CFG] PASSWORD:  %s\n", WIFI_PASSWORD);
  Serial.printf("[CFG] IP_MODE:   %s\n", useStaticIp ? "STATIC" : "DHCP");
  if (useStaticIp) {
    Serial.print("[CFG] STATIC_IP: "); Serial.println(local_IP);
    Serial.print("[CFG] GATEWAY:   "); Serial.println(gateway);
    Serial.print("[CFG] SUBNET:    "); Serial.println(subnet);
    Serial.print("[CFG] DNS:       "); Serial.println(primaryDNS);
  }

  // ── Connect ───────────────────────────────────────────────────────────────
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  Serial.print("Connecting to WiFi");
  connectWithCurrentNetworkConfig();

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (++attempts >= 40) {
      Serial.printf("\n[ERROR] WiFi timed out. Status=%d\n", WiFi.status());
      Serial.println("[HINT] Verify hotspot band is 2.4GHz and credentials are correct.");
      return;
    }
  }

  Serial.println();
  Serial.println("WiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // ── Start web server ──────────────────────────────────────────────────────
  server.on("/",        handleRoot);
  server.on("/control", handleControl);
  server.on("/status",  handleStatus);
  server.on("/network/info", handleNetworkInfo);
  server.on("/network/config", handleNetworkConfig);
  server.onNotFound(    handleNotFound);
  server.begin();
  Serial.println("Server started!");
}

// ─────────────────────────────────────────────────────────────────────────────
// Loop
// ─────────────────────────────────────────────────────────────────────────────

void loop() {
  server.handleClient();

  if (pendingNetworkApply) {
    pendingNetworkApply = false;
    Serial.println("[NET] Applying requested network changes...");
    connectWithCurrentNetworkConfig();
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost, reconnecting...");
    WiFi.reconnect();
    delay(5000);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pulse output
// ─────────────────────────────────────────────────────────────────────────────

void activateSwitch() {
  Serial.printf("Sending %d pulses — ON:%dms OFF:%dms\n", numPulses, pulseOnMs, pulseOffMs);
  for (int i = 0; i < numPulses; i++) {
    digitalWrite(SW_PIN, HIGH);
    delay(pulseOnMs);
    digitalWrite(SW_PIN, LOW);
    delay(pulseOffMs);
    Serial.printf("Pulse %d/%d sent\n", i + 1, numPulses);
  }
  Serial.println("All pulses sent.");
}

#endif