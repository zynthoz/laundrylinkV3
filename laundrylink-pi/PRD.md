# PRD: LaundryLink — Raspberry Pi Migration

## Project Description
Migrate LaundryLink from a single ESP32-hosted web interface into a three-tier architecture where the Raspberry Pi serves as the local location manager. The Pi sits on the same LAN as ESP32 devices, acts as the intermediary for operators, and syncs transactions to a cloud backend.

**Tiers:**
1. **ESP32** — hardware pulse controller only (already built, not modified)
2. **Raspberry Pi** — local location manager, operator UI, offline-first data layer (this project)
3. **Cloud Server** — multi-tenant SaaS backend

## Hardware Context
- Machine: LG FH069FDP Commercial Washer
- Vend price: 60 pesos (rgpr = 60), coin value 5 pesos/pulse
- Washer: 2 pulses, 50ms ON / 50ms OFF (hardware verified)
- Dryer: 4 pulses, 50ms ON / 50ms OFF (hardware verified)
- ESP32 board: DOIT DevKit V1, GPIO32 through PC817 optocoupler

---

## Task List

### Phase 1: ESP32 Audit & Compatibility Check
- [x] **Task 1.1** — Read all existing ESP32 source files and understand current implementation
- [x] **Task 1.2** — Confirm ESP32 endpoints match migration spec (`/control`, `/status`)
- [x] **Task 1.3** — Confirm .env structure is consistent between ESP32 and Pi layers
- [x] **Task 1.4** — Flag any inconsistencies between ESP32 firmware and migration spec
  - *Finding:* ESP32 defaults (500ms/500ms/3 pulses) differ from hardware-tested values (50ms/50ms/2 pulses). Not a functional issue — Pi sends explicit params, overriding defaults.

### Phase 2: Pi Project Structure & Configuration
- [x] **Task 2.1** — Create `laundrylink-pi/` directory with `routes/` and `services/` subdirectories
- [x] **Task 2.2** — Create `requirements.txt` with pinned dependencies (flask, requests, python-dotenv, apscheduler)
- [x] **Task 2.3** — Create `.env.example` with all required keys and placeholder values
- [x] **Task 2.4** — Add `__init__.py` files to `routes/` and `services/` packages

### Phase 3: Database Layer
- [x] **Task 3.1** — Create `database.py` with SQLite init (machines + transactions tables)
- [x] **Task 3.2** — Implement machine CRUD helpers (upsert, get_all, get_one, update_status)
- [x] **Task 3.3** — Implement transaction helpers (insert, get_recent, get_unsynced, mark_synced)
- [x] **Task 3.4** — Ensure all SQL uses parameterized queries (no string concatenation)

### Phase 4: ESP32 Communication Service
- [x] **Task 4.1** — Create `services/esp32.py` with `send_pulse()` function
- [x] **Task 4.2** — Implement dynamic timeout calculation: `((pulse_on + pulse_off) * pulse_count / 1000) + 5`
- [x] **Task 4.3** — Implement `get_esp32_status()` returning BUSY/IDLE/OFFLINE
- [x] **Task 4.4** — Add timestamped console logging for all ESP32 interactions

### Phase 5: Cloud Sync Service
- [x] **Task 5.1** — Create `services/sync.py` with APScheduler background job (60s interval)
- [x] **Task 5.2** — Implement `sync_transactions()` — POST unsynced to cloud, mark synced on success
- [x] **Task 5.3** — Implement `try_immediate_sync()` for post-transaction sync attempts
- [x] **Task 5.4** — Handle cloud unreachable gracefully (log `[QUEUED]`, leave synced=0)

### Phase 6: Flask Routes
- [x] **Task 6.1** — Create `routes/machines.py` blueprint with `GET /machines`
- [x] **Task 6.2** — Implement `POST /machines/<id>/start` with full business logic flow
- [x] **Task 6.3** — Implement `GET /machines/<id>/status` with ESP32 polling
- [x] **Task 6.4** — Create `routes/transactions.py` blueprint with `GET /transactions`
- [x] **Task 6.5** — Implement dev mode simulation (SIMULATED status when ESP32 unreachable)
- [x] **Task 6.6** — Implement production mode error response (502 when ESP32 unreachable)

### Phase 7: Application Entry Point
- [x] **Task 7.1** — Create `app.py` with Flask app factory
- [x] **Task 7.2** — Implement startup .env validation (fail fast on missing keys)
- [x] **Task 7.3** — Implement dynamic machine loading from .env (regex pattern MACHINE_*_IP)
- [x] **Task 7.4** — Upsert loaded machines into SQLite on startup
- [x] **Task 7.5** — Print boot summary (loaded machines, IPs, pulse configs, server URL)
- [x] **Task 7.6** — Wire dev/prod host binding (127.0.0.1 vs 0.0.0.0)

### Phase 8: Integration Testing & Validation
- [x] **Task 8.1** — Run `python app.py` in dev mode and verify boot output
- [x] **Task 8.2** — Test `GET /machines` returns configured machines
- [x] **Task 8.3** — Test `POST /machines/w1/start` records transaction (dev mode simulation)
- [x] **Task 8.4** — Test `GET /transactions` returns recorded transactions
- [x] **Task 8.5** — Test `GET /machines/w1/status` returns OFFLINE (no ESP32 on dev machine)
- [x] **Task 8.6** — Verify SQLite database file is created with correct schema

### Phase 9: Cloud Server Backend
- [x] **Task 9.1** — Design cloud API schema for multi-tenant transaction ingestion
- [x] **Task 9.2** — Implement cloud `POST /api/transactions` endpoint
- [x] **Task 9.3** — Implement cloud authentication (API key validation)
- [x] **Task 9.4** — Build owner dashboard for viewing location data
- [x] **Task 9.5** — Create cloud `app.py` entry point with demo data seeding
- [x] **Task 9.6** — End-to-end integration test: Pi start → cloud sync → dashboard visible

---

## Completion Status
- **Phase 1:** 4/4 done
- **Phase 2:** 4/4 done
- **Phase 3:** 4/4 done
- **Phase 4:** 4/4 done
- **Phase 5:** 4/4 done
- **Phase 6:** 6/6 done
- **Phase 7:** 6/6 done
- **Phase 8:** 6/6 done
- **Phase 9:** 6/6 done
