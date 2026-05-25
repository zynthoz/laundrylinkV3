import sqlite3
import os
import uuid
import hashlib
import re
import time
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "laundrylink.db")
DAY_CHANGE_TIME_SETTING_KEY = "day_change_time"
DEFAULT_DAY_CHANGE_TIME = "08:01"
RECEIPT_FORMAT_SETTING_KEY = "receipt_format_config"
RECENT_SHIFT_SUMMARY_COUNT_SETTING_KEY = "recent_shift_summary_count"
DEFAULT_RECEIPT_SHOP_NAME = os.environ.get("RECEIPT_SHOP_NAME", "LOYOLA")
DEFAULT_RECENT_SHIFT_SUMMARY_COUNT = 5
DEFAULT_RECEIPT_FORMAT_CONFIG = {
    "version": 3,
    "shop_name": DEFAULT_RECEIPT_SHOP_NAME,
    "elements": {
        "common.generated_footer": True,
        "shiftday.date_line": True,
        "shiftday.weekday_line": True,
        "shiftday.shift_number_line": True,
        "shiftday.employee_section": True,
        "shiftday.machine_revenue_section": True,
        "shiftday.machine_usage_breakdown": True,
        "shiftday.product_revenue_section": True,
        "shiftday.service_tips_section": True,
        "shiftday.cash_revenue_section": True,
        "shiftday.gcash_revenue_section": True,
        "shiftday.expenses_section": True,
        "shiftday.net_sales_section": True,
        "recent_shifts_summary.date_line": True,
        "recent_shifts_summary.weekday_line": True,
        "recent_shifts_summary.shift_number_line": True,
        "recent_shifts_summary.employee_section": True,
        "recent_shifts_summary.machine_revenue_section": True,
        "recent_shifts_summary.machine_usage_breakdown": True,
        "recent_shifts_summary.product_revenue_section": True,
        "recent_shifts_summary.service_tips_section": True,
        "recent_shifts_summary.cash_revenue_section": True,
        "recent_shifts_summary.gcash_revenue_section": True,
        "recent_shifts_summary.expenses_section": True,
        "recent_shifts_summary.net_sales_section": True,
        "transaction.header_section": True,
        "transaction.customer_section": True,
        "transaction.employee_section": True,
        "transaction.status_line": True,
        "transaction.payment_section": True,
        "transaction.items_section": True,
        "transaction.totals_section": True,
        "bulk.header_section": True,
        "bulk.employee_customer_section": True,
        "bulk.machines_section": True,
        "bulk.addons_section": True,
        "bulk.payment_counts_section": True,
        "bulk.totals_section": True,
        "job_order.header_section": True,
        "job_order.customer_section": True,
        "job_order.machine_section": True,
        "job_order.quantity_section": True,
        "job_order.payment_section": True,
        "job_order.unit_price_section": True,
        "job_order.total_section": True,
        "job_order.cashier_status_section": True,
    },
    "order": {
        "shiftday": [
            "shiftday.date_line",
            "shiftday.weekday_line",
            "shiftday.shift_number_line",
            "shiftday.employee_section",
            "shiftday.machine_revenue_section",
            "shiftday.machine_usage_breakdown",
            "shiftday.product_revenue_section",
            "shiftday.service_tips_section",
            "shiftday.cash_revenue_section",
            "shiftday.gcash_revenue_section",
            "shiftday.expenses_section",
            "shiftday.net_sales_section",
        ],
        "recent_shifts_summary": [
            "recent_shifts_summary.date_line",
            "recent_shifts_summary.weekday_line",
            "recent_shifts_summary.shift_number_line",
            "recent_shifts_summary.employee_section",
            "recent_shifts_summary.machine_revenue_section",
            "recent_shifts_summary.machine_usage_breakdown",
            "recent_shifts_summary.product_revenue_section",
            "recent_shifts_summary.service_tips_section",
            "recent_shifts_summary.cash_revenue_section",
            "recent_shifts_summary.gcash_revenue_section",
            "recent_shifts_summary.expenses_section",
            "recent_shifts_summary.net_sales_section",
        ],
        "transaction": [
            "transaction.header_section",
            "transaction.customer_section",
            "transaction.employee_section",
            "transaction.status_line",
            "transaction.payment_section",
            "transaction.items_section",
            "transaction.totals_section",
        ],
        "bulk": [
            "bulk.header_section",
            "bulk.employee_customer_section",
            "bulk.machines_section",
            "bulk.addons_section",
            "bulk.payment_counts_section",
            "bulk.totals_section",
        ],
        "job_order": [
            "job_order.header_section",
            "job_order.customer_section",
            "job_order.machine_section",
            "job_order.quantity_section",
            "job_order.payment_section",
            "job_order.unit_price_section",
            "job_order.total_section",
            "job_order.cashier_status_section",
        ],
    },
}


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash_pin(pin):
    return hashlib.sha256(str(pin).encode("utf-8")).hexdigest()


def _normalize_phone(phone):
    if phone in (None, ""):
        return None

    digits = re.sub(r"\D", "", str(phone))
    if len(digits) < 10 or len(digits) > 11:
        raise ValueError("phone must be 10 to 11 digits")
    return digits


def _normalize_day_change_time(value):
    raw = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        raise ValueError("day_change_time must be in HH:MM format")

    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("day_change_time must be a valid 24-hour time")

    return f"{hour:02d}:{minute:02d}"


def _normalize_recent_shift_summary_count(value):
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError("recent_shift_summary_count must be a whole number")

    if normalized < 1 or normalized > 30:
        raise ValueError("recent_shift_summary_count must be between 1 and 30")

    return normalized


def _normalize_receipt_format_config(value):
    if value is None:
        source = {}
    elif isinstance(value, str):
        try:
            source = json.loads(value)
        except ValueError:
            source = {}
    elif isinstance(value, dict):
        source = value
    else:
        source = {}

    default_elements = dict(DEFAULT_RECEIPT_FORMAT_CONFIG["elements"])
    incoming_elements = source.get("elements") if isinstance(source.get("elements"), dict) else {}

    env_shop_name = os.environ.get("RECEIPT_SHOP_NAME", "").strip()
    source_shop_name = str(source.get("shop_name") or "").strip()
    shop_name = env_shop_name or source_shop_name or DEFAULT_RECEIPT_SHOP_NAME

    normalized_elements = {}
    for key, default_value in default_elements.items():
        normalized_elements[key] = bool(incoming_elements.get(key, default_value))

    default_order = DEFAULT_RECEIPT_FORMAT_CONFIG.get("order") if isinstance(DEFAULT_RECEIPT_FORMAT_CONFIG.get("order"), dict) else {}
    incoming_order = source.get("order") if isinstance(source.get("order"), dict) else {}
    normalized_order = {}

    for group_key, default_group_order in default_order.items():
        incoming_group_order = incoming_order.get(group_key) if isinstance(incoming_order.get(group_key), list) else []
        valid_keys = [k for k in default_group_order if k in default_elements]
        ordered = []
        seen = set()

        for key in incoming_group_order:
            normalized_key = str(key or "").strip()
            if normalized_key in valid_keys and normalized_key not in seen:
                ordered.append(normalized_key)
                seen.add(normalized_key)

        for key in valid_keys:
            if key not in seen:
                ordered.append(key)
                seen.add(key)

        normalized_order[group_key] = ordered

    return {
        "version": 3,
        "shop_name": shop_name,
        "elements": normalized_elements,
        "order": normalized_order,
    }


def _next_customer_code(conn):
    day = datetime.now().strftime("%Y%m%d")
    prefix = f"CUS-{day}-"
    row = conn.execute(
        """
        SELECT customer_id
        FROM customers
        WHERE customer_id LIKE ?
        ORDER BY customer_id DESC
        LIMIT 1
        """,
        (f"{prefix}%",),
    ).fetchone()
    if not row or not row["customer_id"]:
        return f"{prefix}001"

    try:
        seq = int(str(row["customer_id"]).split("-")[-1]) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def _next_job_order_no(conn):
    day = datetime.now().strftime("%Y%m%d")
    prefix = f"JO-{day}-"
    row = conn.execute(
        """
        SELECT job_order_no
        FROM job_orders
        WHERE job_order_no LIKE ?
        ORDER BY job_order_no DESC
        LIMIT 1
        """,
        (f"{prefix}%",),
    ).fetchone()
    if not row or not row["job_order_no"]:
        return f"{prefix}001"

    try:
        seq = int(str(row["job_order_no"]).split("-")[-1]) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def get_connection():
    # Longer timeout + busy_timeout helps under brief write contention.
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _run_write_transaction(work_fn, max_attempts=4, sleep_seconds=0.2):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        conn = get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = work_fn(conn)
            conn.commit()
            return result
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass

            is_locked = isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower()
            if is_locked and attempt < max_attempts:
                last_error = exc
                time.sleep(sleep_seconds * attempt)
                continue
            raise
        finally:
            conn.close()

    if last_error is not None:
        raise last_error


