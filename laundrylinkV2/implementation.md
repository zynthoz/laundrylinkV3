# Implementation: LaundryLink Pi Layer

## Architecture Overview

```
┌──────────────┐     HTTP (LAN)     ┌──────────────┐     HTTP (WAN)     ┌──────────────┐
│   ESP32(s)   │◄───────────────────│  Raspberry Pi │───────────────────►│    Cloud      │
│  GPIO pulse  │  /control, /status │  Flask + SQL  │  /api/transactions │   Backend    │
└──────────────┘                    └──────────────┘                    └──────────────┘
                                          │
                                     SQLite (WAL)
                                    laundrylink.db
```

## File Responsibilities

### `app.py` — Entry Point
- Loads `.env` via python-dotenv
- Validates required keys exist (CLOUD_URL, API_KEY, LOCATION_ID)
- Dynamically discovers machines from `MACHINE_*_IP` env vars using regex
- Upserts machine configs into SQLite on every boot (so .env changes take effect)
- Initializes background sync scheduler
- Starts Flask with dev/prod host binding

### `database.py` — Data Layer
- SQLite with WAL journal mode for concurrent read/write safety
- Two tables: `machines` (config + status) and `transactions` (audit log + sync queue)
- All queries parameterized — no string concatenation
- `upsert_machine()` uses `ON CONFLICT(id) DO UPDATE` for idempotent boot
- `mark_transactions_synced()` uses `IN (?)` with dynamic placeholder generation

### `services/esp32.py` — Hardware Communication
- `send_pulse(ip, on, off, count)` — sends `GET /control?on=X&off=X&count=X`
- Timeout formula: `((on + off) * count / 1000) + 5` seconds
  - For washer (2 pulses, 50ms): timeout = 5.2s
  - For dryer (4 pulses, 50ms): timeout = 5.4s
- `get_esp32_status(ip)` — polls `/status`, returns BUSY/IDLE/OFFLINE

### `services/sync.py` — Cloud Sync
- APScheduler `BackgroundScheduler` runs `sync_transactions()` every 60s
- Finds all `synced=0` transactions, POSTs to `{CLOUD_URL}/api/transactions`
- Uses `Bearer {API_KEY}` authorization header
- On success: marks batch as `synced=1`
- On failure: logs `[QUEUED]`, leaves `synced=0` for next retry
- `try_immediate_sync()` called after each transaction for low-latency sync

### `routes/machines.py` — Machine Endpoints
- `GET /machines` — lists all machines, polls each ESP32 for live status
- `POST /machines/<id>/start` — core business logic:
  1. Look up machine in DB
  2. Send pulse to ESP32
  3. Dev mode: simulate on failure, log `[SIMULATED]`
  4. Prod mode: return 502 on failure
  5. Record transaction with `synced=0`
  6. Attempt immediate cloud sync
- `GET /machines/<id>/status` — polls single ESP32, updates DB status

### `routes/transactions.py` — Transaction Endpoint
- `GET /transactions` — returns last 50 transactions ordered by date DESC

## Key Design Decisions

### Dynamic Machine Discovery
Machines are parsed from `.env` by regex matching `MACHINE_<KEY>_IP`. Adding a new machine (e.g., Washer 2) requires only adding env vars:
```
MACHINE_W2_IP=172.20.10.7
MACHINE_W2_NAME=Washer 2
MACHINE_W2_TYPE=washer
MACHINE_W2_PULSE_ON=50
MACHINE_W2_PULSE_OFF=50
MACHINE_W2_PULSE_COUNT=2
MACHINE_W2_VEND_PRICE=60
```
No code changes needed.

### Dev vs Prod Behavior
Controlled by `FLASK_ENV` environment variable:
| Behavior | Dev (`development`) | Prod (anything else) |
|---|---|---|
| ESP32 unreachable | Simulate, log `[SIMULATED]` | Return 502 error |
| Cloud unreachable | Queue locally, log `[QUEUED]` | Queue locally, log `[QUEUED]` |
| Flask host | `127.0.0.1` | `0.0.0.0` |
| Flask debug | `True` | `False` |

### Offline-First Transaction Recording
Transactions always write to SQLite first with `synced=0`. Cloud sync is best-effort. This guarantees no transaction is ever lost, even if the cloud is down for extended periods.

## ESP32 Endpoint Compatibility Matrix

| Pi calls | ESP32 endpoint | Response | Status |
|---|---|---|---|
| `send_pulse()` | `GET /control?on=50&off=50&count=2` | `"DONE"` | Confirmed working |
| `get_esp32_status()` | `GET /status` | `"BUSY"` or `"IDLE"` | Confirmed working |

## Database Schema

```sql
machines (
    id          TEXT PRIMARY KEY,    -- e.g., "w1", "d1"
    name        TEXT NOT NULL,       -- e.g., "Washer 1"
    type        TEXT NOT NULL,       -- "washer" or "dryer"
    esp32_ip    TEXT NOT NULL,       -- e.g., "172.20.10.5"
    pulse_on    INTEGER DEFAULT 50,
    pulse_off   INTEGER DEFAULT 50,
    pulse_count INTEGER DEFAULT 2,
    vend_price  INTEGER DEFAULT 60,
    status      TEXT DEFAULT 'IDLE'
)

transactions (
    id          TEXT PRIMARY KEY,    -- UUID v4
    machine_id  TEXT NOT NULL,       -- FK to machines.id
    amount      INTEGER NOT NULL,    -- vend price in pesos
    status      TEXT NOT NULL,       -- COMPLETED | SIMULATED
    started_at  TEXT NOT NULL,       -- ISO timestamp
    ended_at    TEXT,                -- nullable
    synced      INTEGER DEFAULT 0   -- 0=pending, 1=synced to cloud
)
```
