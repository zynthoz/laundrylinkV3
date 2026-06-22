import requests
from datetime import datetime
import concurrent.futures

# Global thread pool for ESP32 background tasks
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)


def send_pulse(esp32_ip, pulse_on, pulse_off, pulse_count):
    """Send pulse command to ESP32 and return (success, message)."""
    import os
    if os.environ.get("FLASK_ENV", "development") == "development":
        return True, "SIMULATED"

    url = f"http://{esp32_ip}/control?on={pulse_on}&off={pulse_off}&count={pulse_count}"
    timeout = ((pulse_on + pulse_off) * pulse_count / 1000) + 5

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Sending pulse to {esp32_ip}: on={pulse_on} off={pulse_off} count={pulse_count} (timeout={timeout:.1f}s)")

    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.text.strip() == "DONE":
            print(f"[{timestamp}] Pulse complete from {esp32_ip}: DONE")
            return True, "DONE"
        else:
            print(f"[{timestamp}] Unexpected response from {esp32_ip}: {resp.status_code} {resp.text}")
            return False, f"Unexpected response: {resp.status_code}"
    except requests.exceptions.RequestException as e:
        print(f"[{timestamp}] ESP32 unreachable at {esp32_ip}: {e}")
        return False, f"ESP32 unreachable: {e}"


def async_send_pulse(esp32_ip, pulse_on, pulse_off, pulse_count, callback):
    """
    Asynchronously send pulse and invoke a callback with the results.
    callback signature: def on_result(success: bool, message: str)
    """
    def task():
        success, message = send_pulse(esp32_ip, pulse_on, pulse_off, pulse_count)
        if callback:
            callback(success, message)

    _executor.submit(task)


def get_esp32_status(esp32_ip):
    """Poll ESP32 for current status. Returns 'BUSY', 'IDLE', or 'OFFLINE'."""
    url = f"http://{esp32_ip}/status"
    try:
        resp = requests.get(url, timeout=3)
        status = resp.text.strip()
        if status in ("BUSY", "IDLE"):
            return status
        return "IDLE"
    except requests.exceptions.RequestException:
        return "OFFLINE"


def check_esp32_life(esp32_ip):
    """Trigger NodeMCU/ESP32 life-check endpoint and return (success, message)."""
    import os
    if os.environ.get("FLASK_ENV", "development") == "development":
        return True, "ALIVE (SIMULATED)"

    # NodeMCU firmware life-check beeps on D8 (GPIO15) via /life.
    url = f"http://{esp32_ip}/life?pin=8"
    try:
        resp = requests.get(url, timeout=5)
        body = resp.text.strip()
        body_upper = body.upper()
        if resp.status_code == 200 and ("ALIVE" in body_upper or body_upper in ("DONE", "OK")):
            return True, body or "ALIVE"
        if resp.status_code == 409 and "BUSY" in body_upper:
            return False, "Machine busy; life-check beep not triggered"
        return False, f"Unexpected response: {resp.status_code} {resp.text.strip()}"
    except requests.exceptions.RequestException as e:
        return False, f"ESP32 unreachable: {e}"
