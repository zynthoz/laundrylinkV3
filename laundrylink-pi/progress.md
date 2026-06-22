# Progress Log: LaundryLink Pi Migration

## Session 1 — Initial Build (Phases 1–7)

### Tasks Attempted
All of Phase 1 through Phase 7 (28 tasks total).

### What Happened
All 28 tasks completed successfully in a single session.

### Approach
1. Read all existing ESP32 files (`src/main.cpp`, `.env.example`, `platformio.ini`)
2. Explored full project structure — confirmed no Python/Pi code existed yet
3. Audited ESP32 endpoints against migration spec — confirmed match
4. Flagged one inconsistency: ESP32 firmware defaults (500ms/500ms/3 pulses) differ from hardware-tested values (50ms/50ms/2), but this is not functional since the Pi sends explicit params
5. Built all Pi files bottom-up: database → services → routes → app.py → config files

### Files Created
```
laundrylink-pi/
├── app.py
├── database.py
├── .env.example
├── requirements.txt
├── routes/__init__.py
├── routes/machines.py
├── routes/transactions.py
├── services/__init__.py
├── services/esp32.py
└── services/sync.py
```

### Patterns & Insights
- Dynamic machine discovery via regex on env vars works well — avoids hardcoding
- SQLite WAL mode chosen for concurrent read safety with APScheduler background thread
- `upsert_machine()` with `ON CONFLICT DO UPDATE` means .env changes apply on reboot without manual DB cleanup
- Dev/prod split on `FLASK_ENV` keeps the same codebase deployable locally and on Pi

### Known Issues
- None blocking. All code follows the spec.

### Next Steps
- **Phase 8**: Integration testing — run the app, hit all endpoints, verify DB creation
- **Phase 9**: Cloud server backend (future scope, out of current migration)

---

## Session 2 — Ralph Loop Setup

### Tasks Attempted
Create PRD.md, implementation.md, and progress.md for Ralph Loop workflow.

### What Happened
Created all three documents reflecting the current state of the project. PRD shows Phases 1-7 complete (28/28 tasks), Phase 8 (integration testing) as next, Phase 9 (cloud) as future.

### Next Steps
- Begin Phase 8: Task 8.1 — Run `python app.py` in dev mode and verify boot output

---

## Session 3 — Integration Testing (Phase 8)

### Tasks Attempted
All 6 tasks in Phase 8 (integration testing).

### What Happened
All 6 tasks passed on first attempt.

### Test Results
| Task | Endpoint | Expected | Actual | Status |
|---|---|---|---|---|
| 8.1 | `python app.py` | Boot with machine listing | 2 machines printed with correct configs | PASS |
| 8.2 | `GET /machines` | JSON array of 2 machines | Both W1 and D1 returned with correct fields | PASS |
| 8.3 | `POST /machines/w1/start` | SIMULATED transaction | `{"status":"SIMULATED","transaction_id":"...","amount":60}` | PASS |
| 8.4 | `GET /transactions` | Array with recorded transaction | 1 transaction, synced=0, amount=60 | PASS |
| 8.5 | `GET /machines/w1/status` | OFFLINE (no ESP32) | `{"status":"OFFLINE"}` | PASS |
| 8.6 | SQLite schema | machines + transactions tables | Both tables match spec exactly | PASS |

### Boot Output Verified
```
LaundryLink Pi — Local Manager
Location ID:  loc_001
Cloud URL:    http://localhost:4000
Database initialized.
Machine: Washer 1 — 2x @ 50ms ON / 50ms OFF — 60 pesos
Machine: Dryer 1  — 4x @ 50ms ON / 50ms OFF — 20 pesos
Background sync scheduler started (every 60s)
Server: http://127.0.0.1:5000 — development
```

### Issues Encountered
- `pip install` failed on global Python due to Windows permission error. Resolved with `--user` flag.

### Next Steps
- Phase 9 (Cloud Server Backend) is future scope — not part of current Pi migration task.

---

## Session 4 — Cloud Server Backend (Phase 9)

### Tasks Attempted
All 6 tasks in Phase 9 (cloud server backend).

### What Happened
All 6 tasks completed and integration test passed on first attempt.

### Approach
1. Read the Pi's `sync.py` to understand the exact HTTP contract (endpoint, headers, payload format)
2. Built cloud server matching that contract exactly
3. Multi-tenant schema: owners -> api_keys -> locations -> transactions
4. `require_api_key` decorator validates Bearer token and enforces location ownership
5. Demo data auto-seeded on startup (owner_001 / sk_test_abc123 / loc_001) matching Pi .env defaults
6. Dashboard uses same visual style as ESP32 UI (Space Mono + DM Sans, dark theme)

### Files Created
```
laundrylink-cloud/
├── app.py
├── database.py
├── .env.example
├── requirements.txt
├── routes/__init__.py
├── routes/api.py
├── routes/dashboard.py
└── templates/dashboard.html
```

### Integration Test Results
| Step | Action | Result |
|---|---|---|
| 1 | `POST /machines/w1/start` on Pi | Transaction recorded as SIMULATED, amount=60 |
| 2 | Pi immediate sync fires | `POST /api/transactions` sent to cloud on port 4000 |
| 3 | Cloud receives, inserts | 1 transaction in cloud DB with synced_at timestamp |
| 4 | Pi marks synced | Pi DB shows `synced=1` for the transaction |
| 5 | Dashboard renders | Transaction visible on cloud dashboard at `http://localhost:4000/` |
| 6 | Auth rejection (bad key) | Returns `{"error": "Invalid API key"}` with 401 |
| 7 | Auth rejection (no header) | Returns `{"error": "Missing or malformed Authorization header"}` with 401 |

### Patterns & Insights
- Deduplication via `SELECT id ... WHERE id = ?` before insert prevents duplicate transactions from Pi retry syncs
- `seed_demo_data()` is idempotent — checks existence before inserting, safe for repeated restarts
- Dashboard auto-refreshes every 30s via simple `setTimeout` — no WebSocket needed for MVP
- Cloud only needs `flask` and `python-dotenv` — no `requests` or `apscheduler` since it's a passive receiver

### All Phases Complete
- **Phases 1-9**: 40/40 tasks done
- The entire three-tier architecture (ESP32 -> Pi -> Cloud) is built and tested end-to-end