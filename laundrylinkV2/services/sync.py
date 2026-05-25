import os
import requests
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_unsynced_transactions, mark_transactions_synced, get_all_machines

CLOUD_URL = None
API_KEY = None
LOCATION_ID = None
SYNC_ENABLED = False

scheduler = BackgroundScheduler(daemon=True)


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_cloud_reachable(cloud_url):
    """Best-effort connectivity probe for cloud backend."""
    try:
        resp = requests.get(cloud_url, timeout=5)
        return 200 <= resp.status_code < 500
    except requests.exceptions.RequestException:
        return False


def init_sync(cloud_url, api_key, location_id):
    global CLOUD_URL, API_KEY, LOCATION_ID, SYNC_ENABLED
    CLOUD_URL = cloud_url
    API_KEY = api_key
    LOCATION_ID = location_id

    if not (CLOUD_URL and API_KEY and LOCATION_ID):
        SYNC_ENABLED = False
        print(f"[{_timestamp()}] Cloud sync disabled: missing cloud configuration")
        return

    SYNC_ENABLED = True

    if not _is_cloud_reachable(CLOUD_URL):
        SYNC_ENABLED = False
        print(f"[{_timestamp()}] Cloud unreachable at startup. Running in local-only mode.")
        return

    scheduler.add_job(sync_transactions, "interval", seconds=60, id="cloud_sync", replace_existing=True)
    scheduler.add_job(sync_machines, "interval", seconds=120, id="machine_sync", replace_existing=True)
    scheduler.start()
    print(f"[{_timestamp()}] Background sync scheduler started (transactions: 60s, machines: 120s)")

    # Sync machines immediately on startup
    sync_machines()


def sync_transactions():
    """Push unsynced transactions to cloud. Mark synced on success."""
    if not SYNC_ENABLED:
        return

    timestamp = _timestamp()
    unsynced = get_unsynced_transactions()

    if not unsynced:
        return

    print(f"[{timestamp}] Syncing {len(unsynced)} transaction(s) to cloud...")

    url = f"{CLOUD_URL}/api/transactions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "location_id": LOCATION_ID,
        "transactions": unsynced,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201):
            synced_ids = [t["id"] for t in unsynced]
            mark_transactions_synced(synced_ids)
            print(f"[{timestamp}] Synced {len(synced_ids)} transaction(s) successfully")
        else:
            print(f"[{timestamp}] Cloud sync failed: HTTP {resp.status_code} — {resp.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"[{timestamp}] [QUEUED] Cloud unreachable: {e}")


def try_immediate_sync():
    """Attempt a one-off sync right after recording a transaction."""
    if not SYNC_ENABLED:
        return

    try:
        sync_transactions()
    except Exception as e:
        timestamp = _timestamp()
        print(f"[{timestamp}] [QUEUED] Immediate sync failed: {e}")


def sync_machines():
    """Push machine registry to cloud so the dashboard can display them."""
    if not SYNC_ENABLED:
        return

    timestamp = _timestamp()
    machines = get_all_machines()
    if not machines:
        return

    url = f"{CLOUD_URL}/api/machines"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "location_id": LOCATION_ID,
        "machines": machines,
        "pi_url": f"http://127.0.0.1:{os.environ.get('PORT', '5000')}",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            print(f"[{timestamp}] Synced {len(machines)} machine(s) to cloud")
        else:
            print(f"[{timestamp}] Machine sync failed: HTTP {resp.status_code} — {resp.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"[{timestamp}] Machine sync unreachable: {e}")


def is_sync_enabled():
    return SYNC_ENABLED
