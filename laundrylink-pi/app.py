import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify
from database import get_all_machines, init_db, upsert_machine
from routes import (
    dashboard_bp,
    inventory_bp,
    machines_bp,
    reports_bp,
    shifts_bp,
    transactions_bp,
)
from services.sync import init_sync, is_sync_enabled
from services.emailing import init_email_scheduler

load_dotenv()


# Optional code-level machine definitions.
# Add entries here if you want machine IPs hardcoded in code instead of .env.
# Environment entries (MACHINE_<ID>_*) with the same id will override these values.
HARDCODED_MACHINES = [
    # {
    #     "id": "w1",
    #     "name": "Washer 1",
    #     "type": "washer",
    #     "machine_function": "standard",
    #     "esp32_ip": "192.168.1.50",
    #     "pulse_on": 50,
    #     "pulse_off": 50,
    #     "pulse_count": 2,
    #     "quick_wash_pulse_count": 1,
    #     "vend_price": 60,
    #     "quick_wash_price": 60,
    # },
]


def validate_env():
    """No validation needed for strictly local mode."""
    pass


def get_cloud_config():
    """Always return None for strictly local mode."""
    return None


def load_machines():
    """Parse MACHINE_* keys from environment and return machine config list."""
    machine_pattern = re.compile(r"^MACHINE_([A-Z0-9]+)_IP$")
    machines_by_id = {}

    for machine in HARDCODED_MACHINES:
        machine_id = str(machine.get("id") or "").strip().lower()
        if not machine_id:
            continue
        machines_by_id[machine_id] = {
            "id": machine_id,
            "name": str(machine.get("name") or machine_id).strip(),
            "type": str(machine.get("type") or "washer").strip().lower(),
            "machine_function": str(machine.get("machine_function") or "standard").strip() or "standard",
            "esp32_ip": str(machine.get("esp32_ip") or "").strip(),
            "pulse_on": int(machine.get("pulse_on", 50)),
            "pulse_off": int(machine.get("pulse_off", 50)),
            "pulse_count": int(machine.get("pulse_count", 2)),
            "vend_price": int(machine.get("vend_price", 60)),
            "quick_wash_pulse_count": int(machine.get("quick_wash_pulse_count", 1)),
            "quick_wash_price": int(machine.get("quick_wash_price", machine.get("vend_price", 60))),
        }

    for key, value in os.environ.items():
        match = machine_pattern.match(key)
        if not match:
            continue

        machine_key = match.group(1)
        prefix = f"MACHINE_{machine_key}_"

        ip = value
        name = os.environ.get(f"{prefix}NAME", machine_key)
        machine_type = os.environ.get(f"{prefix}TYPE", "washer")
        machine_function = os.environ.get(f"{prefix}FUNCTION", "standard")
        pulse_on = int(os.environ.get(f"{prefix}PULSE_ON", "50"))
        pulse_off = int(os.environ.get(f"{prefix}PULSE_OFF", "50"))
        pulse_count = int(os.environ.get(f"{prefix}PULSE_COUNT", "2"))
        vend_price = int(os.environ.get(f"{prefix}VEND_PRICE", "60"))
        quick_wash_pulse_count = int(os.environ.get(f"{prefix}QUICK_WASH_PULSE_COUNT", "1"))
        quick_wash_price = int(os.environ.get(f"{prefix}QUICK_WASH_PRICE", str(vend_price)))

        machine_id = machine_key.lower()

        machines_by_id[machine_id] = {
            "id": machine_id,
            "name": name,
            "type": machine_type,
            "machine_function": machine_function,
            "esp32_ip": ip,
            "pulse_on": pulse_on,
            "pulse_off": pulse_off,
            "pulse_count": pulse_count,
            "vend_price": vend_price,
            "quick_wash_pulse_count": quick_wash_pulse_count,
            "quick_wash_price": quick_wash_price,
        }

    return list(machines_by_id.values())


def create_app():
    # Ensure schema/migrations are applied even when launched via app factory
    # (e.g., flask run / WSGI), not only through main().
    init_db()

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "service": "LaundryLink Pi",
            "status": "ok",
            "mode": "cloud-sync" if is_sync_enabled() else "local-only",
            "routes": [
                "/",
                "/health",
                "/machines",
                "/machines/<machine_id>/start",
                "/machines/<machine_id>/stop",
                "/machines/<machine_id>/status",
                "/employees",
                "/shifts/active",
                "/shifts/time-in",
                "/shifts/time-out",
                "/catalog/products",
                "/catalog/services",
                "/inventory/low-stock",
                "/dashboard/summary/shift",
                "/dashboard/summary/day",
                "/dashboard/summary/calendar",
                "/dashboard/machines/runtime",
                "/expenses/manual",
                "/reports/shift/<shift_id>/receipt",
                "/reports/day/<YYYY-MM-DD>/receipt",
                "/reports/shifts/recent/print",
                "/reports/print-jobs",
                "/transactions",
            ],
        })

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(machines_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(transactions_bp)

    # Start the background email scheduler
    init_email_scheduler(app)

    return app


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}")
    print(f"  LaundryLink Pi — Local Manager")
    print(f"  Started at {timestamp}")
    print(f"{'='*50}\n")

    validate_env()

    cloud_config = get_cloud_config()
    location_id = os.environ.get("LOCATION_ID", "local")

    print(f"Location ID:  {location_id}")
    if cloud_config:
        print(f"Cloud URL:    {cloud_config['cloud_url']}")
    else:
        print("Cloud URL:    <disabled>")
    print()

    init_db()
    print("Database initialized.\n")

    env_machines = load_machines()
    existing_machines = get_all_machines()

    if not existing_machines and env_machines:
        print("Seeding machines from environment into SQLite (first-run bootstrap).")
        for m in env_machines:
            upsert_machine(
                m["id"], m["name"], m["type"], m["machine_function"], m["esp32_ip"],
                m["pulse_on"], m["pulse_off"], m["pulse_count"], m["vend_price"],
                m["quick_wash_pulse_count"], m["quick_wash_price"],
            )
        print()
    elif existing_machines and env_machines:
        print("SQLite machine registry already populated. Skipping environment machine sync.")
        print()
    elif not env_machines:
        print("No MACHINE_<ID>_IP environment entries found. Using machines stored in SQLite.")
        print()

    machines = get_all_machines()

    if not machines:
        print("No machines configured yet. Add machines from Settings > Machine Registry in the dashboard.")
        print()

    for m in machines:
        print(f"  Machine: {m['name']}")
        print(f"    ID:       {m['id']}")
        print(f"    Type:     {m['type']}")
        print(f"    Function: {m.get('machine_function', 'standard')}")
        print(f"    ESP32 IP: {m['esp32_ip']}")
        print(f"    Pulses:   {m['pulse_count']}x @ {m['pulse_on']}ms ON / {m['pulse_off']}ms OFF")
        print(f"    Vend:     {m['vend_price']} pesos")
        print()

    if cloud_config:
        init_sync(
            cloud_config["cloud_url"],
            cloud_config["api_key"],
            cloud_config["location_id"],
        )
    else:
        print("Cloud sync:   disabled (running fully local with SQLite only)")
        print()

    is_dev = os.environ.get("FLASK_ENV", "development") == "development"
    host = "127.0.0.1" if is_dev else "0.0.0.0"
    port = int(os.environ.get("PORT", "5000"))

    print(f"Server: http://{host}:{port}")
    print(f"Mode:   {'development' if is_dev else 'production'}\n")

    app = create_app()
    app.run(host=host, port=port, debug=is_dev)


if __name__ == "__main__":
    main()
