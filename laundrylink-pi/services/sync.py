import os
from datetime import datetime

CLOUD_URL = None
API_KEY = None
LOCATION_ID = None
SYNC_ENABLED = False


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_sync(cloud_url, api_key, location_id):
    """Stub initialization for strictly local mode."""
    global CLOUD_URL, API_KEY, LOCATION_ID, SYNC_ENABLED
    CLOUD_URL = None
    API_KEY = None
    LOCATION_ID = None
    SYNC_ENABLED = False
    print(f"[{_timestamp()}] Cloud sync disabled (strictly local mode)")


def sync_transactions():
    """No-op stub for strictly local mode."""
    pass


def try_immediate_sync():
    """No-op stub for strictly local mode."""
    pass


def sync_machines():
    """No-op stub for strictly local mode."""
    pass


def is_sync_enabled():
    """Always return False in strictly local mode."""
    return False
