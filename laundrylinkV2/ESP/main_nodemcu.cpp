#if defined(ARDUINO_ARCH_ESP8266)

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// Hardcoded Network Config
const char* WIFI_SSID     = "JRKTech";
const char* WIFI_PASSWORD = "Nayr0505";

// Phone hotspots usually assign a dynamic subnet, so DHCP is safer by default.
const bool USE_STATIC_IP = true;
bool useStaticIp = USE_STATIC_IP;

IPAddress local_IP(192, 168, 0, 56);
IPAddress gateway(192, 168, 0, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(8, 8, 8, 8);

bool pendingNetworkApply = false;

// Hardware-locked output pin: NodeMCU D1 = GPIO5
#define SW_PIN 5
// Dedicated life-check beep pin: NodeMCU D8 = GPIO15
#define LIFE_BEEP_PIN 15

// Guardrails for externally provided pulse configuration.
const int MIN_PULSE_MS = 50;
const int MAX_PULSE_MS = 3000;
const int MIN_PULSE_COUNT = 1;
const int MAX_PULSE_COUNT = 20;

// Pulse Config (overridden by UI)
int pulseOnMs  = 500;
int pulseOffMs = 500;
int numPulses  = 3;

const uint8_t PIN_SCAN_CANDIDATES[] = {12, 14, 13, 15, 5, 4};

const char* wifiStatusText(int status) {
  switch (status) {
    case WL_IDLE_STATUS: return "IDLE";
    case WL_NO_SSID_AVAIL: return "NO_SSID";
    case WL_SCAN_COMPLETED: return "SCAN_DONE";
    case WL_CONNECTED: return "CONNECTED";
    case WL_CONNECT_FAILED: return "CONNECT_FAILED";
    case WL_CONNECTION_LOST: return "CONNECTION_LOST";
    case WL_DISCONNECTED: return "DISCONNECTED";
    default: return "UNKNOWN";
  }
}

void printHotspotScan() {
  Serial.println("[WIFI] Scanning nearby SSIDs...");
  int count = WiFi.scanNetworks();
  if (count <= 0) {
    Serial.println("[WIFI] No networks found in scan.");
    return;
  }

  bool foundTarget = false;
  for (int i = 0; i < count; i++) {
    String ssid = WiFi.SSID(i);
    int32_t rssi = WiFi.RSSI(i);
    uint8_t enc = WiFi.encryptionType(i);
    int32_t chan = WiFi.channel(i);

    if (ssid == WIFI_SSID) {
      foundTarget = true;
    }

    Serial.printf("[WIFI] %2d) SSID='%s' RSSI=%lddBm CH=%ld ENC=%u\n",
      i + 1, ssid.c_str(), (long)rssi, (long)chan, (unsigned int)enc);
  }

  if (!foundTarget) {
    Serial.println("[WIFI][HINT] Target SSID not visible. Check hotspot is ON, 2.4GHz, and in range.");
  }
}

const char* gpioToNodeMcuLabel(uint8_t gpio) {
  switch (gpio) {
    case 16: return "D0";
    case 5: return "D1";
    case 4: return "D2";
    case 0: return "D3";
    case 2: return "D4";
    case 14: return "D5";
    case 12: return "D6";
    case 13: return "D7";
    case 15: return "D8";
    default: return "UNKNOWN";
  }
}

void runPinScan() {
  const size_t pinCount = sizeof(PIN_SCAN_CANDIDATES) / sizeof(PIN_SCAN_CANDIDATES[0]);
  const int onMs = 2000;
  const int offMs = 1000;

  Serial.println("[PINSCAN] Starting output scan.");
  Serial.println("[PINSCAN] Probe module SW vs N while this runs.");

  for (size_t i = 0; i < pinCount; i++) {
    uint8_t gpio = PIN_SCAN_CANDIDATES[i];
    const char* label = gpioToNodeMcuLabel(gpio);

    pinMode(gpio, OUTPUT);
    digitalWrite(gpio, LOW);
    delay(100);

    Serial.printf("[PINSCAN] Testing %s (GPIO%u) HIGH for %dms\n", label, gpio, onMs);
    digitalWrite(gpio, HIGH);
    delay(onMs);
    digitalWrite(gpio, LOW);
    Serial.printf("[PINSCAN] %s (GPIO%u) LOW for %dms\n", label, gpio, offMs);
    delay(offMs);
  }

  Serial.println("[PINSCAN] Completed. All candidate pins set LOW.");
}

void activateSwitch(uint8_t gpio);
void beepLifeCheck();
ESP8266WebServer server(80);
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
    Serial.printf("[NET] Reconnect failed. Status=%d (%s)\n", WiFi.status(), wifiStatusText(WiFi.status()));
  }
}

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
      &#9654; START MACHINE
    </button>
  </div>

  <div class="footer">LaundryLink v1.0 - NodeMCU Mode</div>

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

void handleRoot() {
  server.send(200, "text/html", htmlPage);
}