def _ensure_column(conn, table_name, column_name, column_sql):
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _ensure_default_services(conn):
    timestamp = _now_str()
    defaults = [
        ("svc-extra-wash", "Extra Wash", 20, 1),
        ("svc-extra-dry", "Extra Dry", 20, 1),
    ]

    for service_id, name, unit_price, bonus_pulses in defaults:
        existing = conn.execute(
            "SELECT id FROM services WHERE lower(name) = lower(?)",
            (name,),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO services (id, name, unit_price, bonus_pulses, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (service_id, name, unit_price, bonus_pulses, timestamp, timestamp),
        )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Enable WAL once at initialization time.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS machines (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL,
            machine_function TEXT NOT NULL DEFAULT 'standard',
            esp32_ip    TEXT NOT NULL,
            pulse_on    INTEGER DEFAULT 50,
            pulse_off   INTEGER DEFAULT 50,
            pulse_count INTEGER DEFAULT 2,
            quick_wash_pulse_count INTEGER DEFAULT 1,
            vend_price  INTEGER DEFAULT 60,
            quick_wash_price INTEGER DEFAULT 60,
            status      TEXT DEFAULT 'IDLE'
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          TEXT PRIMARY KEY,
            machine_id  TEXT NOT NULL,
            amount      INTEGER NOT NULL,
            status      TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            synced      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS employees (
            id           TEXT PRIMARY KEY,
            display_name TEXT NOT NULL UNIQUE,
            pin_hash     TEXT NOT NULL,
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shift_sessions (
            id          TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            end_reason  TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS products (
            id                  TEXT PRIMARY KEY,
            name                TEXT NOT NULL UNIQUE,
            unit_price          INTEGER NOT NULL,
            unit_cost           INTEGER NOT NULL DEFAULT 0,
            stock_on_hand       INTEGER NOT NULL DEFAULT 0,
            boxes_on_hand       INTEGER NOT NULL DEFAULT 0,
            low_stock_threshold INTEGER NOT NULL DEFAULT 20,
            low_box_threshold   INTEGER NOT NULL DEFAULT 5,
            is_active           INTEGER NOT NULL DEFAULT 1,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS services (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            unit_price  INTEGER NOT NULL,
            bonus_pulses INTEGER NOT NULL DEFAULT 1,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transaction_items (
            id            TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            item_type     TEXT NOT NULL,
            item_id       TEXT NOT NULL,
            item_name     TEXT NOT NULL,
            unit_price    INTEGER NOT NULL,
            quantity      INTEGER NOT NULL,
            line_total    INTEGER NOT NULL,
            created_at    TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id)
        );

        CREATE TABLE IF NOT EXISTS stock_movements (
            id             TEXT PRIMARY KEY,
            product_id     TEXT NOT NULL,
            transaction_id TEXT,
            delta_qty      INTEGER NOT NULL,
            stock_after    INTEGER NOT NULL,
            reason         TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id)
        );

        CREATE TABLE IF NOT EXISTS manual_expenses (
            id          TEXT PRIMARY KEY,
            amount      INTEGER NOT NULL,
            note        TEXT,
            expense_at  TEXT NOT NULL,
            shift_id    TEXT,
            employee_id TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY(shift_id) REFERENCES shift_sessions(id),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS post_cycle_payment_logs (
            id          TEXT PRIMARY KEY,
            amount      INTEGER NOT NULL,
            logged_at   TEXT NOT NULL,
            shift_id    TEXT,
            employee_id TEXT,
            note        TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY(shift_id) REFERENCES shift_sessions(id),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS print_jobs (
            id           TEXT PRIMARY KEY,
            report_type  TEXT NOT NULL,
            reference_id TEXT NOT NULL,
            printed_at   TEXT NOT NULL,
            printed_by   TEXT,
            status       TEXT NOT NULL,
            created_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            id                TEXT PRIMARY KEY,
            customer_id       TEXT NOT NULL UNIQUE,
            name              TEXT NOT NULL,
            phone             TEXT,
            wash_order_count  INTEGER NOT NULL DEFAULT 0,
            dry_order_count   INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS job_orders (
            id                       TEXT PRIMARY KEY,
            job_order_no             TEXT NOT NULL UNIQUE,
            customer_id              TEXT NOT NULL,
            customer_name            TEXT NOT NULL,
            customer_phone           TEXT,
            machine_id               TEXT NOT NULL,
            machine_name             TEXT NOT NULL,
            machine_type             TEXT NOT NULL,
            wash_mode                TEXT NOT NULL DEFAULT 'normal',
            dry_mode                 TEXT NOT NULL DEFAULT 'normal',
            wash_qty                 INTEGER NOT NULL DEFAULT 0,
            dry_qty                  INTEGER NOT NULL DEFAULT 0,
            product_qty              INTEGER NOT NULL DEFAULT 0,
            service_qty              INTEGER NOT NULL DEFAULT 0,
            paid_by_gcash            INTEGER NOT NULL DEFAULT 0,
            wash_unit_price          INTEGER NOT NULL DEFAULT 0,
            dry_unit_price           INTEGER NOT NULL DEFAULT 0,
            total_amount             INTEGER NOT NULL DEFAULT 0,
            status                   TEXT NOT NULL DEFAULT 'OPEN',
            created_by_shift_id      TEXT,
            created_by_employee_id   TEXT,
            created_by_employee_name TEXT,
            created_at               TEXT NOT NULL,
            used_at                  TEXT,
            used_machine_id          TEXT,
            used_transaction_id      TEXT,
            updated_at               TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS receipt_overrides (
            reference_id  TEXT PRIMARY KEY,
            kind          TEXT NOT NULL,
            overrides_json TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_started_at ON transactions(started_at);
        CREATE INDEX IF NOT EXISTS idx_shift_sessions_location ON shift_sessions(location_id);
        CREATE INDEX IF NOT EXISTS idx_shift_sessions_employee ON shift_sessions(employee_id);
        CREATE INDEX IF NOT EXISTS idx_transaction_items_txn ON transaction_items(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_products_low_stock ON products(is_active, stock_on_hand, low_stock_threshold);
        CREATE INDEX IF NOT EXISTS idx_post_cycle_payment_logs_logged_at ON post_cycle_payment_logs(logged_at);
        CREATE INDEX IF NOT EXISTS idx_post_cycle_payment_logs_shift_id ON post_cycle_payment_logs(shift_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_one_active_per_location
            ON shift_sessions(location_id)
            WHERE ended_at IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_name_ci ON customers(lower(name));
        CREATE INDEX IF NOT EXISTS idx_job_orders_status_created ON job_orders(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_job_orders_customer_status ON job_orders(customer_id, status, created_at DESC);
    """)

    _ensure_column(conn, "transactions", "employee_id", "employee_id TEXT")
    _ensure_column(conn, "transactions", "shift_id", "shift_id TEXT")
    _ensure_column(conn, "transactions", "product_total", "product_total INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "transactions", "service_total", "service_total INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "transactions", "request_id", "request_id TEXT")
    _ensure_column(conn, "transactions", "customer_id", "customer_id TEXT")
    _ensure_column(conn, "transactions", "customer_name", "customer_name TEXT")
    _ensure_column(conn, "transactions", "customer_phone", "customer_phone TEXT")
    _ensure_column(conn, "transactions", "paid_by_gcash", "paid_by_gcash INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "transactions", "gcash_amount", "gcash_amount INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "transactions", "job_order_id", "job_order_id TEXT")
    _ensure_column(conn, "transactions", "job_order_no", "job_order_no TEXT")
    _ensure_column(conn, "job_orders", "created_by_shift_id", "created_by_shift_id TEXT")
    _ensure_column(conn, "job_orders", "wash_mode", "wash_mode TEXT NOT NULL DEFAULT 'normal'")
    _ensure_column(conn, "job_orders", "dry_mode", "dry_mode TEXT NOT NULL DEFAULT 'normal'")
    _ensure_column(conn, "job_orders", "product_qty", "product_qty INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "job_orders", "service_qty", "service_qty INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "job_orders", "paid_by_gcash", "paid_by_gcash INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "machines", "machine_function", "machine_function TEXT NOT NULL DEFAULT 'standard'")
    _ensure_column(conn, "machines", "quick_wash_pulse_count", "quick_wash_pulse_count INTEGER DEFAULT 1")
    _ensure_column(conn, "machines", "quick_wash_price", "quick_wash_price INTEGER DEFAULT 60")
    _ensure_column(conn, "machines", "run_started_at", "run_started_at TEXT")
    _ensure_column(conn, "machines", "run_ends_at", "run_ends_at TEXT")
    _ensure_column(conn, "products", "boxes_on_hand", "boxes_on_hand INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "products", "low_box_threshold", "low_box_threshold INTEGER NOT NULL DEFAULT 5")
    _ensure_column(conn, "services", "bonus_pulses", "bonus_pulses INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "transaction_items", "unit_cost", "unit_cost INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "transaction_items", "line_cost", "line_cost INTEGER NOT NULL DEFAULT 0")

    timestamp = _now_str()
    conn.execute(
        """
        INSERT OR IGNORE INTO app_settings (key, value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (DAY_CHANGE_TIME_SETTING_KEY, DEFAULT_DAY_CHANGE_TIME, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO app_settings (key, value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            RECEIPT_FORMAT_SETTING_KEY,
            json.dumps(DEFAULT_RECEIPT_FORMAT_CONFIG, separators=(",", ":"), sort_keys=True),
            timestamp,
            timestamp,
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO app_settings (key, value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            RECENT_SHIFT_SUMMARY_COUNT_SETTING_KEY,
            str(DEFAULT_RECENT_SHIFT_SUMMARY_COUNT),
            timestamp,
            timestamp,
        ),
    )

    _ensure_default_services(conn)
    _backfill_customers_from_transactions(conn)

    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_request_id ON transactions(request_id)")

    conn.commit()
    conn.close()


def get_day_change_time():
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
        (DAY_CHANGE_TIME_SETTING_KEY,),
    ).fetchone()
    conn.close()

    if row and row["value"]:
        try:
            return _normalize_day_change_time(row["value"])
        except ValueError:
            pass
    return DEFAULT_DAY_CHANGE_TIME


def set_day_change_time(day_change_time):
    normalized = _normalize_day_change_time(day_change_time)
    timestamp = _now_str()

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (DAY_CHANGE_TIME_SETTING_KEY, normalized, timestamp, timestamp),
    )
    conn.commit()
    conn.close()
    return normalized


def get_recent_shift_summary_count():
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
        (RECENT_SHIFT_SUMMARY_COUNT_SETTING_KEY,),
    ).fetchone()
    conn.close()

    if row and row["value"] is not None:
        try:
            return _normalize_recent_shift_summary_count(row["value"])
        except ValueError:
            pass
    return DEFAULT_RECENT_SHIFT_SUMMARY_COUNT


def set_recent_shift_summary_count(value):
    normalized = _normalize_recent_shift_summary_count(value)
    timestamp = _now_str()

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (RECENT_SHIFT_SUMMARY_COUNT_SETTING_KEY, str(normalized), timestamp, timestamp),
    )
    conn.commit()
    conn.close()
    return normalized


def get_receipt_format_config():
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
        (RECEIPT_FORMAT_SETTING_KEY,),
    ).fetchone()
    conn.close()

    if row and row["value"]:
        return _normalize_receipt_format_config(row["value"])
    return _normalize_receipt_format_config(DEFAULT_RECEIPT_FORMAT_CONFIG)


def set_receipt_format_config(config):
    normalized = _normalize_receipt_format_config(config)
    timestamp = _now_str()
    serialized = json.dumps(normalized, separators=(",", ":"), sort_keys=True)

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (RECEIPT_FORMAT_SETTING_KEY, serialized, timestamp, timestamp),
    )
    conn.commit()
    conn.close()
    return normalized


def _backfill_customers_from_transactions(conn):
    rows = conn.execute(
        """
        SELECT DISTINCT customer_id, customer_name, customer_phone
        FROM transactions
        WHERE customer_name IS NOT NULL AND trim(customer_name) <> ''
        """
    ).fetchall()
    timestamp = _now_str()

    for row in rows:
        name = str(row["customer_name"] or "").strip()
        if not name:
            continue

        try:
            phone = _normalize_phone(row["customer_phone"])
        except ValueError:
            phone = None

        existing = conn.execute(
            "SELECT id, customer_id, phone FROM customers WHERE lower(name) = lower(?) LIMIT 1",
            (name,),
        ).fetchone()
        if existing:
            if phone and phone != (existing["phone"] or None):
                conn.execute(
                    "UPDATE customers SET phone = ?, updated_at = ? WHERE id = ?",
                    (phone, timestamp, existing["id"]),
                )
            continue

        desired_customer_id = str(row["customer_id"] or "").strip() or _next_customer_code(conn)
        conflict = conn.execute(
            "SELECT id FROM customers WHERE customer_id = ? LIMIT 1",
            (desired_customer_id,),
        ).fetchone()
        if conflict:
            desired_customer_id = _next_customer_code(conn)

        conn.execute(
            """
            INSERT INTO customers (
                id, customer_id, name, phone,
                wash_order_count, dry_order_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                desired_customer_id,
                name,
                phone,
                timestamp,
                timestamp,
            ),
        )


def list_customers(limit=500):
    lim = max(1, min(int(limit or 500), 5000))
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
        FROM customers
        ORDER BY name ASC
        LIMIT ?
        """,
        (lim,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer_by_name(name):
    normalized = str(name or "").strip()
    if not normalized:
        return None

    conn = get_connection()
    row = conn.execute(
        """
        SELECT customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
        FROM customers
        WHERE lower(name) = lower(?)
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_customer_by_customer_id(customer_id):
    normalized = str(customer_id or "").strip()
    if not normalized:
        return None

    conn = get_connection()
    row = conn.execute(
        """
        SELECT customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
        FROM customers
        WHERE customer_id = ?
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_customer(name, phone=None):
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("customer name is required")

    normalized_phone = _normalize_phone(phone)
    timestamp = _now_str()
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        existing = conn.execute(
            """
            SELECT id, customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
            FROM customers
            WHERE lower(name) = lower(?)
            LIMIT 1
            """,
            (normalized_name,),
        ).fetchone()

        if existing:
            updates = []
            values = []
            if normalized_phone and normalized_phone != (existing["phone"] or None):
                updates.append("phone = ?")
                values.append(normalized_phone)
            if normalized_name != (existing["name"] or ""):
                updates.append("name = ?")
                values.append(normalized_name)

            if updates:
                updates.append("updated_at = ?")
                values.append(timestamp)
                values.append(existing["id"])
                conn.execute(
                    f"UPDATE customers SET {', '.join(updates)} WHERE id = ?",
                    values,
                )

            row = conn.execute(
                """
                SELECT customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
                FROM customers
                WHERE id = ?
                LIMIT 1
                """,
                (existing["id"],),
            ).fetchone()
            conn.commit()
            return dict(row)

        customer_id = _next_customer_code(conn)
        row_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO customers (
                id, customer_id, name, phone,
                wash_order_count, dry_order_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (row_id, customer_id, normalized_name, normalized_phone, timestamp, timestamp),
        )
        row = conn.execute(
            """
            SELECT customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
            FROM customers
            WHERE id = ?
            LIMIT 1
            """,
            (row_id,),
        ).fetchone()
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def increment_customer_order_count(customer_id, machine_type, quantity=1):
    normalized_customer_id = str(customer_id or "").strip()
    normalized_machine_type = str(machine_type or "").strip().lower()
    qty = max(0, int(quantity or 0))

    if not normalized_customer_id or qty <= 0:
        return None
    if normalized_machine_type not in ("washer", "dryer"):
        return None

    target_column = "wash_order_count" if normalized_machine_type == "washer" else "dry_order_count"
    conn = get_connection()
    conn.execute(
        f"UPDATE customers SET {target_column} = {target_column} + ?, updated_at = ? WHERE customer_id = ?",
        (qty, _now_str(), normalized_customer_id),
    )
    row = conn.execute(
        """
        SELECT customer_id, name, phone, wash_order_count, dry_order_count, created_at, updated_at
        FROM customers
        WHERE customer_id = ?
        LIMIT 1
        """,
        (normalized_customer_id,),
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def create_job_order(
    customer_id,
    customer_name,
    customer_phone,
    machine_id,
    machine_name,
    machine_type,
    wash_qty,
    dry_qty,
    wash_unit_price,
    dry_unit_price,
    product_qty=0,
    service_qty=0,
    product_amount=0,
    service_amount=0,
    paid_by_gcash=False,
    wash_mode="normal",
    dry_mode="normal",
    created_by_shift_id=None,
    created_by_employee_id=None,
    created_by_employee_name=None,
):
    def _normalize_mode(mode_value):
        normalized = str(mode_value or "normal").strip().lower()
        if normalized not in ("normal", "quick"):
            raise ValueError("wash_mode and dry_mode must be 'normal' or 'quick'")
        return normalized

    normalized_machine_type = str(machine_type or "").strip().lower()
    if normalized_machine_type not in ("washer", "dryer", "mixed"):
        raise ValueError("machine_type must be washer, dryer, or mixed")
    normalized_wash_mode = _normalize_mode(wash_mode)
    normalized_dry_mode = _normalize_mode(dry_mode)

    wash_count = int(wash_qty or 0)
    dry_count = int(dry_qty or 0)
    product_count = int(product_qty or 0)
    service_count = int(service_qty or 0)
    paid_by_gcash_value = 1 if bool(paid_by_gcash) else 0
    if wash_count < 0 or dry_count < 0:
        raise ValueError("wash_qty and dry_qty cannot be negative")
    if product_count < 0:
        raise ValueError("product_qty cannot be negative")
    if service_count < 0:
        raise ValueError("service_qty cannot be negative")
    if wash_count == 0 and dry_count == 0:
        raise ValueError("At least one of wash_qty or dry_qty must be greater than zero")

    wash_price = max(0, int(wash_unit_price or 0))
    dry_price = max(0, int(dry_unit_price or 0))
    product_total = max(0, int(product_amount or 0))
    service_total = max(0, int(service_amount or 0))
    total_amount = (wash_count * wash_price) + (dry_count * dry_price) + product_total + service_total

    timestamp = _now_str()

    def _work(conn):
        order_id = str(uuid.uuid4())
        order_no = _next_job_order_no(conn)
        conn.execute(
            """
            INSERT INTO job_orders (
                id, job_order_no,
                customer_id, customer_name, customer_phone,
                machine_id, machine_name, machine_type,
                wash_mode, dry_mode,
                wash_qty, dry_qty, product_qty, service_qty,
                paid_by_gcash,
                wash_unit_price, dry_unit_price, total_amount,
                status,
                created_by_shift_id,
                created_by_employee_id, created_by_employee_name,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                order_no,
                str(customer_id or "").strip(),
                str(customer_name or "").strip(),
                (str(customer_phone or "").strip() or None),
                str(machine_id or "").strip(),
                str(machine_name or "").strip(),
                normalized_machine_type,
                normalized_wash_mode,
                normalized_dry_mode,
                wash_count,
                dry_count,
                product_count,
                service_count,
                paid_by_gcash_value,
                wash_price,
                dry_price,
                total_amount,
                (str(created_by_shift_id or "").strip() or None),
                (str(created_by_employee_id or "").strip() or None),
                (str(created_by_employee_name or "").strip() or None),
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            "SELECT * FROM job_orders WHERE id = ? LIMIT 1",
            (order_id,),
        ).fetchone()
        return dict(row)

    return _run_write_transaction(_work)


def create_job_orders_bulk(
    customer_id,
    customer_name,
    customer_phone,
    machine_orders,
    created_by_shift_id=None,
    created_by_employee_id=None,
    created_by_employee_name=None,
):
    normalized_orders = machine_orders if isinstance(machine_orders, list) else []
    if not normalized_orders:
        raise ValueError("machine_orders is required")

    timestamp = _now_str()

    def _work(conn):
        created = []
        for order in normalized_orders:
            machine_id = str(order.get("machine_id") or "").strip()
            machine_name = str(order.get("machine_name") or machine_id).strip()
            machine_type = str(order.get("machine_type") or "").strip().lower()
            if machine_type not in ("washer", "dryer"):
                raise ValueError("machine_type must be washer or dryer")
            wash_mode = str(order.get("wash_mode") or "normal").strip().lower()
            dry_mode = str(order.get("dry_mode") or "normal").strip().lower()
            if wash_mode not in ("normal", "quick") or dry_mode not in ("normal", "quick"):
                raise ValueError("wash_mode and dry_mode must be 'normal' or 'quick'")

            wash_qty = int(order.get("wash_qty") or 0)
            dry_qty = int(order.get("dry_qty") or 0)
            product_qty = int(order.get("product_qty") or 0)
            service_qty = int(order.get("service_qty") or 0)
            product_amount = max(0, int(order.get("product_amount") or 0))
            service_amount = max(0, int(order.get("service_amount") or 0))
            paid_by_gcash_value = 1 if bool(order.get("paid_by_gcash")) else 0
            if wash_qty < 0 or dry_qty < 0:
                raise ValueError("wash_qty and dry_qty cannot be negative")
            if product_qty < 0:
                raise ValueError("product_qty cannot be negative")
            if service_qty < 0:
                raise ValueError("service_qty cannot be negative")
            if wash_qty == 0 and dry_qty == 0:
                raise ValueError("At least one of wash_qty or dry_qty must be greater than zero")

            wash_unit_price = max(0, int(order.get("wash_unit_price") or 0))
            dry_unit_price = max(0, int(order.get("dry_unit_price") or 0))
            total_amount = (wash_qty * wash_unit_price) + (dry_qty * dry_unit_price) + product_amount + service_amount

            order_id = str(uuid.uuid4())
            order_no = _next_job_order_no(conn)
            conn.execute(
                """
                INSERT INTO job_orders (
                    id, job_order_no,
                    customer_id, customer_name, customer_phone,
                    machine_id, machine_name, machine_type,
                    wash_mode, dry_mode,
                    wash_qty, dry_qty, product_qty, service_qty,
                    paid_by_gcash,
                    wash_unit_price, dry_unit_price, total_amount,
                    status,
                    created_by_shift_id,
                    created_by_employee_id, created_by_employee_name,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    order_no,
                    str(customer_id or "").strip(),
                    str(customer_name or "").strip(),
                    (str(customer_phone or "").strip() or None),
                    machine_id,
                    machine_name,
                    machine_type,
                    wash_mode,
                    dry_mode,
                    wash_qty,
                    dry_qty,
                    product_qty,
                    service_qty,
                    paid_by_gcash_value,
                    wash_unit_price,
                    dry_unit_price,
                    total_amount,
                    (str(created_by_shift_id or "").strip() or None),
                    (str(created_by_employee_id or "").strip() or None),
                    (str(created_by_employee_name or "").strip() or None),
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM job_orders WHERE id = ? LIMIT 1",
                (order_id,),
            ).fetchone()
            created.append(dict(row))
        return created

    return _run_write_transaction(_work)


def list_open_job_orders(customer_id=None, machine_id=None, machine_type=None, limit=100):
    lim = max(1, min(int(limit or 100), 500))
    where_parts = ["status = 'OPEN'"]
    params = []

    normalized_customer_id = str(customer_id or "").strip()
    if normalized_customer_id:
        where_parts.append("customer_id = ?")
        params.append(normalized_customer_id)

    normalized_machine_id = str(machine_id or "").strip()
    if normalized_machine_id:
        where_parts.append("machine_id = ?")
        params.append(normalized_machine_id)

    normalized_machine_type = str(machine_type or "").strip().lower()
    if normalized_machine_type in ("washer", "dryer"):
        where_parts.append("machine_type = ?")
        params.append(normalized_machine_type)

    where_sql = " AND ".join(where_parts)

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT *
        FROM job_orders
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [*params, lim],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_order(job_order_id):
    normalized = str(job_order_id or "").strip()
    if not normalized:
        return None

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM job_orders WHERE id = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_job_order(job_order_id):
    normalized = str(job_order_id or "").strip()
    if not normalized:
        return False

    conn = get_connection()
    cursor = conn.execute(
        """
        DELETE FROM job_orders
        WHERE id = ? AND status = 'OPEN'
        """,
        (normalized,),
    )
    conn.commit()
    deleted = int(cursor.rowcount or 0) == 1
    conn.close()
    return deleted


def claim_job_order_for_activation(job_order_id, machine_id, machine_type, customer_id=None):
    normalized_order_id = str(job_order_id or "").strip()
    normalized_machine_id = str(machine_id or "").strip()
    normalized_machine_type = str(machine_type or "").strip().lower()
    normalized_customer_id = str(customer_id or "").strip() if customer_id else None

    if not normalized_order_id:
        raise ValueError("job_order_id is required")
    if normalized_machine_type not in ("washer", "dryer"):
        raise ValueError("invalid machine type for activation")

    conn = get_connection()
    try:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM job_orders WHERE id = ? LIMIT 1",
            (normalized_order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Job order not found")

        order = dict(row)
        if str(order.get("status") or "").upper() != "OPEN":
            raise ValueError("Job order is already used or closed")
        order_machine_id = str(order.get("machine_id") or "").strip().lower()
        is_type_scoped_order = order_machine_id in ("any-washer", "any-dryer", "any-mixed")
        if not is_type_scoped_order and str(order.get("machine_id") or "") != normalized_machine_id:
            raise ValueError("Job order does not match selected machine")
        order_machine_type = str(order.get("machine_type") or "").strip().lower()
        if order_machine_type not in ("mixed", normalized_machine_type):
            raise ValueError("Job order does not match selected machine type")
        if normalized_customer_id and str(order.get("customer_id") or "") != normalized_customer_id:
            raise ValueError("Job order does not belong to selected customer")

        wash_qty = int(order.get("wash_qty") or 0)
        dry_qty = int(order.get("dry_qty") or 0)

        if normalized_machine_type == "washer" and wash_qty < 1:
            raise ValueError("Job order does not include wash quantity for this machine")
        if normalized_machine_type == "dryer" and dry_qty < 1:
            raise ValueError("Job order does not include dry quantity for this machine")

        new_wash_qty = wash_qty - (1 if normalized_machine_type == "washer" else 0)
        new_dry_qty = dry_qty - (1 if normalized_machine_type == "dryer" else 0)
        is_completed = new_wash_qty <= 0 and new_dry_qty <= 0
        new_status = "USED" if is_completed else "OPEN"

        timestamp = _now_str()
        used_at_value = timestamp if is_completed else None
        conn.execute(
            """
            UPDATE job_orders
            SET wash_qty = ?,
                dry_qty = ?,
                status = ?,
                used_at = CASE WHEN ? IS NULL THEN used_at ELSE ? END,
                used_machine_id = ?,
                updated_at = ?
            WHERE id = ? AND status = 'OPEN'
            """,
            (
                max(0, new_wash_qty),
                max(0, new_dry_qty),
                new_status,
                used_at_value,
                used_at_value,
                normalized_machine_id,
                timestamp,
                normalized_order_id,
            ),
        )

        claimed = conn.execute(
            "SELECT * FROM job_orders WHERE id = ? LIMIT 1",
            (normalized_order_id,),
        ).fetchone()
        conn.commit()
        return dict(claimed)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def attach_job_order_transaction(job_order_id, transaction_id):
    normalized_order_id = str(job_order_id or "").strip()
    normalized_txn_id = str(transaction_id or "").strip()
    if not normalized_order_id or not normalized_txn_id:
        return False

    conn = get_connection()
    cursor = conn.execute(
        """
        UPDATE job_orders
        SET used_transaction_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (normalized_txn_id, _now_str(), normalized_order_id),
    )
    conn.commit()
    updated = int(cursor.rowcount or 0) == 1
    conn.close()
    return updated


def revert_job_order_usage(job_order_id, machine_type):
    normalized_order_id = str(job_order_id or "").strip()
    normalized_machine_type = str(machine_type or "").strip().lower()
    if not normalized_order_id or normalized_machine_type not in ("washer", "dryer"):
        return False

    conn = get_connection()
    try:
        conn.execute("BEGIN")
        row = conn.execute("SELECT * FROM job_orders WHERE id = ? LIMIT 1", (normalized_order_id,)).fetchone()
        if not row:
            conn.rollback()
            return False

        wash_add = 1 if normalized_machine_type == "washer" else 0
        dry_add = 1 if normalized_machine_type == "dryer" else 0

        conn.execute(
            """
            UPDATE job_orders
            SET wash_qty = wash_qty + ?,
                dry_qty = dry_qty + ?,
                status = 'OPEN',
                used_at = NULL,
                used_transaction_id = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (wash_add, dry_add, _now_str(), normalized_order_id)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_machine(
    machine_id,
    name,
    machine_type,
    machine_function,
    esp32_ip,
    pulse_on,
    pulse_off,
    pulse_count,
    vend_price,
    quick_wash_pulse_count=1,
    quick_wash_price=None,
):
    quick_wash_price_value = int(vend_price if quick_wash_price is None else quick_wash_price)
    conn = get_connection()
    conn.execute(
        """INSERT INTO machines (
               id, name, type, machine_function, esp32_ip,
               pulse_on, pulse_off, pulse_count,
               quick_wash_pulse_count, vend_price, quick_wash_price
           )
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               name=excluded.name,
               type=excluded.type,
               machine_function=excluded.machine_function,
               esp32_ip=excluded.esp32_ip,
               pulse_on=excluded.pulse_on,
               pulse_off=excluded.pulse_off,
               pulse_count=excluded.pulse_count,
               quick_wash_pulse_count=excluded.quick_wash_pulse_count,
               vend_price=excluded.vend_price,
               quick_wash_price=excluded.quick_wash_price""",
        (
            machine_id,
            name,
            machine_type,
            machine_function,
            esp32_ip,
            pulse_on,
            pulse_off,
            pulse_count,
            int(quick_wash_pulse_count),
            vend_price,
            quick_wash_price_value,
        ),
    )
    conn.commit()
    conn.close()


def create_machine(
    machine_id,
    name,
    machine_type,
    esp32_ip,
    machine_function="standard",
    pulse_on=50,
    pulse_off=50,
    pulse_count=2,
    vend_price=60,
    quick_wash_pulse_count=1,
    quick_wash_price=None,
):
    quick_wash_price_value = int(vend_price if quick_wash_price is None else quick_wash_price)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO machines (
            id, name, type, machine_function, esp32_ip,
            pulse_on, pulse_off, pulse_count,
            quick_wash_pulse_count, vend_price, quick_wash_price,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'IDLE')
        """,
        (
            machine_id,
            name,
            machine_type,
            str(machine_function or "standard").strip() or "standard",
            esp32_ip,
            int(pulse_on),
            int(pulse_off),
            int(pulse_count),
            int(quick_wash_pulse_count),
            int(vend_price),
            quick_wash_price_value,
        ),
    )
    conn.commit()
    conn.close()


def update_machine(
    machine_id,
    name=None,
    machine_type=None,
    machine_function=None,
    esp32_ip=None,
    pulse_on=None,
    pulse_off=None,
    pulse_count=None,
    vend_price=None,
    quick_wash_pulse_count=None,
    quick_wash_price=None,
):
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if machine_type is not None:
        updates.append("type = ?")
        values.append(machine_type)
    if machine_function is not None:
        updates.append("machine_function = ?")
        values.append(str(machine_function).strip() or "standard")
    if esp32_ip is not None:
        updates.append("esp32_ip = ?")
        values.append(esp32_ip)
    if pulse_on is not None:
        updates.append("pulse_on = ?")
        values.append(int(pulse_on))
    if pulse_off is not None:
        updates.append("pulse_off = ?")
        values.append(int(pulse_off))
    if pulse_count is not None:
        updates.append("pulse_count = ?")
        values.append(int(pulse_count))
    if vend_price is not None:
        updates.append("vend_price = ?")
        values.append(int(vend_price))
    if quick_wash_pulse_count is not None:
        updates.append("quick_wash_pulse_count = ?")
        values.append(int(quick_wash_pulse_count))
    if quick_wash_price is not None:
        updates.append("quick_wash_price = ?")
        values.append(int(quick_wash_price))

    if not updates:
        return False

    values.append(machine_id)
    conn = get_connection()
    cursor = conn.execute(
        f"UPDATE machines SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def update_machine_vend_price_bulk(vend_price, machine_type="all"):
    normalized_type = str(machine_type or "all").strip().lower()
    if normalized_type not in ("all", "washer", "dryer"):
        raise ValueError("machine_type must be all, washer, or dryer")

    conn = get_connection()
    if normalized_type == "all":
        cursor = conn.execute(
            "UPDATE machines SET vend_price = ?",
            (int(vend_price),),
        )
    else:
        cursor = conn.execute(
            "UPDATE machines SET vend_price = ? WHERE type = ?",
            (int(vend_price), normalized_type),
        )
    conn.commit()
    updated = int(cursor.rowcount or 0)
    conn.close()
    return updated


def update_machine_settings_bulk(
    machine_ids,
    vend_price=None,
    pulse_count=None,
    quick_wash_price=None,
    quick_wash_pulse_count=None,
):
    normalized_ids = [str(machine_id).strip() for machine_id in (machine_ids or []) if str(machine_id).strip()]
    if not normalized_ids:
        return 0

    updates = []
    values = []

    if vend_price is not None:
        updates.append("vend_price = ?")
        values.append(int(vend_price))
    if pulse_count is not None:
        updates.append("pulse_count = ?")
        values.append(int(pulse_count))
    if quick_wash_price is not None:
        updates.append("quick_wash_price = ?")
        values.append(int(quick_wash_price))
    if quick_wash_pulse_count is not None:
        updates.append("quick_wash_pulse_count = ?")
        values.append(int(quick_wash_pulse_count))

    if not updates:
        return 0

    placeholders = ",".join(["?"] * len(normalized_ids))
    values.extend(normalized_ids)

    conn = get_connection()
    cursor = conn.execute(
        f"UPDATE machines SET {', '.join(updates)} WHERE id IN ({placeholders})",
        values,
    )
    conn.commit()
    updated = int(cursor.rowcount or 0)
    conn.close()
    return updated


def delete_machine(machine_id):
    conn = get_connection()
    cursor = conn.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_all_machines():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM machines").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_machine(machine_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_machine_status(machine_id, status):
    conn = get_connection()
    conn.execute("UPDATE machines SET status = ? WHERE id = ?", (status, machine_id))
    conn.commit()
    conn.close()


def set_machine_run_window(machine_id, started_at, ends_at):
    conn = get_connection()
    conn.execute(
        "UPDATE machines SET status = 'BUSY', run_started_at = ?, run_ends_at = ? WHERE id = ?",
        (started_at, ends_at, machine_id),
    )
    conn.commit()
    conn.close()


def clear_machine_run_window(machine_id):
    conn = get_connection()
    conn.execute(
        "UPDATE machines SET status = 'IDLE', run_started_at = NULL, run_ends_at = NULL WHERE id = ?",
        (machine_id,),
    )
    conn.commit()
    conn.close()


def insert_transaction(
    txn_id,
    machine_id,
    amount,
    status,
    started_at,
    employee_id=None,
    shift_id=None,
    product_total=0,
    service_total=0,
):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO transactions (
            id, machine_id, amount, status, started_at,
            employee_id, shift_id, product_total, service_total
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            txn_id,
            machine_id,
            amount,
            status,
            started_at,
            employee_id,
            shift_id,
            int(product_total or 0),
            int(service_total or 0),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_transactions(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unsynced_transactions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM transactions WHERE synced = 0").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_transactions_synced(txn_ids):
    if not txn_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" for _ in txn_ids)
    conn.execute(f"UPDATE transactions SET synced = 1 WHERE id IN ({placeholders})", txn_ids)
    conn.commit()
    conn.close()


def delete_transactions(txn_ids):
    tx_ids = [str(txn_id).strip() for txn_id in (txn_ids or []) if str(txn_id or "").strip()]
    if not tx_ids:
        return {
            "deleted_count": 0,
            "restocked_quantity": 0,
        }

    # Preserve order while removing duplicates.
    unique_ids = list(dict.fromkeys(tx_ids))

    conn = get_connection()
    try:
        conn.execute("BEGIN")

        placeholders = ",".join("?" for _ in unique_ids)
        existing_rows = conn.execute(
            f"SELECT id FROM transactions WHERE id IN ({placeholders})",
            unique_ids,
        ).fetchall()
        existing_ids = [row["id"] for row in existing_rows]
        if not existing_ids:
            conn.rollback()
            return {
                "deleted_count": 0,
                "restocked_quantity": 0,
            }

        existing_placeholders = ",".join("?" for _ in existing_ids)
        product_rows = conn.execute(
            f"""
            SELECT item_id, quantity
            FROM transaction_items
            WHERE transaction_id IN ({existing_placeholders}) AND item_type = 'product'
            """,
            existing_ids,
        ).fetchall()

        restock_by_product = {}
        for row in product_rows:
            pid = str(row["item_id"])
            qty = int(row["quantity"] or 0)
            if qty <= 0:
                continue
            restock_by_product[pid] = restock_by_product.get(pid, 0) + qty

        restocked_quantity = 0
        for product_id, qty in restock_by_product.items():
            row = conn.execute(
                "SELECT stock_on_hand FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
            if not row:
                continue

            new_stock = int(row["stock_on_hand"] or 0) + int(qty)
            conn.execute(
                "UPDATE products SET stock_on_hand = ?, updated_at = ? WHERE id = ?",
                (new_stock, _now_str(), product_id),
            )
            conn.execute(
                """
                INSERT INTO stock_movements (id, product_id, transaction_id, delta_qty, stock_after, reason, created_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), product_id, int(qty), new_stock, "transaction_deleted", _now_str()),
            )
            restocked_quantity += int(qty)

        conn.execute(
            f"DELETE FROM transaction_items WHERE transaction_id IN ({existing_placeholders})",
            existing_ids,
        )
        conn.execute(
            f"DELETE FROM stock_movements WHERE transaction_id IN ({existing_placeholders})",
            existing_ids,
        )
        deleted_cursor = conn.execute(
            f"DELETE FROM transactions WHERE id IN ({existing_placeholders})",
            existing_ids,
        )

        conn.commit()
        return {
            "deleted_count": int(deleted_cursor.rowcount or 0),
            "restocked_quantity": restocked_quantity,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_employee(display_name, pin):
    employee_id = str(uuid.uuid4())
    timestamp = _now_str()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO employees (id, display_name, pin_hash, is_active, created_at, updated_at)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (employee_id, display_name.strip(), _hash_pin(pin), timestamp, timestamp),
    )
    conn.commit()
    conn.close()
    return employee_id


def list_employees(active_only=False):
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            "SELECT id, display_name, is_active, created_at, updated_at FROM employees WHERE is_active = 1 ORDER BY display_name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, display_name, is_active, created_at, updated_at FROM employees ORDER BY display_name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_employee(employee_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, display_name, is_active, created_at, updated_at FROM employees WHERE id = ?",
        (employee_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def verify_employee_pin(employee_id, pin):
    conn = get_connection()
    row = conn.execute(
        "SELECT pin_hash, is_active FROM employees WHERE id = ?",
        (employee_id,),
    ).fetchone()
    conn.close()

    if not row or int(row["is_active"] or 0) != 1:
        return False
    return row["pin_hash"] == _hash_pin(pin)


def rotate_employee_pin(employee_id, new_pin):
    conn = get_connection()
    conn.execute(
        "UPDATE employees SET pin_hash = ?, updated_at = ? WHERE id = ?",
        (_hash_pin(new_pin), _now_str(), employee_id),
    )
    conn.commit()
    conn.close()


def deactivate_employee(employee_id):
    conn = get_connection()
    conn.execute(
        "UPDATE employees SET is_active = 0, updated_at = ? WHERE id = ?",
        (_now_str(), employee_id),
    )
    conn.commit()
    conn.close()


def get_active_shift(location_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT s.id, s.employee_id, s.location_id, s.started_at, s.ended_at, s.end_reason,
               e.display_name
        FROM shift_sessions s
        JOIN employees e ON e.id = s.employee_id
        WHERE s.location_id = ? AND s.ended_at IS NULL
        ORDER BY s.started_at DESC
        LIMIT 1
        """,
        (location_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_shift(shift_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT s.id, s.employee_id, s.location_id, s.started_at, s.ended_at, s.end_reason,
               e.display_name
        FROM shift_sessions s
        JOIN employees e ON e.id = s.employee_id
        WHERE s.id = ?
        LIMIT 1
        """,
        (shift_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_recent_shifts(location_id, limit=20, include_active=False):
    lim = max(1, min(int(limit or 20), 200))
    conn = get_connection()

    if include_active:
        rows = conn.execute(
            """
            SELECT s.id, s.employee_id, s.location_id, s.started_at, s.ended_at, s.end_reason,
                   e.display_name
            FROM shift_sessions s
            JOIN employees e ON e.id = s.employee_id
            WHERE s.location_id = ?
            ORDER BY s.started_at DESC
            LIMIT ?
            """,
            (location_id, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT s.id, s.employee_id, s.location_id, s.started_at, s.ended_at, s.end_reason,
                   e.display_name
            FROM shift_sessions s
            JOIN employees e ON e.id = s.employee_id
            WHERE s.location_id = ? AND s.ended_at IS NOT NULL
            ORDER BY s.started_at DESC
            LIMIT ?
            """,
            (location_id, lim),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def query_shift_history(location_id, page=1, per_page=20, include_active=False, search_term=""):
    page_num = max(1, int(page or 1))
    page_size = max(1, min(int(per_page or 20), 100))
    offset = (page_num - 1) * page_size

    conn = get_connection()

    where_parts = ["s.location_id = ?"]
    params = [location_id]

    if not include_active:
        where_parts.append("s.ended_at IS NOT NULL")

    q = str(search_term or "").strip().lower()
    if q:
        where_parts.append(
            """
            (
                lower(e.display_name) LIKE ? OR
                lower(s.id) LIKE ? OR
                lower(COALESCE(s.started_at, '')) LIKE ? OR
                lower(COALESCE(s.ended_at, '')) LIKE ?
            )
            """
        )
        q_like = f"%{q}%"
        params.extend([q_like, q_like, q_like, q_like])

    where_sql = " AND ".join(where_parts)

    total_row = conn.execute(
        f"""
        SELECT COUNT(1) AS total
        FROM shift_sessions s
        JOIN employees e ON e.id = s.employee_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()
    total = int(total_row["total"] or 0) if total_row else 0

    rows = conn.execute(
        f"""
        SELECT s.id, s.employee_id, s.location_id, s.started_at, s.ended_at, s.end_reason,
               e.display_name
        FROM shift_sessions s
        JOIN employees e ON e.id = s.employee_id
        WHERE {where_sql}
        ORDER BY s.started_at DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()

    conn.close()
    return {
        "shifts": [dict(r) for r in rows],
        "page": page_num,
        "per_page": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


def start_shift(employee_id, location_id):
    shift_id = str(uuid.uuid4())
    timestamp = _now_str()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO shift_sessions (id, employee_id, location_id, started_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (shift_id, employee_id, location_id, timestamp, timestamp),
    )
    conn.commit()
    conn.close()
    return shift_id


def end_shift(shift_id, reason="logout"):
    conn = get_connection()
    conn.execute(
        "UPDATE shift_sessions SET ended_at = ?, end_reason = ? WHERE id = ? AND ended_at IS NULL",
        (_now_str(), reason, shift_id),
    )
    conn.commit()
    conn.close()


def end_active_shift(location_id, reason="handover"):
    active = get_active_shift(location_id)
    if not active:
        return None
    end_shift(active["id"], reason=reason)
    return active["id"]


def list_products(active_only=True):
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            """
            SELECT id, name, unit_price, unit_cost, stock_on_hand, boxes_on_hand, low_stock_threshold, low_box_threshold, is_active,
                   created_at, updated_at
            FROM products
            WHERE is_active = 1
            ORDER BY name
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, name, unit_price, unit_cost, stock_on_hand, boxes_on_hand, low_stock_threshold, low_box_threshold, is_active,
                   created_at, updated_at
            FROM products
            ORDER BY name
            """
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_product(name, unit_price, unit_cost=0, stock_on_hand=0, boxes_on_hand=0, low_stock_threshold=20, low_box_threshold=5):
    product_id = str(uuid.uuid4())
    timestamp = _now_str()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO products (
            id, name, unit_price, unit_cost, stock_on_hand, boxes_on_hand, low_stock_threshold, low_box_threshold,
            is_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            product_id,
            name.strip(),
            int(unit_price),
            int(unit_cost),
            int(stock_on_hand),
            int(boxes_on_hand),
            int(low_stock_threshold),
            int(low_box_threshold),
            timestamp,
            timestamp,
        ),
    )
    conn.commit()
    conn.close()
    return product_id


def update_product(
    product_id,
    name=None,
    unit_price=None,
    unit_cost=None,
    stock_on_hand=None,
    boxes_on_hand=None,
    low_stock_threshold=None,
    low_box_threshold=None,
):
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        conn.close()
        return False

    conn.execute(
        """
        UPDATE products
        SET name = ?, unit_price = ?, unit_cost = ?, stock_on_hand = ?, boxes_on_hand = ?, low_stock_threshold = ?, low_box_threshold = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            (name.strip() if name is not None else row["name"]),
            int(unit_price) if unit_price is not None else int(row["unit_price"]),
            int(unit_cost) if unit_cost is not None else int(row["unit_cost"]),
            int(stock_on_hand) if stock_on_hand is not None else int(row["stock_on_hand"]),
            int(boxes_on_hand) if boxes_on_hand is not None else int(row["boxes_on_hand"]),
            int(low_stock_threshold) if low_stock_threshold is not None else int(row["low_stock_threshold"]),
            int(low_box_threshold) if low_box_threshold is not None else int(row["low_box_threshold"]),
            _now_str(),
            product_id,
        ),
    )
    conn.commit()
    conn.close()
    return True


def adjust_product_stock(product_id, quantity, reason="manual_restock"):
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id, name, stock_on_hand, boxes_on_hand, is_active FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not row or int(row["is_active"] or 0) != 1:
            conn.rollback()
            conn.close()
            return None

        delta_qty = int(quantity)
        new_stock = int(row["stock_on_hand"] or 0) + delta_qty
        new_boxes = int(row["boxes_on_hand"] or 0) - 1
        timestamp = _now_str()

        conn.execute(
            "UPDATE products SET stock_on_hand = ?, boxes_on_hand = ?, updated_at = ? WHERE id = ?",
            (new_stock, new_boxes, timestamp, product_id),
        )
        conn.execute(
            """
            INSERT INTO stock_movements (id, product_id, transaction_id, delta_qty, stock_after, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), product_id, None, delta_qty, new_stock, reason, timestamp),
        )

        conn.commit()
        return {
            "product_id": product_id,
            "product_name": row["name"],
            "delta_qty": delta_qty,
            "stock_after": new_stock,
            "boxes_after": new_boxes,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def adjust_product_boxes(product_id, quantity):
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id, name, boxes_on_hand, is_active FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not row or int(row["is_active"] or 0) != 1:
            conn.rollback()
            conn.close()
            return None

        delta_boxes = int(quantity)
        new_boxes = int(row["boxes_on_hand"] or 0) + delta_boxes
        timestamp = _now_str()

        conn.execute(
            "UPDATE products SET boxes_on_hand = ?, updated_at = ? WHERE id = ?",
            (new_boxes, timestamp, product_id),
        )

        conn.commit()
        return {
            "product_id": product_id,
            "product_name": row["name"],
            "delta_boxes": delta_boxes,
            "boxes_after": new_boxes,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def deactivate_product(product_id):
    conn = get_connection()
    conn.execute(
        "UPDATE products SET is_active = 0, updated_at = ? WHERE id = ?",
        (_now_str(), product_id),
    )
    conn.commit()
    conn.close()


def list_services(active_only=True):
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            """
            SELECT id, name, unit_price, bonus_pulses, is_active, created_at, updated_at
            FROM services
            WHERE is_active = 1
            ORDER BY name
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, name, unit_price, bonus_pulses, is_active, created_at, updated_at
            FROM services
            ORDER BY name
            """
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_services_by_ids(service_ids):
    ids = [str(sid).strip() for sid in (service_ids or []) if str(sid or "").strip()]
    if not ids:
        return {}

    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, name, unit_price, bonus_pulses, is_active FROM services WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    conn.close()
    return {row["id"]: dict(row) for row in rows}


def get_active_service_by_name(name):
    service_name = str(name or "").strip()
    if not service_name:
        return None

    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, name, unit_price, bonus_pulses, is_active
        FROM services
        WHERE lower(name) = lower(?) AND is_active = 1
        LIMIT 1
        """,
        (service_name,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_service(name, unit_price, bonus_pulses=1):
    service_id = str(uuid.uuid4())
    timestamp = _now_str()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO services (id, name, unit_price, bonus_pulses, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (service_id, name.strip(), int(unit_price), int(bonus_pulses), timestamp, timestamp),
    )
    conn.commit()
    conn.close()
    return service_id


def update_service(service_id, name=None, unit_price=None, bonus_pulses=None):
    conn = get_connection()
    row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not row:
        conn.close()
        return False

    conn.execute(
        "UPDATE services SET name = ?, unit_price = ?, bonus_pulses = ?, updated_at = ? WHERE id = ?",
        (
            (name.strip() if name is not None else row["name"]),
            int(unit_price) if unit_price is not None else int(row["unit_price"]),
            int(bonus_pulses) if bonus_pulses is not None else int(row["bonus_pulses"]),
            _now_str(),
            service_id,
        ),
    )
    conn.commit()
    conn.close()
    return True


def deactivate_service(service_id):
    conn = get_connection()
    conn.execute(
        "UPDATE services SET is_active = 0, updated_at = ? WHERE id = ?",
        (_now_str(), service_id),
    )
    conn.commit()
    conn.close()


def list_low_stock_products():
    conn = get_connection()
    rows = conn.execute(
        """
                SELECT id, name, stock_on_hand, low_stock_threshold, boxes_on_hand, low_box_threshold
        FROM products
                WHERE is_active = 1
                    AND (
                        stock_on_hand <= low_stock_threshold
                        OR boxes_on_hand <= low_box_threshold
                    )
                ORDER BY
                    CASE
                        WHEN stock_on_hand <= low_stock_threshold AND boxes_on_hand <= low_box_threshold THEN 0
                        WHEN stock_on_hand <= low_stock_threshold THEN 1
                        ELSE 2
                    END,
                    stock_on_hand ASC,
                    boxes_on_hand ASC,
                    name ASC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_transaction_with_items(
    txn_id,
    machine_id,
    base_amount,
    status,
    started_at,
    employee_id=None,
    shift_id=None,
    sale_items=None,
    request_id=None,
    customer_id=None,
    customer_name=None,
    customer_phone=None,
    paid_by_gcash=False,
    job_order_id=None,
    job_order_no=None,
):
    conn = get_connection()
    sale_items = sale_items or []
    product_total = 0
    service_total = 0
    warnings = []
    normalized_items = []
    pending_stock_movements = []

    try:
        if request_id:
            existing = conn.execute(
                """
                SELECT id, amount, product_total, service_total,
                      customer_id, customer_name, customer_phone,
                                                paid_by_gcash, gcash_amount,
                      job_order_id, job_order_no
                FROM transactions
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if existing:
                item_count_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM transaction_items WHERE transaction_id = ?",
                    (existing["id"],),
                ).fetchone()
                return {
                    "total_amount": int(existing["amount"] or 0),
                    "product_total": int(existing["product_total"] or 0),
                    "service_total": int(existing["service_total"] or 0),
                    "item_count": int(item_count_row["c"] or 0),
                    "low_stock_warnings": [],
                    "idempotent_hit": True,
                    "transaction_id": existing["id"],
                    "customer_id": existing["customer_id"],
                    "customer_name": existing["customer_name"],
                    "customer_phone": existing["customer_phone"],
                    "paid_by_gcash": int(existing["paid_by_gcash"] or 0),
                    "gcash_amount": int(existing["gcash_amount"] or 0),
                    "job_order_id": existing["job_order_id"],
                    "job_order_no": existing["job_order_no"],
                }

        conn.execute("BEGIN")

        for item in sale_items:
            kind = str(item.get("kind") or "").strip().lower()
            item_id = str(item.get("item_id") or "").strip()
            try:
                quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0

            if not item_id or quantity <= 0 or kind not in ("product", "service"):
                continue

            if kind == "product":
                product = conn.execute(
                    "SELECT id, name, unit_price, unit_cost, stock_on_hand, low_stock_threshold, is_active FROM products WHERE id = ?",
                    (item_id,),
                ).fetchone()
                if not product or int(product["is_active"] or 0) != 1:
                    warnings.append(f"Skipped inactive product: {item_id}")
                    continue

                unit_price = int(product["unit_price"])
                unit_cost = int(product["unit_cost"])
                line_total = unit_price * quantity
                line_cost = unit_cost * quantity
                new_stock = int(product["stock_on_hand"]) - quantity

                conn.execute(
                    "UPDATE products SET stock_on_hand = ?, updated_at = ? WHERE id = ?",
                    (new_stock, _now_str(), item_id),
                )
                pending_stock_movements.append((item_id, -quantity, new_stock))

                if new_stock <= int(product["low_stock_threshold"]):
                    warnings.append(
                        f"Low stock warning: {product['name']} is at {new_stock} pcs (threshold {product['low_stock_threshold']})"
                    )
                if new_stock < 0:
                    warnings.append(f"Negative stock: {product['name']} is at {new_stock} pcs")

                normalized_items.append({
                    "item_type": "product",
                    "item_id": item_id,
                    "item_name": product["name"],
                    "unit_price": unit_price,
                    "unit_cost": unit_cost,
                    "quantity": quantity,
                    "line_total": line_total,
                    "line_cost": line_cost,
                })
                product_total += line_total
                continue

            service = conn.execute(
                "SELECT id, name, unit_price, is_active FROM services WHERE id = ?",
                (item_id,),
            ).fetchone()
            if not service or int(service["is_active"] or 0) != 1:
                warnings.append(f"Skipped inactive service: {item_id}")
                continue

            unit_price = int(service["unit_price"])
            line_total = unit_price * quantity
            normalized_items.append({
                "item_type": "service",
                "item_id": item_id,
                "item_name": service["name"],
                "unit_price": unit_price,
                "unit_cost": 0,
                "quantity": quantity,
                "line_total": line_total,
                "line_cost": 0,
            })
            service_total += line_total

        total_amount = int(base_amount or 0) + product_total + service_total

        conn.execute(
            """
            INSERT INTO transactions (
                id, machine_id, amount, status, started_at,
                employee_id, shift_id, product_total, service_total, request_id,
                customer_id, customer_name, customer_phone, paid_by_gcash, gcash_amount,
                job_order_id, job_order_no
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                txn_id,
                machine_id,
                total_amount,
                status,
                started_at,
                employee_id,
                shift_id,
                product_total,
                service_total,
                request_id,
                (str(customer_id).strip() if customer_id else None),
                (str(customer_name).strip() if customer_name else None),
                (str(customer_phone).strip() if customer_phone else None),
                1 if bool(paid_by_gcash) else 0,
                total_amount if bool(paid_by_gcash) else 0,
                (str(job_order_id).strip() if job_order_id else None),
                (str(job_order_no).strip() if job_order_no else None),
            ),
        )

        for item in normalized_items:
            conn.execute(
                """
                INSERT INTO transaction_items (
                    id, transaction_id, item_type, item_id, item_name,
                    unit_price, unit_cost, quantity, line_total, line_cost, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    txn_id,
                    item["item_type"],
                    item["item_id"],
                    item["item_name"],
                    item["unit_price"],
                    item["unit_cost"],
                    item["quantity"],
                    item["line_total"],
                    item["line_cost"],
                    _now_str(),
                ),
            )

        for product_id, delta_qty, stock_after in pending_stock_movements:
            conn.execute(
                """
                INSERT INTO stock_movements (id, product_id, transaction_id, delta_qty, stock_after, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), product_id, txn_id, delta_qty, stock_after, "machine_sale", _now_str()),
            )

        conn.commit()
        return {
            "total_amount": total_amount,
            "product_total": product_total,
            "service_total": service_total,
            "item_count": len(normalized_items),
            "low_stock_warnings": warnings,
            "idempotent_hit": False,
            "transaction_id": txn_id,
            "paid_by_gcash": 1 if bool(paid_by_gcash) else 0,
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        if request_id and "request_id" in str(exc).lower():
            existing = conn.execute(
                """
                SELECT id, amount, product_total, service_total,
                      customer_id, customer_name, customer_phone,
                        paid_by_gcash, gcash_amount,
                      job_order_id, job_order_no
                FROM transactions
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if existing:
                item_count_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM transaction_items WHERE transaction_id = ?",
                    (existing["id"],),
                ).fetchone()
                return {
                    "total_amount": int(existing["amount"] or 0),
                    "product_total": int(existing["product_total"] or 0),
                    "service_total": int(existing["service_total"] or 0),
                    "item_count": int(item_count_row["c"] or 0),
                    "low_stock_warnings": [],
                    "idempotent_hit": True,
                    "transaction_id": existing["id"],
                    "customer_id": existing["customer_id"],
                    "customer_name": existing["customer_name"],
                    "customer_phone": existing["customer_phone"],
                    "paid_by_gcash": int(existing["paid_by_gcash"] or 0),
                    "gcash_amount": int(existing["gcash_amount"] or 0),
                    "job_order_id": existing["job_order_id"],
                    "job_order_no": existing["job_order_no"],
                }
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_manual_expense(amount, note=None, expense_at=None, shift_id=None, employee_id=None):
    expense_id = str(uuid.uuid4())
    timestamp = _now_str()
    expense_time = expense_at or timestamp
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO manual_expenses (id, amount, note, expense_at, shift_id, employee_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (expense_id, int(amount), note, expense_time, shift_id, employee_id, timestamp),
    )
    conn.commit()
    conn.close()
    return expense_id


def update_manual_expense(expense_id, amount=None, note=None, expense_at=None, shift_id=None, employee_id=None):
    normalized_id = str(expense_id or '').strip()
    if not normalized_id:
        return None

    updates = []
    values = []

    if amount is not None:
        updates.append("amount = ?")
        values.append(int(amount))
    if note is not None:
        updates.append("note = ?")
        values.append(note)
    if expense_at is not None:
        updates.append("expense_at = ?")
        values.append(expense_at)
    if shift_id is not None:
        updates.append("shift_id = ?")
        values.append(shift_id)
    if employee_id is not None:
        updates.append("employee_id = ?")
        values.append(employee_id)

    if not updates:
        conn = get_connection()
        row = conn.execute("SELECT * FROM manual_expenses WHERE id = ? LIMIT 1", (normalized_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    updates.append("created_at = created_at")
    values.append(normalized_id)

    conn = get_connection()
    cursor = conn.execute(
        f"UPDATE manual_expenses SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    if int(cursor.rowcount or 0) <= 0:
        conn.close()
        return None

    row = conn.execute("SELECT * FROM manual_expenses WHERE id = ? LIMIT 1", (normalized_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_manual_expenses(date_str=None, shift_id=None):
    conn = get_connection()
    if shift_id:
        rows = conn.execute(
            "SELECT * FROM manual_expenses WHERE shift_id = ? ORDER BY expense_at DESC",
            (shift_id,),
        ).fetchall()
    elif date_str:
        rows = conn.execute(
            "SELECT * FROM manual_expenses WHERE substr(expense_at, 1, 10) = ? ORDER BY expense_at DESC",
            (date_str,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM manual_expenses ORDER BY expense_at DESC LIMIT 200").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_post_cycle_payment_log(amount, logged_at=None, shift_id=None, employee_id=None, note=None):
    amount_int = int(amount)
    if amount_int <= 0:
        raise ValueError("amount must be greater than 0")

    log_id = str(uuid.uuid4())
    timestamp = _now_str()
    logged_time = str(logged_at or timestamp)

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO post_cycle_payment_logs (id, amount, logged_at, shift_id, employee_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (log_id, amount_int, logged_time, shift_id, employee_id, note, timestamp),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM post_cycle_payment_logs WHERE id = ? LIMIT 1",
        (log_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_post_cycle_payment_logs(shift_id=None, shift_ids=None, start_at=None, end_at=None, limit=500):
    conn = get_connection()

    if shift_id:
        shift_ids = [shift_id]

    if shift_ids:
        placeholders = ",".join("?" for _ in shift_ids)
        rows = conn.execute(
            f"""
            SELECT *
            FROM post_cycle_payment_logs
            WHERE shift_id IN ({placeholders})
               OR ((shift_id IS NULL OR TRIM(shift_id) = '') AND logged_at >= ? AND logged_at <= ?)
            ORDER BY logged_at DESC
            """,
            tuple(shift_ids) + (
                str(start_at or "0000-01-01 00:00:00"),
                str(end_at or "9999-12-31 23:59:59"),
            ),
        ).fetchall()
    elif start_at and end_at:
        rows = conn.execute(
            """
            SELECT *
            FROM post_cycle_payment_logs
            WHERE logged_at >= ? AND logged_at <= ?
            ORDER BY logged_at DESC
            """,
            (str(start_at), str(end_at)),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM post_cycle_payment_logs
            ORDER BY logged_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def summarize_post_cycle_payment_logs(shift_id=None, shift_ids=None, start_at=None, end_at=None):
    rows = list_post_cycle_payment_logs(shift_id=shift_id, shift_ids=shift_ids, start_at=start_at, end_at=end_at, limit=10000)
    total_amount = sum(int(r.get("amount") or 0) for r in rows)
    return {
        "count": len(rows),
        "amount": total_amount,
    }


def log_print_job(report_type, reference_id, printed_by=None, status="PRINTED"):
    job_id = str(uuid.uuid4())
    timestamp = _now_str()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO print_jobs (id, report_type, reference_id, printed_at, printed_by, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (job_id, report_type, reference_id, timestamp, printed_by, status, timestamp),
    )
    conn.commit()
    conn.close()
    return job_id


def list_print_jobs(limit=100):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM print_jobs ORDER BY printed_at DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transaction_by_request_id(request_id):
    if not request_id:
        return None
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, machine_id, amount, status, started_at, employee_id, shift_id,
             product_total, service_total, customer_id, customer_name, customer_phone,
               paid_by_gcash, gcash_amount,
               job_order_id, job_order_no
        FROM transactions
        WHERE request_id = ?
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    if not row:
        conn.close()
        return None

    item_count_row = conn.execute(
        "SELECT COUNT(*) AS c FROM transaction_items WHERE transaction_id = ?",
        (row["id"],),
    ).fetchone()
    conn.close()

    data = dict(row)
    data["item_count"] = int(item_count_row["c"] or 0)
    return data


def update_transaction_gcash_amount(transaction_id, gcash_amount):
    if not transaction_id:
        return None

    try:
        requested_gcash = int(gcash_amount)
    except (TypeError, ValueError):
        raise ValueError("gcash_amount must be a whole number")

    conn = get_connection()
    row = conn.execute(
        "SELECT id, amount FROM transactions WHERE id = ? LIMIT 1",
        (str(transaction_id).strip(),),
    ).fetchone()
    if not row:
        conn.close()
        return None

    total_amount = int(row["amount"] or 0)
    if requested_gcash < 0 or requested_gcash > total_amount:
        conn.close()
        raise ValueError("gcash_amount must be between 0 and the transaction total")

    cursor = conn.execute(
        "UPDATE transactions SET paid_by_gcash = ?, gcash_amount = ? WHERE id = ?",
        (1 if requested_gcash > 0 else 0, requested_gcash, str(transaction_id).strip()),
    )
    if int(cursor.rowcount or 0) <= 0:
        conn.commit()
        conn.close()
        return None

    row = conn.execute(
        "SELECT id, amount, paid_by_gcash, gcash_amount FROM transactions WHERE id = ? LIMIT 1",
        (str(transaction_id).strip(),),
    ).fetchone()
    conn.commit()
    conn.close()
    if not row:
        return None

    out = dict(row)
    out["cash_amount"] = int(out.get("amount") or 0) - int(out.get("gcash_amount") or 0)
    return out
def save_receipt_overrides(reference_id, kind, overrides):
    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overrides_json = json.dumps(overrides) if overrides else "{}"
    conn.execute(
        """
        INSERT INTO receipt_overrides (reference_id, kind, overrides_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(reference_id) DO UPDATE SET
            kind=excluded.kind,
            overrides_json=excluded.overrides_json,
            updated_at=excluded.updated_at
        """,
        (reference_id, kind, overrides_json, now_str),
    )
    conn.commit()
    conn.close()

def get_receipt_overrides(reference_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT overrides_json FROM receipt_overrides WHERE reference_id = ?",
        (reference_id,)
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["overrides_json"])
        except Exception:
            return {}
    return {}

def apply_receipt_overrides(payload, overrides):
    if not isinstance(overrides, dict) or not payload:
        return payload

    out = dict(payload)

    text_fields = [
        "report_date",
        "shift_number",
        "employee_name",
        "time_in",
        "time_out",
    ]
    numeric_fields = [
        "gross_collected",
        "total_sales",
        "machine_revenue",
        "cash_sales",
        "product_revenue",
        "manual_expenses",
        "cogs_total",
        "total_expenses",
        "gcash_job_order_count",
        "gcash_revenue",
        "net_sales",
        "transaction_count",
    ]

    for field in text_fields:
        if field in overrides:
            value = overrides.get(field)
            out[field] = "" if value is None else str(value)

    for field in numeric_fields:
        if field in overrides:
            try:
                out[field] = int(overrides.get(field) or 0)
            except (TypeError, ValueError):
                continue

    # Recompute key derived totals when not explicitly overridden.
    if "total_sales" not in overrides:
        out["total_sales"] = int(out.get("machine_revenue") or 0) + int(out.get("product_revenue") or 0)
    if "total_expenses" not in overrides:
        out["total_expenses"] = int(out.get("manual_expenses") or 0) + int(out.get("cogs_total") or 0)
    if "cash_sales" not in overrides:
        if "cash_sales" in out:
            out["cash_sales"] = int(out.get("cash_sales") or 0)
        else:
            out["cash_sales"] = max(0, int(out.get("gross_collected") or 0) - int(out.get("gcash_revenue") or 0))
    out["cash_revenue"] = max(0, int(out.get("cash_sales") or 0) - int(out.get("total_expenses") or 0))
    if "net_sales" not in overrides:
        out["net_sales"] = int(out.get("total_sales") or 0) - int(out.get("total_expenses") or 0)

    return out
