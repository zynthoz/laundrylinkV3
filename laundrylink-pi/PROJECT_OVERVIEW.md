# LaundryLink Pi — Project Overview

## What Is LaundryLink?

LaundryLink is a **three-tier IoT system** that automates commercial laundry machine vending. It replaces traditional physical coin mechanisms with software-controlled pulse signals, enabling **cashless operation**, **remote monitoring**, and **centralized transaction logging** across multiple laundromat locations.

---

## Purpose

Commercial laundry machines (e.g., LG FH069FDP washers and compatible dryers) typically require physical coin insertion to operate. LaundryLink eliminates this limitation by:

- **Simulating coin credits** via precisely timed electrical pulses sent through an optocoupler to the machine's coin input
- **Centralizing machine control** through the Raspberry Pi, so operators can start machines from a single local API instead of manually feeding coins
- **Enabling remote visibility** for business owners through a cloud dashboard that aggregates transactions and machine status across all locations
- **Ensuring reliability** with an offline-first architecture — transactions are always recorded locally first and synced to the cloud when connectivity is available

--
-

## System Architecture

LaundryLink is divided into three tiers, each with a distinct role:

```
┌─────────────┐     HTTP (LAN)     ┌─────────────┐     HTTP (WAN)     ┌─────────────┐
│   ESP32(s)  │◄──────────────────►│ Raspberry Pi │───────────────────►│   Cloud      │
│  GPIO pulse │  /control, /status │  Flask + SQL │  /api/transactions │  Flask + SQL │
│  controller │                    │  Port 5000   │                    │  Port 4000   │
└─────────────┘                    └─────────────┘                    └─────────────┘
```

| Tier | Device | Role |
|------|--------|------|
| **Tier 1** | ESP32 (DOIT DevKit V1) | Hardware pulse controller — sends coin-simulating pulses to the machine's optocoupler via GPIO32 |
| **Tier 2** | Raspberry Pi *(this project)* | Local location manager — operator API, offline-first SQLite database, ESP32 orchestration, cloud sync |
| **Tier 3** | Cloud Server | Multi-tenant SaaS backend — owner dashboard, transaction aggregation, machine status overview |

---

## Goals

### 1. Cashless Machine Operation
Replace the need for physical coins with API-driven pulse control. An operator sends a single HTTP request to the Pi, which translates it into the precise pulse sequence the machine expects.

### 2. Offline-First Reliability
Every transaction is written to a local SQLite database **before** any cloud sync is attempted. If the cloud is unreachable, transactions queue locally and automatically sync on the next cycle (every 60 seconds). No transaction is ever lost.

### 3. Multi-Location Scalability
Each Raspberry Pi manages one physical location. Multiple Pi units can independently sync to the same cloud backend, giving business owners a unified view of all their laundromat locations from a single dashboard.

### 4. Zero-Code Machine Management
Adding a new machine requires only adding environment variables to the Pi's `.env` file — no code changes. The Pi dynamically discovers machines on startup via regex pattern matching on `MACHINE_<KEY>_*` variables.

### 5. Dev/Prod Flexibility
The system supports seamless development without hardware. In development mode (`FLASK_ENV=development`), if an ESP32 is unreachable, the Pi simulates the operation and logs it as `SIMULATED`. In production, unreachable hardware returns a `502` error.

### 6. Operator Simplicity
Starting a machine is one command:
```bash
curl -X POST http://<pi-ip>:5000/machines/w1/start
```
The Pi handles all the complexity: looking up machine config, sending the correct pulse parameters to the right ESP32, recording the transaction, and syncing to the cloud.

---

## The Pi's Role (This Project)

The `laundrylink-pi` component is the **central orchestration layer** of the system. It:

1. **Receives operator commands** via a Flask REST API
2. **Communicates with ESP32 devices** over the local network to trigger machine operations
3. **Records all transactions** in a local SQLite database with full audit trail
4. **Syncs data to the cloud** via background jobs (transactions every 60s, machine registry every 120s)
5. **Provides machine status** by polling ESP32 endpoints and reporting `IDLE`, `BUSY`, or `OFFLINE`

### Key Components

| File | Responsibility |
|------|---------------|
| `app.py` | Entry point — config loading, machine discovery, server startup |
| `database.py` | SQLite data layer — machines and transactions tables |
| `routes/machines.py` | Machine API endpoints (list, start, status) |
| `routes/transactions.py` | Transaction listing endpoint |
| `services/esp32.py` | HTTP communication with ESP32 controllers |
| `services/sync.py` | Background cloud sync via APScheduler |

---

## Hardware Context

- **Target Machine:** LG FH069FDP Commercial Washer (and compatible dryers)
- **Washer:** 2 pulses × 50ms ON / 50ms OFF → 60 pesos
- **Dryer:** 4 pulses × 50ms ON / 50ms OFF → 20 pesos
- **Coin Value:** 5 pesos per pulse
- **ESP32 Board:** DOIT DevKit V1, GPIO32 through PC817 optocoupler

---

## Current Status

All 9 phases of development are **complete** (40/40 tasks):

- ✅ ESP32 audit & compatibility check
- ✅ Pi project structure & configuration
- ✅ Database layer
- ✅ ESP32 communication service
- ✅ Cloud sync service
- ✅ Flask routes
- ✅ Application entry point
- ✅ Integration testing
- ✅ Cloud server backend

The full three-tier architecture (ESP32 → Pi → Cloud) is built and tested end-to-end.