int parseClampedArg(const String& value, int fallback, int minVal, int maxVal) {
  int parsed = value.toInt();
  if (parsed < minVal || parsed > maxVal) {
    return fallback;
  }
  return parsed;
}

void handleControl() {
  if (machineState) {
    server.send(409, "text/plain", "BUSY");
    return;
  }

  if (server.hasArg("on")) {
    pulseOnMs = parseClampedArg(server.arg("on"), pulseOnMs, MIN_PULSE_MS, MAX_PULSE_MS);
  }
  if (server.hasArg("off")) {
    pulseOffMs = parseClampedArg(server.arg("off"), pulseOffMs, MIN_PULSE_MS, MAX_PULSE_MS);
  }
  if (server.hasArg("count")) {
    numPulses = parseClampedArg(server.arg("count"), numPulses, MIN_PULSE_COUNT, MAX_PULSE_COUNT);
  }

  Serial.printf("Config -> PIN:%s(GPIO%u) ON:%dms OFF:%dms PULSES:%d\n",
    gpioToNodeMcuLabel(SW_PIN), SW_PIN, pulseOnMs, pulseOffMs, numPulses);

  machineState = true;
  activateSwitch(SW_PIN);
  machineState = false;

  server.send(200, "text/plain", "DONE");
}

void handleStatus() {
  server.send(200, "text/plain", machineState ? "BUSY" : "IDLE");
}

void handlePinScan() {
  if (machineState) {
    server.send(409, "text/plain", "BUSY");
    return;
  }

  machineState = true;
  server.send(200, "text/plain", "PINSCAN_STARTED");
  runPinScan();
  machineState = false;
}

void handleLifeCheck() {
  if (machineState) {
    server.send(409, "text/plain", "BUSY");
    return;
  }

  machineState = true;
  beepLifeCheck();
  machineState = false;
  server.send(200, "text/plain", "ALIVE");
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

void setup() {
  delay(8000);
  Serial.begin(115200);
  Serial.println("Booting NodeMCU...");

  for (size_t i = 0; i < sizeof(PIN_SCAN_CANDIDATES) / sizeof(PIN_SCAN_CANDIDATES[0]); i++) {
    pinMode(PIN_SCAN_CANDIDATES[i], OUTPUT);
    digitalWrite(PIN_SCAN_CANDIDATES[i], LOW);
  }

  pinMode(LIFE_BEEP_PIN, OUTPUT);
  digitalWrite(LIFE_BEEP_PIN, LOW);

  Serial.printf("[CFG] SSID: %s\n", WIFI_SSID);
  Serial.printf("[CFG] IP_MODE: %s\n", useStaticIp ? "STATIC" : "DHCP");
  if (useStaticIp) {
    Serial.print("[CFG] STATIC_IP: ");
    Serial.println(local_IP);
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);

  printHotspotScan();

  Serial.print("Connecting to WiFi");
  connectWithCurrentNetworkConfig();

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (++attempts >= 40) {
      int status = WiFi.status();
      Serial.printf("\n[ERROR] WiFi timed out. Status=%d (%s)\n", status, wifiStatusText(status));
      Serial.println("[HINT] Use WPA2 hotspot, 2.4GHz band, and avoid hidden SSID.");
      return;
    }
  }

  Serial.println();
  Serial.println("WiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  server.on("/", handleRoot);
  server.on("/control", handleControl);
  server.on("/status", handleStatus);
  server.on("/pinscan", handlePinScan);
  server.on("/life", handleLifeCheck);
  server.on("/network/info", handleNetworkInfo);
  server.on("/network/config", handleNetworkConfig);
  server.onNotFound(handleNotFound);
  server.begin();
  Serial.println("Server started!");
}

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

void activateSwitch(uint8_t gpio) {
  pinMode(gpio, OUTPUT);
  digitalWrite(gpio, LOW);

  Serial.printf("Sending %d pulses on %s(GPIO%u) - ON:%dms OFF:%dms\n",
    numPulses, gpioToNodeMcuLabel(gpio), gpio, pulseOnMs, pulseOffMs);
  for (int i = 0; i < numPulses; i++) {
    digitalWrite(gpio, HIGH);
    delay(pulseOnMs);
    digitalWrite(gpio, LOW);
    delay(pulseOffMs);
    Serial.printf("Pulse %d/%d sent\n", i + 1, numPulses);
  }
  Serial.println("All pulses sent.");
}

void beepLifeCheck() {
  const int beepMs = 100;
  const int gapMs = 100;

  Serial.printf("[LIFE] Beeping on %s(GPIO%u)\n", gpioToNodeMcuLabel(LIFE_BEEP_PIN), LIFE_BEEP_PIN);
  for (int i = 0; i < 2; i++) {
    digitalWrite(LIFE_BEEP_PIN, HIGH);
    delay(beepMs);
    digitalWrite(LIFE_BEEP_PIN, LOW);
    if (i == 0) {
      delay(gapMs);
    }
  }
}

#endif
