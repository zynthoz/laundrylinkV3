from datetime import datetime, timedelta
import os
import re
import shutil
import subprocess
import tempfile

from flask import Blueprint, jsonify, render_template, request

from database import (
    create_manual_expense,
    get_connection,
    get_receipt_format_config,
    get_recent_shift_summary_count,
    list_manual_expenses,
    list_print_jobs,
    log_print_job,
    summarize_post_cycle_payment_logs,
    update_manual_expense,
    get_receipt_overrides,
    get_day_change_time,
    get_analytics_settings,
)
from routes.security import require_admin_pin

reports_bp = Blueprint("reports", __name__)
DEFAULT_RECEIPT_SHOP_NAME = os.environ.get("RECEIPT_SHOP_NAME", "LOYOLA")
RECEIPT_PAPER_MM = int(os.environ.get("RECEIPT_PAPER_MM", "58"))
RECEIPT_TEXT_WIDTH = int(os.environ.get("RECEIPT_TEXT_WIDTH", "32"))


def _operational_day_window(day_str):
    change_time = get_day_change_time()
    try:
        parts = change_time.split(":")
        hh = int(parts[0])
        mm = int(parts[1])
    except Exception:
        hh = 8
        mm = 1

    dt_start = datetime.strptime(day_str, "%Y-%m-%d") + timedelta(hours=hh, minutes=mm)
    dt_end = dt_start + timedelta(days=1) - timedelta(seconds=1)
    return (
        dt_start.strftime("%Y-%m-%d %H:%M:%S"),
        dt_end.strftime("%Y-%m-%d %H:%M:%S")
    )


def _peso(amount):
    return f"P{int(amount or 0)}"


def _line(label, value, width=42):
    left = str(label)
    right = str(value)
    max_left = max(1, width - len(right) - 1)
    if len(left) > max_left:
        left = left[: max_left - 1] + "~"
    spaces = " " * (width - len(left) - len(right))
    return f"{left}{spaces}{right}"


def _receipt_enabled(config, key):
    elements = (config or {}).get("elements") if isinstance(config, dict) else None
    if not isinstance(elements, dict):
        return True
    return bool(elements.get(key, True))


def _receipt_order(config, group_key, default_order):
    order_cfg = (config or {}).get("order") if isinstance(config, dict) else None
    incoming = order_cfg.get(group_key) if isinstance(order_cfg, dict) and isinstance(order_cfg.get(group_key), list) else []

    ordered = []
    seen = set()
    for key in incoming:
        normalized = str(key or "").strip()
        if normalized in default_order and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)

    for key in default_order:
        if key not in seen:
            ordered.append(key)
            seen.add(key)

    return ordered


def _receipt_shop_name(config=None):
    if isinstance(config, dict):
        shop_name = str(config.get("shop_name") or "").strip()
        if shop_name:
            return shop_name
    return DEFAULT_RECEIPT_SHOP_NAME


def _format_receipt_date(value):
    raw = str(value or "").strip()
    if not raw:
        return "N/A"

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw[:19], fmt)
            return parsed.strftime("%B %d, %Y (%A)")
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%B %d, %Y (%A)")
    except ValueError:
        return raw


def _split_receipt_date(value):
    raw = str(value or "").strip()
    if not raw or raw == "N/A":
        return "N/A", ""

    match = re.match(r"^(.*)\s*\(([^)]+)\)\s*$", raw)
    if match:
        return match.group(1).strip() or raw, match.group(2).strip()

    return raw, ""


def _render_receipt_text(report):
    width = max(24, min(64, int(RECEIPT_TEXT_WIDTH)))
    divider = "-" * width
    config = get_receipt_format_config()
    receipt_group = "recent_shifts_summary" if report.get("report_type") == "recent_shifts_summary" else "shiftday"
    product_lines = report.get("product_breakdown") or []
    service_lines = report.get("service_breakdown") or []
    expense_lines = report.get("expense_breakdown") or []
    machine_usage_lines = report.get("machine_usage_breakdown") or []

    top_spacing = int(config.get("top_spacing_lines", 3))
    lines = [""] * top_spacing
    lines.extend([
        _receipt_shop_name(config),
        divider,
    ])

    if receipt_group == "recent_shifts_summary":
        default_order = [
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
            "recent_shifts_summary.job_orders_section",
            "recent_shifts_summary.net_sales_section",
        ]
    else:
        default_order = [
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
            "shiftday.job_orders_section",
            "shiftday.net_sales_section",
        ]

    ordered_sections = _receipt_order(config, receipt_group, default_order)

    for section_key in ordered_sections:
        if not _receipt_enabled(config, section_key):
            continue

        if section_key == f"{receipt_group}.date_line":
            display_date = _split_receipt_date(report.get("report_date"))[0]
            lines.append(_line("DATE", display_date, width))
        elif section_key == f"{receipt_group}.weekday_line":
            display_day = _split_receipt_date(report.get("report_date"))[1]
            lines.append(_line("DAY", display_day, width))
        elif section_key == f"{receipt_group}.shift_number_line":
            lines.append(_line("SHIFT No.", report.get("shift_number") or "N/A", width))
        elif section_key == f"{receipt_group}.employee_section":
            lines.extend([
                divider,
                "1) EMPLOYEE",
                _line("Name", report.get("employee_name") or "N/A", width),
                _line("Time In", report.get("time_in") or "N/A", width),
                _line("Time Out", report.get("time_out") or "N/A", width),
            ])
        elif section_key == f"{receipt_group}.machine_revenue_section":
            lines.extend([
                divider,
                "2) MACHINE REVENUE",
                _line("Amount", _peso(report.get("machine_revenue")), width),
            ])
        elif section_key == f"{receipt_group}.machine_usage_breakdown":
            lines.append(divider)
            lines.append("MACHINE USAGE SUMMARY")
            if machine_usage_lines:
                for row in machine_usage_lines:
                    label = row.get("machine_type_label") or str(row.get("machine_type") or "Machine").title()
                    lines.append(_line(f"- {label} Used", int(row.get("count") or 0), width))
                    lines.append(_line(f"  {label} Revenue", _peso(row.get("revenue") or 0), width))
            else:
                lines.append(_line("- None", _peso(0), width))
        elif section_key == f"{receipt_group}.product_revenue_section":
            lines.extend([
                divider,
                "3) PRODUCT REVENUE",
            ])
            if product_lines:
                for row in product_lines:
                    lines.append(_line(f"- {row['name']} x{row['qty']}", _peso(row["total"]), width))
            else:
                lines.append(_line("- None", _peso(0), width))
            lines.append(_line("Total", _peso(report.get("product_revenue")), width))
        elif section_key == f"{receipt_group}.service_tips_section":
            lines.extend([
                divider,
                "4) SERVICE TIPS",
                _line("Total", _peso(report.get("service_revenue")), width),
            ])
            if service_lines:
                for row in service_lines:
                    lines.append(_line(f"- {row['name']} x{row['qty']}", _peso(row["total"]), width))
            else:
                lines.append(_line("- None", _peso(0), width))
        elif section_key == f"{receipt_group}.cash_revenue_section":
            lines.extend([
                divider,
                "5) CASH REVENUE (NET)",
                _line("Net", _peso(report.get("cash_revenue")), width),
            ])
        elif section_key == f"{receipt_group}.gcash_revenue_section":
            lines.extend([
                divider,
                "6) GCASH REVENUE",
                _line("Orders", int(report.get("gcash_job_order_count") or 0), width),
                _line("Total", _peso(report.get("gcash_revenue")), width),
            ])
        elif section_key == f"{receipt_group}.expenses_section":
            lines.extend([
                divider,
                "7) EXPENSES",
                _line("Total", _peso(report.get("total_expenses")), width),
            ])
            if expense_lines:
                for row in expense_lines:
                    lines.append(_line(f"- {row['name']} x{row['count']}", _peso(row["total"]), width))
            else:
                lines.append(_line("- None", _peso(0), width))
        elif section_key == f"{receipt_group}.job_orders_section":
            promo_count = int(report.get("job_order_promo_count") or 0)
            promo_lines = []
            for item in report.get("job_order_promo_breakdown") or []:
                promo_lines.append(_line(f"  - {item['name']}", item["count"], width))
            
            lines.extend([
                divider,
                "JOB ORDERS SUMMARY",
                _line("Total Orders", int(report.get("job_order_count") or 0), width),
                _line("- Used", int(report.get("job_order_used_count") or 0), width),
                _line("- Open", int(report.get("job_order_open_count") or 0), width),
                _line("Total Revenue", _peso(report.get("job_order_total_amount") or 0), width),
                _line("Promo Orders", promo_count, width),
            ])
            if promo_lines:
                lines.append("PROMO BREAKDOWN:")
                lines.extend(promo_lines)
        elif section_key == f"{receipt_group}.net_sales_section":
            lines.extend([
                divider,
                "8) NET SALES",
                _line("Net", _peso(report.get("net_sales")), width),
            ])

    lines.append(divider)
    if _receipt_enabled(config, "common.generated_footer"):
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    bottom_spacing = int(config.get("bottom_spacing_lines", 6))
    lines.extend([""] * bottom_spacing)
    return "\n".join(lines)


def _discover_cups_printers():
    if not shutil.which("lpstat"):
        return []

    result = subprocess.run(
        ["lpstat", "-v"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    printers = []
    for line in result.stdout.splitlines():
        # Expected format: "device for PRINTER_NAME: DEVICE_URI"
        match = re.match(r"^device for\s+([^:]+):\s+(.+)$", line.strip())
        if not match:
            continue
        name = match.group(1).strip()
        uri = match.group(2).strip()
        printers.append({"name": name, "uri": uri, "is_usb": "usb://" in uri.lower()})
    return printers


def _get_default_printer_name():
    if not shutil.which("lpstat"):
        return None

    result = subprocess.run(
        ["lpstat", "-d"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    match = re.search(r":\s*(.+)$", result.stdout.strip())
    if match:
        return match.group(1).strip()
    return None


def _resolve_target_printer(printer_name=None):
    printers = _discover_cups_printers()
    if not printers:
        raise RuntimeError("No CUPS printers found. Connect a USB printer and confirm CUPS is running.")

    names = {p["name"] for p in printers}
    if printer_name:
        if printer_name not in names:
            raise RuntimeError(f"Printer '{printer_name}' is not available on this device.")
        return printer_name

    for printer in printers:
        if printer["is_usb"]:
            return printer["name"]

    default_name = _get_default_printer_name()
    if default_name and default_name in names:
        return default_name

    return printers[0]["name"]


def _send_to_cups(receipt_text, title, printer_name=None, copies=1):
    if not shutil.which("lp"):
        raise RuntimeError("CUPS printing command 'lp' is not installed.")

    target_printer = _resolve_target_printer(printer_name=printer_name)

    fd, temp_path = tempfile.mkstemp(prefix="laundrylink-receipt-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(receipt_text)

        result = subprocess.run(
            ["lp", "-d", target_printer, "-n", str(max(1, int(copies))), "-t", title, temp_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown CUPS error").strip()
            raise RuntimeError(f"CUPS print failed: {err}")

        return {
            "printer": target_printer,
            "job": (result.stdout or "").strip(),
        }
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _sum_item_usage(txn_ids):
    if not txn_ids:
        return {
            "product_qty": 0,
            "service_qty": 0,
            "cogs_total": 0,
        }

    conn = get_connection()
    placeholders = ",".join("?" for _ in txn_ids)
    rows = conn.execute(
        f"""
        SELECT item_type, SUM(quantity) AS qty, SUM(line_cost) AS cost
        FROM transaction_items
        WHERE transaction_id IN ({placeholders})
        GROUP BY item_type
        """,
        txn_ids,
    ).fetchall()
    conn.close()

    data = {"product_qty": 0, "service_qty": 0, "cogs_total": 0}
    for row in rows:
        kind = row["item_type"]
        qty = int(row["qty"] or 0)
        cost = int(row["cost"] or 0)
        if kind == "product":
            data["product_qty"] = qty
            data["cogs_total"] += cost
        elif kind == "service":
            data["service_qty"] = qty
    return data


def _build_item_revenue_breakdown(txn_ids):
    if not txn_ids:
        return {"product": [], "service": []}

    conn = get_connection()
    placeholders = ",".join("?" for _ in txn_ids)
    rows = conn.execute(
        f"""
        SELECT item_type, item_name, SUM(quantity) AS qty, SUM(line_total) AS total
        FROM transaction_items
        WHERE transaction_id IN ({placeholders})
        GROUP BY item_type, item_name
        ORDER BY item_type ASC, item_name ASC
        """,
        txn_ids,
    ).fetchall()
    conn.close()

    out = {"product": [], "service": []}
    for row in rows:
        bucket = row["item_type"]
        if bucket not in out:
            continue
        out[bucket].append(
            {
                "name": row["item_name"],
                "qty": int(row["qty"] or 0),
                "total": int(row["total"] or 0),
            }
        )
    return out


def _build_expense_breakdown(expense_rows, item_usage):
    breakdown = []
    for row in expense_rows:
        breakdown.append(
            {
                "name": row["name"] or "Manual Expense",
                "count": int(row["count"] or 0),
                "total": int(row["total"] or 0),
            }
        )

    if int(item_usage.get("cogs_total") or 0) > 0:
        breakdown.append(
            {
                "name": "COGS",
                "count": int(item_usage.get("product_qty") or 0),
                "total": int(item_usage.get("cogs_total") or 0),
            }
        )
    return breakdown


def _compute_cash_sales_and_net(total_sales, txn_gcash_revenue, post_cycle_transfer_amount, total_expenses, service_adjustment=0):
    effective_sales = int(total_sales or 0) + int(service_adjustment or 0)
    cash_sales = effective_sales - int(txn_gcash_revenue or 0) - int(post_cycle_transfer_amount or 0)
    net_cash = cash_sales - int(total_expenses or 0)
    return cash_sales, net_cash


def _build_machine_usage_breakdown(txns):
    machine_ids = sorted({
        str(txn.get("machine_id") or "").strip()
        for txn in (txns or [])
        if str(txn.get("machine_id") or "").strip() and str(txn.get("machine_id") or "").strip() != "post-cycle-addons"
    })
    if not machine_ids:
        return []

    conn = get_connection()
    placeholders = ",".join("?" for _ in machine_ids)
    rows = conn.execute(
        f"""
        SELECT id, type
        FROM machines
        WHERE id IN ({placeholders})
        """,
        machine_ids,
    ).fetchall()
    conn.close()

    machine_meta = {str(row["id"]): str(row["type"] or "").strip().lower() for row in rows}

    def _type_rank(machine_type):
        if machine_type == "washer":
            return 0
        if machine_type == "dryer":
            return 1
        return 2

    summary = {}
    for txn in txns or []:
        machine_id = str(txn.get("machine_id") or "").strip()
        if not machine_id or machine_id == "post-cycle-addons":
            continue

        machine_type = machine_meta.get(machine_id) or "unknown"
        amount = int(txn.get("amount") or 0)
        product_total = int(txn.get("product_total") or 0)
        service_total = int(txn.get("service_total") or 0)
        machine_amount = max(0, amount - product_total - service_total)

        if machine_type not in summary:
            summary[machine_type] = {"count": 0, "revenue": 0}

        summary[machine_type]["count"] += 1
        summary[machine_type]["revenue"] += machine_amount

    breakdown = []
    for machine_type, values in summary.items():
        label = machine_type.title() if machine_type in ("washer", "dryer") else "Unknown"
        breakdown.append(
            {
                "machine_type": machine_type,
                "machine_type_label": label,
                "count": int(values["count"]),
                "revenue": int(values["revenue"]),
            }
        )

    breakdown.sort(key=lambda row: (_type_rank(row["machine_type"]), row["machine_type_label"].lower()))
    return breakdown


def _apply_receipt_overrides(payload, overrides):
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


def _build_shift_receipt_data(shift_id):
    conn = get_connection()
    shift = conn.execute(
        """
        SELECT s.id, s.employee_id, s.location_id, s.started_at, s.ended_at, s.end_reason,
               e.display_name
        FROM shift_sessions s
        JOIN employees e ON e.id = s.employee_id
        WHERE s.id = ?
        """,
        (shift_id,),
    ).fetchone()

    if not shift:
        conn.close()
        return None

    tx_rows = conn.execute(
        """
        SELECT id, machine_id, amount, status, started_at, product_total, service_total,
               paid_by_gcash, gcash_amount
        FROM transactions
        WHERE shift_id = ? AND status IN ('COMPLETED', 'SIMULATED')
        ORDER BY started_at ASC
        """,
        (shift_id,),
    ).fetchall()

    expense_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(note), ''), 'Manual Expense') AS name,
               COUNT(*) AS count,
               SUM(amount) AS total
        FROM manual_expenses
        WHERE shift_id = ?
           OR (
                (shift_id IS NULL OR TRIM(shift_id) = '')
                AND expense_at >= ?
                AND expense_at <= ?
           )
        GROUP BY COALESCE(NULLIF(TRIM(note), ''), 'Manual Expense')
        ORDER BY name ASC
        """,
        (
            shift_id,
            shift["started_at"],
            shift["ended_at"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchall()

    job_order_rows = conn.execute(
        """
        SELECT id, job_order_no, machine_name, status, total_amount, paid_by_gcash, promo_id, promo_name
        FROM job_orders
        WHERE (
                created_by_shift_id = ?
                OR (
                     created_by_shift_id IS NULL
                     AND created_by_employee_id = ?
                     AND created_at >= ?
                     AND created_at <= ?
                )
              )
          AND (
                status = 'OPEN'
                OR id IN (
                    SELECT job_order_id FROM transactions
                    WHERE job_order_id IS NOT NULL
                      AND status IN ('COMPLETED', 'SIMULATED')
                )
          )
        ORDER BY created_at ASC
        """,
        (
            shift_id,
            shift["employee_id"],
            shift["started_at"],
            shift["ended_at"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchall()
    conn.close()

    txns = [dict(r) for r in tx_rows]
    txn_ids = [t["id"] for t in txns]
    item_usage = _sum_item_usage(txn_ids)
    item_breakdown = _build_item_revenue_breakdown(txn_ids)
    machine_usage_breakdown = _build_machine_usage_breakdown(txns)

    gross_collected = sum(int(t.get("amount") or 0) for t in txns)
    product_revenue = sum(int(t.get("product_total") or 0) for t in txns)
    service_tips = sum(int(t.get("service_total") or 0) for t in txns)
    machine_revenue = gross_collected - product_revenue - service_tips
    total_sales = gross_collected

    manual_expenses = sum(int(r["total"] or 0) for r in expense_rows)
    total_expenses = manual_expenses + item_usage["cogs_total"]
    expense_breakdown = _build_expense_breakdown(expense_rows, item_usage)
    job_orders = [dict(r) for r in job_order_rows]
    job_order_count = len(job_orders)
    job_order_used_count = sum(1 for r in job_orders if str(r.get("status") or "").upper() == "USED")
    job_order_open_count = sum(1 for r in job_orders if str(r.get("status") or "").upper() == "OPEN")
    job_order_total_amount = sum(int(r.get("total_amount") or 0) for r in job_orders)

    promo_orders = [r for r in job_orders if r.get("promo_id") or r.get("promo_name")]
    job_order_promo_count = len(promo_orders)
    promo_counts = {}
    for r in promo_orders:
        name = str(r.get("promo_name") or r.get("promo_id") or "Unknown Promo").strip()
        promo_counts[name] = promo_counts.get(name, 0) + 1
    job_order_promo_breakdown = [{"name": name, "count": count} for name, count in promo_counts.items()]
    txn_gcash_revenue = 0
    txn_gcash_count = 0
    for txn in txns:
        amount = int(txn.get("amount") or 0)
        if txn.get("gcash_amount") is not None:
            gcash_amount = int(txn.get("gcash_amount") or 0)
        else:
            gcash_amount = amount if int(txn.get("paid_by_gcash") or 0) == 1 else 0
        gcash_amount = max(0, min(gcash_amount, amount))
        txn_gcash_revenue += gcash_amount
        if gcash_amount > 0:
            txn_gcash_count += 1

    post_cycle_transfer = summarize_post_cycle_payment_logs(
        shift_id=shift_id,
        start_at=shift["started_at"],
        end_at=shift["ended_at"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    post_cycle_transfer_amount = int(post_cycle_transfer.get("amount") or 0)
    post_cycle_transfer_count = int(post_cycle_transfer.get("count") or 0)

    gcash_job_orders = [r for r in job_orders if int(r.get("paid_by_gcash") or 0) == 1]
    gcash_job_order_count = txn_gcash_count + len(gcash_job_orders) + post_cycle_transfer_count
    gcash_revenue = txn_gcash_revenue + sum(int(r.get("total_amount") or 0) for r in gcash_job_orders) + post_cycle_transfer_amount

    analytics_settings = get_analytics_settings()
    include_service_in_net = bool(analytics_settings.get("include_service_revenue_in_net", False))
    _svc_adj = 0 if include_service_in_net else -service_tips

    cash_sales, cash_revenue = _compute_cash_sales_and_net(
        total_sales,
        txn_gcash_revenue,
        post_cycle_transfer_amount,
        total_expenses,
        service_adjustment=_svc_adj,
    )
    net_sales = total_sales + _svc_adj - total_expenses
    job_order_breakdown = [
        {
            "job_order_no": r.get("job_order_no") or r.get("id"),
            "machine": r.get("machine_name") or "N/A",
            "status": str(r.get("status") or "OPEN").upper(),
            "total": int(r.get("total_amount") or 0),
            "paid_by_gcash": int(r.get("paid_by_gcash") or 0),
        }
        for r in job_orders
    ]

    return {
        "shop_name": _receipt_shop_name(get_receipt_format_config()),
        "report_type": "shift",
        "reference_id": shift["id"],
        "shift_number": shift["id"],
        "employee_name": shift["display_name"],
        "time_in": shift["started_at"],
        "time_out": shift["ended_at"] or "ACTIVE",
        "report_date": _format_receipt_date((shift["started_at"] or "")[:10]),
        "report_date_text": _split_receipt_date(_format_receipt_date((shift["started_at"] or "")[:10]))[0],
        "report_weekday": _split_receipt_date(_format_receipt_date((shift["started_at"] or "")[:10]))[1],
        "paper_width_mm": RECEIPT_PAPER_MM,
        "gross_collected": gross_collected,
        "total_sales": total_sales,
        "machine_revenue": machine_revenue,
        "cash_sales": cash_sales,
        "cash_revenue": cash_revenue,
        "machine_usage_breakdown": machine_usage_breakdown,
        "product_revenue": product_revenue,
        "service_revenue": service_tips,
        "products_used": item_usage["product_qty"],
        "services_used": item_usage["service_qty"],
        "cogs_total": item_usage["cogs_total"],
        "manual_expenses": manual_expenses,
        "total_expenses": total_expenses,
        "product_breakdown": item_breakdown["product"],
        "service_breakdown": item_breakdown["service"],
        "job_order_count": job_order_count,
        "job_order_used_count": job_order_used_count,
        "job_order_open_count": job_order_open_count,
        "job_order_total_amount": job_order_total_amount,
        "job_order_promo_count": job_order_promo_count,
        "job_order_promo_breakdown": job_order_promo_breakdown,
        "gcash_job_order_count": gcash_job_order_count,
        "gcash_revenue": gcash_revenue,
        "post_cycle_transfer_count": post_cycle_transfer_count,
        "post_cycle_transfer_amount": post_cycle_transfer_amount,
        "job_order_breakdown": job_order_breakdown,
        "expense_breakdown": expense_breakdown,
        "net_sales": net_sales,
        "transaction_count": len(txns),
        "transactions": txns,
    }


def _build_day_receipt_data(day_str):
    day_start, day_end = _operational_day_window(day_str)

    conn = get_connection()

    tx_rows = conn.execute(
        """
        SELECT id, machine_id, amount, status, started_at, employee_id, shift_id, product_total, service_total,
               paid_by_gcash, gcash_amount
        FROM transactions
        WHERE started_at >= ? AND started_at <= ?
          AND status IN ('COMPLETED', 'SIMULATED')
        ORDER BY started_at ASC
        """,
        (day_start, day_end),
    ).fetchall()

    employee_rows = conn.execute(
        """
        SELECT DISTINCT e.display_name
        FROM transactions t
        LEFT JOIN employees e ON e.id = t.employee_id
        WHERE t.started_at >= ? AND t.started_at <= ?
          AND t.status IN ('COMPLETED', 'SIMULATED')
        """,
        (day_start, day_end),
    ).fetchall()

    expense_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(note), ''), 'Manual Expense') AS name,
               COUNT(*) AS count,
               SUM(amount) AS total
        FROM manual_expenses
        WHERE expense_at >= ? AND expense_at <= ?
        GROUP BY COALESCE(NULLIF(TRIM(note), ''), 'Manual Expense')
        ORDER BY name ASC
        """,
        (day_start, day_end),
    ).fetchall()

    job_order_rows = conn.execute(
        """
        SELECT id, job_order_no, machine_name, status, total_amount, paid_by_gcash, promo_id, promo_name
        FROM job_orders
        WHERE created_at >= ? AND created_at <= ?
          AND (
                status = 'OPEN'
                OR id IN (
                    SELECT job_order_id FROM transactions
                    WHERE job_order_id IS NOT NULL
                      AND status IN ('COMPLETED', 'SIMULATED')
                )
          )
        ORDER BY created_at ASC
        """,
        (day_start, day_end),
    ).fetchall()
    conn.close()

    txns = [dict(r) for r in tx_rows]
    txn_ids = [t["id"] for t in txns]
    item_usage = _sum_item_usage(txn_ids)
    item_breakdown = _build_item_revenue_breakdown(txn_ids)
    machine_usage_breakdown = _build_machine_usage_breakdown(txns)

    gross_collected = sum(int(t.get("amount") or 0) for t in txns)
    product_revenue = sum(int(t.get("product_total") or 0) for t in txns)
    service_tips = sum(int(t.get("service_total") or 0) for t in txns)
    machine_revenue = gross_collected - product_revenue - service_tips
    total_sales = gross_collected

    employee_names = [row["display_name"] for row in employee_rows if row["display_name"]]
    employee_label = ", ".join(employee_names) if employee_names else "N/A"

    manual_expenses = sum(int(r["total"] or 0) for r in expense_rows)
    total_expenses = manual_expenses + item_usage["cogs_total"]
    expense_breakdown = _build_expense_breakdown(expense_rows, item_usage)
    job_orders = [dict(r) for r in job_order_rows]
    txn_gcash_revenue = 0
    txn_gcash_count = 0
    for txn in txns:
        amount = int(txn.get("amount") or 0)
        if txn.get("gcash_amount") is not None:
            gcash_amount = int(txn.get("gcash_amount") or 0)
        else:
            gcash_amount = amount if int(txn.get("paid_by_gcash") or 0) == 1 else 0
        gcash_amount = max(0, min(gcash_amount, amount))
        txn_gcash_revenue += gcash_amount
        if gcash_amount > 0:
            txn_gcash_count += 1

    post_cycle_transfer = summarize_post_cycle_payment_logs(start_at=day_start, end_at=day_end)
    post_cycle_transfer_amount = int(post_cycle_transfer.get("amount") or 0)
    post_cycle_transfer_count = int(post_cycle_transfer.get("count") or 0)

    gcash_job_orders = [r for r in job_orders if int(r.get("paid_by_gcash") or 0) == 1]
    gcash_job_order_count = txn_gcash_count + len(gcash_job_orders) + post_cycle_transfer_count
    gcash_revenue = txn_gcash_revenue + sum(int(r.get("total_amount") or 0) for r in gcash_job_orders) + post_cycle_transfer_amount

    analytics_settings = get_analytics_settings()
    include_service_in_net = bool(analytics_settings.get("include_service_revenue_in_net", False))
    _svc_adj = 0 if include_service_in_net else -service_tips

    cash_sales, cash_revenue = _compute_cash_sales_and_net(
        total_sales,
        txn_gcash_revenue,
        post_cycle_transfer_amount,
        total_expenses,
        service_adjustment=_svc_adj,
    )
    net_sales = total_sales + _svc_adj - total_expenses
    job_order_count = len(job_orders)
    job_order_used_count = sum(1 for r in job_orders if str(r.get("status") or "").upper() == "USED")
    job_order_open_count = sum(1 for r in job_orders if str(r.get("status") or "").upper() == "OPEN")
    job_order_total_amount = sum(int(r.get("total_amount") or 0) for r in job_orders)

    promo_orders = [r for r in job_orders if r.get("promo_id") or r.get("promo_name")]
    job_order_promo_count = len(promo_orders)
    promo_counts = {}
    for r in promo_orders:
        name = str(r.get("promo_name") or r.get("promo_id") or "Unknown Promo").strip()
        promo_counts[name] = promo_counts.get(name, 0) + 1
    job_order_promo_breakdown = [{"name": name, "count": count} for name, count in promo_counts.items()]
    job_order_breakdown = [
        {
            "job_order_no": r.get("job_order_no") or r.get("id"),
            "machine": r.get("machine_name") or "N/A",
            "status": str(r.get("status") or "OPEN").upper(),
            "total": int(r.get("total_amount") or 0),
            "paid_by_gcash": int(r.get("paid_by_gcash") or 0),
        }
        for r in job_orders
    ]

    return {
        "shop_name": _receipt_shop_name(get_receipt_format_config()),
        "report_type": "day",
        "reference_id": day_str,
        "shift_number": "ALL",
        "employee_name": employee_label,
        "time_in": day_start,
        "time_out": day_end,
        "report_date": _format_receipt_date(day_str),
        "report_window": f"{day_start} to {day_end}",
        "paper_width_mm": RECEIPT_PAPER_MM,
        "gross_collected": gross_collected,
        "total_sales": total_sales,
        "machine_revenue": machine_revenue,
        "cash_sales": cash_sales,
        "cash_revenue": cash_revenue,
        "machine_usage_breakdown": machine_usage_breakdown,
        "product_revenue": product_revenue,
        "service_revenue": service_tips,
        "products_used": item_usage["product_qty"],
        "services_used": item_usage["service_qty"],
        "cogs_total": item_usage["cogs_total"],
        "manual_expenses": manual_expenses,
        "total_expenses": total_expenses,
        "product_breakdown": item_breakdown["product"],
        "service_breakdown": item_breakdown["service"],
        "job_order_count": job_order_count,
        "job_order_used_count": job_order_used_count,
        "job_order_open_count": job_order_open_count,
        "job_order_total_amount": job_order_total_amount,
        "job_order_promo_count": job_order_promo_count,
        "job_order_promo_breakdown": job_order_promo_breakdown,
        "gcash_job_order_count": gcash_job_order_count,
        "gcash_revenue": gcash_revenue,
        "post_cycle_transfer_count": post_cycle_transfer_count,
        "post_cycle_transfer_amount": post_cycle_transfer_amount,
        "job_order_breakdown": job_order_breakdown,
        "expense_breakdown": expense_breakdown,
        "net_sales": net_sales,
        "transaction_count": len(txns),
        "transactions": txns,
    }


def _build_transaction_receipt_data(transaction_id):
    conn = get_connection()
    txn = conn.execute(
        """
        SELECT id, machine_id, amount, status, started_at, employee_id, shift_id,
             product_total, service_total, customer_id, customer_name, customer_phone,
                         paid_by_gcash, gcash_amount,
               job_order_id, job_order_no
        FROM transactions
        WHERE id = ?
        """,
        (transaction_id,),
    ).fetchone()
    if not txn:
        conn.close()
        return None

    employee = None
    if txn["employee_id"]:
        employee = conn.execute(
            "SELECT display_name FROM employees WHERE id = ?",
            (txn["employee_id"],),
        ).fetchone()

    item_rows = conn.execute(
        """
        SELECT item_type, item_name, quantity, line_total
        FROM transaction_items
        WHERE transaction_id = ?
        ORDER BY item_type ASC, item_name ASC
        """,
        (transaction_id,),
    ).fetchall()
    conn.close()

    items = [dict(r) for r in item_rows]
    base_amount = int(txn["amount"] or 0) - int(txn["product_total"] or 0) - int(txn["service_total"] or 0)
    total_amount = int(txn["amount"] or 0)
    gcash_amount = int(txn["gcash_amount"] or 0) if txn["gcash_amount"] is not None else (total_amount if int(txn["paid_by_gcash"] or 0) == 1 else 0)
    gcash_amount = max(0, min(gcash_amount, total_amount))
    cash_amount = total_amount - gcash_amount

    if gcash_amount <= 0:
        payment_method = "Cash"
    elif gcash_amount >= total_amount:
        payment_method = "GCash"
    else:
        payment_method = "Split (Cash + GCash)"

    return {
        "shop_name": _receipt_shop_name(get_receipt_format_config()),
        "transaction_id": txn["id"],
        "report_date": _format_receipt_date(txn["started_at"]),
        "machine_id": txn["machine_id"],
        "status": txn["status"],
        "employee_name": (employee["display_name"] if employee else "N/A"),
        "shift_id": txn["shift_id"] or "N/A",
        "job_order_id": txn["job_order_id"] or "N/A",
        "job_order_no": txn["job_order_no"] or "N/A",
        "customer_id": txn["customer_id"] or "N/A",
        "customer_name": txn["customer_name"] or "N/A",
        "customer_phone": txn["customer_phone"] or "N/A",
        "base_amount": base_amount,
        "product_total": int(txn["product_total"] or 0),
        "service_total": int(txn["service_total"] or 0),
        "total_amount": total_amount,
        "cash_amount": cash_amount,
        "gcash_amount": gcash_amount,
        "payment_method": payment_method,
        "items": items,
    }


def _build_shifts_summary_receipt_data_by_ids(shift_ids, requested_count=None, custom_title=None):
    shifts = []
    employee_names = []
    employee_seen = set()
    first_time_in = None
    last_time_out = None
    first_date_label = None
    last_date_label = None

    machine_revenue_total = 0
    cash_sales_total = 0
    product_revenue_total = 0
    service_revenue_total = 0
    cash_revenue_total = 0
    gcash_revenue_total = 0
    gcash_job_order_count_total = 0
    job_order_count_total = 0
    job_order_used_count_total = 0
    job_order_open_count_total = 0
    job_order_total_amount_total = 0
    job_order_promo_count_total = 0
    promo_count_map = {}

    machine_usage_map = {}
    product_map = {}
    service_map = {}
    expense_map = {}

    total_sales = 0
    total_expenses = 0
    net_sales = 0
    total_transactions = 0

    has_active_shift = False
    if shift_ids:
        conn = get_connection()
        placeholders = ",".join("?" for _ in shift_ids)
        active_rows = conn.execute(
            f"SELECT id FROM shift_sessions WHERE id IN ({placeholders}) AND ended_at IS NULL",
            shift_ids,
        ).fetchall()
        has_active_shift = len(active_rows) > 0
        conn.close()

    for index, shift_id in enumerate(shift_ids, start=1):
        shift_report = _build_shift_receipt_data(shift_id)
        if not shift_report:
            continue

        shift_sales = int(shift_report.get("total_sales") or 0)
        shift_expenses = int(shift_report.get("total_expenses") or 0)
        shift_net = int(shift_report.get("net_sales") or 0)
        shift_transactions = int(shift_report.get("transaction_count") or 0)

        machine_revenue_total += int(shift_report.get("machine_revenue") or 0)
        cash_sales_total += int(shift_report.get("cash_sales") or 0)
        product_revenue_total += int(shift_report.get("product_revenue") or 0)
        service_revenue_total += int(shift_report.get("service_revenue") or 0)
        cash_revenue_total += int(shift_report.get("cash_revenue") or 0)
        gcash_revenue_total += int(shift_report.get("gcash_revenue") or 0)
        gcash_job_order_count_total += int(shift_report.get("gcash_job_order_count") or 0)
        job_order_count_total += int(shift_report.get("job_order_count") or 0)
        job_order_used_count_total += int(shift_report.get("job_order_used_count") or 0)
        job_order_open_count_total += int(shift_report.get("job_order_open_count") or 0)
        job_order_total_amount_total += int(shift_report.get("job_order_total_amount") or 0)
        job_order_promo_count_total += int(shift_report.get("job_order_promo_count") or 0)
        for item in shift_report.get("job_order_promo_breakdown") or []:
            name = item["name"]
            promo_count_map[name] = promo_count_map.get(name, 0) + item["count"]

        emp_name = str(shift_report.get("employee_name") or "").strip()
        if emp_name and emp_name not in employee_seen and emp_name != "N/A":
            employee_seen.add(emp_name)
            employee_names.append(emp_name)

        time_in = str(shift_report.get("time_in") or "").strip()
        if time_in and time_in != "N/A" and (first_time_in is None or time_in < first_time_in):
            first_time_in = time_in

        time_out = str(shift_report.get("time_out") or "").strip()
        if time_out and time_out not in ("N/A", "ACTIVE") and (last_time_out is None or time_out > last_time_out):
            last_time_out = time_out

        date_label = str(shift_report.get("report_date") or "").strip()
        if date_label and date_label != "N/A":
            if first_date_label is None:
                first_date_label = date_label
            last_date_label = date_label

        for row in shift_report.get("machine_usage_breakdown") or []:
            key = str(row.get("machine_type") or row.get("machine_type_label") or "machine").strip().lower()
            if key not in machine_usage_map:
                machine_usage_map[key] = {
                    "machine_type": row.get("machine_type") or key,
                    "machine_type_label": row.get("machine_type_label") or str(row.get("machine_type") or key).title(),
                    "count": 0,
                    "revenue": 0,
                }
            machine_usage_map[key]["count"] += int(row.get("count") or 0)
            machine_usage_map[key]["revenue"] += int(row.get("revenue") or 0)

        for row in shift_report.get("product_breakdown") or []:
            name = str(row.get("name") or "Item").strip()
            if name not in product_map:
                product_map[name] = {"name": name, "qty": 0, "total": 0}
            product_map[name]["qty"] += int(row.get("qty") or 0)
            product_map[name]["total"] += int(row.get("total") or 0)

        for row in shift_report.get("service_breakdown") or []:
            name = str(row.get("name") or "Service").strip()
            if name not in service_map:
                service_map[name] = {"name": name, "qty": 0, "total": 0}
            service_map[name]["qty"] += int(row.get("qty") or 0)
            service_map[name]["total"] += int(row.get("total") or 0)

        for row in shift_report.get("expense_breakdown") or []:
            name = str(row.get("name") or "Expense").strip()
            if name not in expense_map:
                expense_map[name] = {"name": name, "count": 0, "total": 0}
            expense_map[name]["count"] += int(row.get("count") or 0)
            expense_map[name]["total"] += int(row.get("total") or 0)

        total_sales += shift_sales
        total_expenses += shift_expenses
        net_sales += shift_net
        total_transactions += shift_transactions

        shifts.append(
            {
                "index": index,
                "shift_number": shift_report.get("shift_number") or "N/A",
                "employee_name": shift_report.get("employee_name") or "N/A",
                "date": shift_report.get("report_date") or "N/A",
                "transaction_count": shift_transactions,
                "total_sales": shift_sales,
                "total_expenses": shift_expenses,
                "net_sales": shift_net,
            }
        )

    if not shifts:
        return None

    if first_date_label and last_date_label and first_date_label != last_date_label:
        report_date = f"{first_date_label} to {last_date_label}"
    else:
        report_date = first_date_label or "N/A"

    primary_shift_date = shifts[0]["date"] if shifts else report_date
    report_date_text, report_weekday = _split_receipt_date(primary_shift_date)

    if has_active_shift:
        last_time_out = "ACTIVE"

    if not custom_title:
        custom_title = f"LAST {len(shifts)}"

    return {
        "shop_name": _receipt_shop_name(get_receipt_format_config()),
        "report_type": "recent_shifts_summary",
        "shift_number": custom_title,
        "employee_name": ", ".join(employee_names) if employee_names else "N/A",
        "time_in": first_time_in or "N/A",
        "time_out": last_time_out or "N/A",
        "report_date": report_date,
        "report_date_text": report_date_text,
        "report_weekday": report_weekday,
        "requested_count": requested_count or len(shifts),
        "actual_count": len(shifts),
        "paper_width_mm": RECEIPT_PAPER_MM,
        "shifts": shifts,
        "machine_revenue": machine_revenue_total,
        "cash_sales": cash_sales_total,
        "cash_revenue": cash_revenue_total,
        "machine_usage_breakdown": list(machine_usage_map.values()),
        "product_revenue": product_revenue_total,
        "service_revenue": service_revenue_total,
        "product_breakdown": list(product_map.values()),
        "service_breakdown": list(service_map.values()),
        "gcash_job_order_count": gcash_job_order_count_total,
        "gcash_revenue": gcash_revenue_total,
        "expense_breakdown": list(expense_map.values()),
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "net_sales": net_sales,
        "total_transactions": total_transactions,
        "transaction_count": total_transactions,
        "job_order_count": job_order_count_total,
        "job_order_used_count": job_order_used_count_total,
        "job_order_open_count": job_order_open_count_total,
        "job_order_total_amount": job_order_total_amount_total,
        "job_order_promo_count": job_order_promo_count_total,
        "job_order_promo_breakdown": [{"name": name, "count": count} for name, count in promo_count_map.items()],
    }


def _build_recent_shifts_summary_receipt_data(limit_count=None):
    fallback_limit = get_recent_shift_summary_count()
    try:
        requested_count = int(limit_count if limit_count is not None else fallback_limit)
    except (TypeError, ValueError):
        requested_count = fallback_limit
    requested_count = max(1, min(requested_count, 30))

    conn = get_connection()

    active_row = conn.execute(
        """
        SELECT id
        FROM shift_sessions
        WHERE ended_at IS NULL
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()

    remaining_slots = requested_count - (1 if active_row else 0)
    if remaining_slots < 0:
        remaining_slots = 0

    completed_rows = []
    if remaining_slots > 0:
        completed_rows = conn.execute(
            """
            SELECT id
            FROM shift_sessions
            WHERE ended_at IS NOT NULL
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (remaining_slots,),
        ).fetchall()

    conn.close()

    shift_ids = []
    if active_row and active_row["id"]:
        shift_ids.append(active_row["id"])
    shift_ids.extend([row["id"] for row in completed_rows if row and row["id"]])

    return _build_shifts_summary_receipt_data_by_ids(
        shift_ids,
        requested_count=requested_count,
        custom_title=f"LAST {len(shift_ids)}"
    )


def _render_transaction_receipt_text(report):
    width = max(24, min(64, int(RECEIPT_TEXT_WIDTH)))
    divider = "-" * width
    config = get_receipt_format_config()
    top_spacing = int(config.get("top_spacing_lines", 3))
    lines = [""] * top_spacing
    lines.extend([
        _receipt_shop_name(config),
        divider,
        "TRANSACTION RECEIPT",
        divider,
    ])

    ordered_sections = _receipt_order(
        config,
        "transaction",
        [
            "transaction.header_section",
            "transaction.customer_section",
            "transaction.employee_section",
            "transaction.status_line",
            "transaction.payment_section",
            "transaction.items_section",
            "transaction.totals_section",
        ],
    )

    for section_key in ordered_sections:
        if not _receipt_enabled(config, section_key):
            continue

        if section_key == "transaction.header_section":
            lines.extend([
                _line("Txn ID", report.get("transaction_id") or "N/A", width),
                _line("Job Order", report.get("job_order_no") or "N/A", width),
                _line("Date", _split_receipt_date(report.get("report_date"))[0], width),
                _line("Machine", report.get("machine_id") or "N/A", width),
            ])
        elif section_key == "transaction.customer_section":
            lines.extend([
                _line("Customer ID", report.get("customer_id") or "N/A", width),
                _line("Customer", report.get("customer_name") or "N/A", width),
                _line("Phone", report.get("customer_phone") or "N/A", width),
            ])
        elif section_key == "transaction.employee_section":
            lines.extend([
                _line("Employee", report.get("employee_name") or "N/A", width),
                _line("Shift", report.get("shift_id") or "N/A", width),
            ])
        elif section_key == "transaction.status_line":
            lines.append(_line("Status", report.get("status") or "N/A", width))
        elif section_key == "transaction.payment_section":
            lines.extend([
                _line("Payment", report.get("payment_method") or "Cash", width),
                _line("Cash", _peso(report.get("cash_amount") or 0), width),
                _line("GCash", _peso(report.get("gcash_amount") or 0), width),
            ])
        elif section_key == "transaction.items_section":
            lines.extend([divider, "ITEMS"])
            items = report.get("items") or []
            if items:
                for item in items:
                    lines.append(_line(f"- {item['item_name']} x{int(item['quantity'] or 0)}", _peso(item.get("line_total")), width))
            else:
                lines.append(_line("- None", _peso(0), width))
        elif section_key == "transaction.totals_section":
            lines.extend(
                [
                    divider,
                    _line("Base Amount", _peso(report.get("base_amount")), width),
                    _line("Products", _peso(report.get("product_total")), width),
                    _line("Services", _peso(report.get("service_total")), width),
                    divider,
                    _line("TOTAL", _peso(report.get("total_amount")), width),
                ]
            )

    lines.append(divider)
    if _receipt_enabled(config, "common.generated_footer"):
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    bottom_spacing = int(config.get("bottom_spacing_lines", 6))
    lines.extend([""] * bottom_spacing)
    return "\n".join(lines)


def _render_recent_shifts_summary_receipt_text(report):
    # Shift summary should follow the same print structure/config as day summary.
    return _render_receipt_text(report)


def _build_bulk_transaction_receipt_data(transaction_ids):
    ids = []
    seen = set()
    for raw in transaction_ids or []:
        normalized = str(raw or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ids.append(normalized)

    if not ids:
        return None

    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    tx_rows = conn.execute(
        f"""
        SELECT id, machine_id, amount, status, started_at, employee_id,
               customer_id, customer_name, customer_phone, paid_by_gcash
        FROM transactions
        WHERE id IN ({placeholders})
        ORDER BY started_at ASC
        """,
        ids,
    ).fetchall()

    if not tx_rows:
        conn.close()
        return None

    tx_ids = [row["id"] for row in tx_rows]
    item_placeholders = ",".join("?" for _ in tx_ids)
    item_rows = conn.execute(
        f"""
        SELECT item_type, item_name, SUM(quantity) AS qty, SUM(line_total) AS total
        FROM transaction_items
        WHERE transaction_id IN ({item_placeholders})
        GROUP BY item_type, item_name
        ORDER BY item_type ASC, item_name ASC
        """,
        tx_ids,
    ).fetchall()

    employee_map = {}
    employee_ids = sorted({str(row["employee_id"] or "").strip() for row in tx_rows if row["employee_id"]})
    if employee_ids:
        emp_placeholders = ",".join("?" for _ in employee_ids)
        emp_rows = conn.execute(
            f"SELECT id, display_name FROM employees WHERE id IN ({emp_placeholders})",
            employee_ids,
        ).fetchall()
        employee_map = {row["id"]: row["display_name"] for row in emp_rows}

    conn.close()

    transactions = []
    total_amount = 0
    cash_count = 0
    gcash_count = 0
    customer_names = set()
    earliest = None
    latest = None
    employee_names = set()

    for row in tx_rows:
        started_at = row["started_at"]
        earliest = started_at if earliest is None or started_at < earliest else earliest
        latest = started_at if latest is None or started_at > latest else latest
        amount = int(row["amount"] or 0)
        total_amount += amount
        if int(row["paid_by_gcash"] or 0) == 1:
            gcash_count += 1
        else:
            cash_count += 1

        customer_name = str(row["customer_name"] or "").strip()
        if customer_name:
            customer_names.add(customer_name)

        emp_name = employee_map.get(row["employee_id"])
        if emp_name:
            employee_names.add(emp_name)

        transactions.append(
            {
                "id": row["id"],
                "machine_id": row["machine_id"],
                "amount": amount,
                "status": row["status"],
                "started_at": started_at,
                "paid_by_gcash": int(row["paid_by_gcash"] or 0),
                "customer_name": customer_name or "N/A",
            }
        )

    product_lines = []
    service_lines = []
    addons_total = 0
    for row in item_rows:
        line = {
            "name": row["item_name"],
            "qty": int(row["qty"] or 0),
            "total": int(row["total"] or 0),
        }
        addons_total += line["total"]
        if str(row["item_type"] or "") == "product":
            product_lines.append(line)
        else:
            service_lines.append(line)

    return {
        "shop_name": _receipt_shop_name(get_receipt_format_config()),
        "transaction_count": len(transactions),
        "transactions": transactions,
        "total_amount": total_amount,
        "addons_total": addons_total,
        "base_total": max(0, total_amount - addons_total),
        "cash_count": cash_count,
        "gcash_count": gcash_count,
        "earliest": earliest or "N/A",
        "latest": latest or "N/A",
        "employees": sorted(employee_names),
        "customers": sorted(customer_names),
        "product_lines": product_lines,
        "service_lines": service_lines,
    }


def _render_bulk_transaction_receipt_text(report):
    width = max(24, min(64, int(RECEIPT_TEXT_WIDTH)))
    divider = "-" * width
    config = get_receipt_format_config()

    employees = ", ".join(report.get("employees") or []) or "N/A"
    customers = ", ".join(report.get("customers") or []) or "N/A"

    top_spacing = int(config.get("top_spacing_lines", 3))
    lines = [""] * top_spacing
    lines.extend([
        _receipt_shop_name(config),
        divider,
        "BULK ACTIVATION RECEIPT",
    ])

    ordered_sections = _receipt_order(
        config,
        "bulk",
        [
            "bulk.header_section",
            "bulk.employee_customer_section",
            "bulk.machines_section",
            "bulk.addons_section",
            "bulk.payment_counts_section",
            "bulk.totals_section",
        ],
    )

    for section_key in ordered_sections:
        if not _receipt_enabled(config, section_key):
            continue

        if section_key == "bulk.header_section":
            lines.extend([
                divider,
                _line("Transactions", report.get("transaction_count") or 0, width),
                _line("Time Start", report.get("earliest") or "N/A", width),
                _line("Time End", report.get("latest") or "N/A", width),
            ])
        elif section_key == "bulk.employee_customer_section":
            lines.extend([
                _line("Employee", employees, width),
                _line("Customer", customers, width),
            ])
        elif section_key == "bulk.machines_section":
            lines.extend([divider, "MACHINES"])
            txns = report.get("transactions") or []
            if txns:
                for txn in txns:
                    payment = "GCash" if int(txn.get("paid_by_gcash") or 0) == 1 else "Cash"
                    lines.append(_line(f"- {txn.get('machine_id') or 'N/A'} [{payment}]", _peso(txn.get("amount")), width))
            else:
                lines.append(_line("- None", _peso(0), width))
        elif section_key == "bulk.addons_section":
            lines.extend([divider, "ADD-ONS"])
            product_lines = report.get("product_lines") or []
            service_lines = report.get("service_lines") or []
            addon_lines = product_lines + service_lines
            if addon_lines:
                for row in addon_lines:
                    lines.append(_line(f"- {row['name']} x{row['qty']}", _peso(row["total"]), width))
            else:
                lines.append(_line("- None", _peso(0), width))
        elif section_key == "bulk.payment_counts_section":
            lines.extend([
                divider,
                _line("Cash Txns", report.get("cash_count") or 0, width),
                _line("GCash Txns", report.get("gcash_count") or 0, width),
            ])
        elif section_key == "bulk.totals_section":
            lines.extend(
                [
                    divider,
                    _line("Base Total", _peso(report.get("base_total")), width),
                    _line("Add-ons", _peso(report.get("addons_total")), width),
                    divider,
                    _line("TOTAL", _peso(report.get("total_amount")), width),
                ]
            )

    lines.append(divider)
    if _receipt_enabled(config, "common.generated_footer"):
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    bottom_spacing = int(config.get("bottom_spacing_lines", 6))
    lines.extend([""] * bottom_spacing)
    return "\n".join(lines)


def _build_job_order_receipt_data(job_order_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, job_order_no,
               customer_id, customer_name, customer_phone,
               machine_id, machine_name, machine_type,
                         wash_qty, dry_qty, product_qty, service_qty,
                             paid_by_gcash, wash_unit_price, dry_unit_price, total_amount,
               status,
               created_by_employee_name,
               created_at, used_at
        FROM job_orders
        WHERE id = ?
        LIMIT 1
        """,
        (job_order_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None

    report = dict(row)
    report["shop_name"] = _receipt_shop_name(get_receipt_format_config())
    report["payment_method"] = "GCash" if int(report.get("paid_by_gcash") or 0) == 1 else "Cash"
    report["report_date"] = _format_receipt_date(report.get("created_at"))
    return report


def _render_job_order_receipt_text(report):
    width = max(24, min(64, int(RECEIPT_TEXT_WIDTH)))
    divider = "-" * width
    config = get_receipt_format_config()

    top_spacing = int(config.get("top_spacing_lines", 3))
    lines = [""] * top_spacing
    lines.extend([
        _receipt_shop_name(config),
        divider,
        "JOB ORDER RECEIPT",
    ])

    ordered_sections = _receipt_order(
        config,
        "job_order",
        [
            "job_order.header_section",
            "job_order.customer_section",
            "job_order.machine_section",
            "job_order.quantity_section",
            "job_order.payment_section",
            "job_order.unit_price_section",
            "job_order.total_section",
            "job_order.cashier_status_section",
        ],
    )

    for section_key in ordered_sections:
        if not _receipt_enabled(config, section_key):
            continue

        if section_key == "job_order.header_section":
            lines.extend([
                divider,
                _line("Job Order", report.get("job_order_no") or "N/A", width),
                _line("Date", _split_receipt_date(report.get("report_date") or report.get("created_at"))[0], width),
            ])
        elif section_key == "job_order.customer_section":
            lines.extend([
                _line("Customer ID", report.get("customer_id") or "N/A", width),
                _line("Customer", report.get("customer_name") or "N/A", width),
                _line("Phone", report.get("customer_phone") or "N/A", width),
            ])
        elif section_key == "job_order.machine_section":
            lines.extend([
                _line("Machine", report.get("machine_name") or report.get("machine_id") or "N/A", width),
                _line("Machine Type", report.get("machine_type") or "N/A", width),
            ])
        elif section_key == "job_order.quantity_section":
            lines.extend([
                divider,
                _line("Wash Qty", report.get("wash_qty") or 0, width),
                _line("Dry Qty", report.get("dry_qty") or 0, width),
                _line("Product Qty", report.get("product_qty") or 0, width),
                _line("Service Qty", report.get("service_qty") or 0, width),
            ])
        elif section_key == "job_order.payment_section":
            lines.append(_line("Payment", report.get("payment_method") or "Cash", width))
        elif section_key == "job_order.unit_price_section":
            lines.extend([
                _line("Wash Unit", _peso(report.get("wash_unit_price")), width),
                _line("Dry Unit", _peso(report.get("dry_unit_price")), width),
            ])
        elif section_key == "job_order.total_section":
            lines.extend([
                divider,
                _line("TOTAL", _peso(report.get("total_amount")), width),
            ])
        elif section_key == "job_order.cashier_status_section":
            lines.extend([
                _line("Cashier", report.get("created_by_employee_name") or "N/A", width),
                _line("Status", report.get("status") or "N/A", width),
            ])

    lines.append(divider)
    if _receipt_enabled(config, "common.generated_footer"):
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    bottom_spacing = int(config.get("bottom_spacing_lines", 6))
    lines.extend([""] * bottom_spacing)
    return "\n".join(lines)


def _build_bulk_job_order_receipt_data(job_order_ids):
    ids = []
    seen = set()
    for raw in job_order_ids or []:
        normalized = str(raw or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ids.append(normalized)

    if not ids:
        return None

    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT id, job_order_no,
               customer_id, customer_name, customer_phone,
               machine_name, machine_type,
               wash_qty, dry_qty, product_qty, service_qty,
               paid_by_gcash, total_amount,
               created_by_employee_name,
               created_at, status
        FROM job_orders
        WHERE id IN ({placeholders})
        ORDER BY created_at ASC
        """,
        ids,
    ).fetchall()
    conn.close()

    if not rows:
        return None

    orders = [dict(row) for row in rows]
    first = orders[0]

    return {
        "shop_name": _receipt_shop_name(get_receipt_format_config()),
        "job_order_count": len(orders),
        "customer_id": first.get("customer_id") or "N/A",
        "customer_name": first.get("customer_name") or "N/A",
        "customer_phone": first.get("customer_phone") or "N/A",
        "created_at": first.get("created_at") or "N/A",
        "report_date": _format_receipt_date(first.get("created_at")),
        "cashier": first.get("created_by_employee_name") or "N/A",
        "orders": orders,
        "total_wash_qty": sum(int(row.get("wash_qty") or 0) for row in orders),
        "total_dry_qty": sum(int(row.get("dry_qty") or 0) for row in orders),
        "total_product_qty": sum(int(row.get("product_qty") or 0) for row in orders),
        "total_service_qty": sum(int(row.get("service_qty") or 0) for row in orders),
        "total_amount": sum(int(row.get("total_amount") or 0) for row in orders),
    }


def _render_bulk_job_order_receipt_text(report):
    width = max(24, min(64, int(RECEIPT_TEXT_WIDTH)))
    divider = "-" * width
    config = get_receipt_format_config()

    top_spacing = int(config.get("top_spacing_lines", 3))
    lines = [""] * top_spacing
    lines.extend([
        _receipt_shop_name(config),
        divider,
        "JOB ORDER RECEIPT",
        divider,
        _line("Orders", report.get("job_order_count") or 0, width),
        _line("Date", report.get("report_date") or report.get("created_at") or "N/A", width),
        _line("Customer ID", report.get("customer_id") or "N/A", width),
        _line("Customer", report.get("customer_name") or "N/A", width),
        _line("Phone", report.get("customer_phone") or "N/A", width),
        _line("Cashier", report.get("cashier") or "N/A", width),
        divider,
        "ORDER LINES",
    ])

    for row in report.get("orders") or []:
        order_no = row.get("job_order_no") or row.get("id") or "N/A"
        machine_name = row.get("machine_name") or row.get("machine_type") or "N/A"
        status = str(row.get("status") or "OPEN").upper()
        payment = "GCash" if int(row.get("paid_by_gcash") or 0) == 1 else "Cash"

        lines.extend(
            [
                divider,
                _line("JO", order_no, width),
                _line("Machine", machine_name, width),
                _line("Mode", str(row.get("machine_type") or "N/A").title(), width),
                _line("Wash Qty", int(row.get("wash_qty") or 0), width),
                _line("Dry Qty", int(row.get("dry_qty") or 0), width),
                _line("Product Qty", int(row.get("product_qty") or 0), width),
                _line("Service Qty", int(row.get("service_qty") or 0), width),
                _line("Payment", payment, width),
                _line("Status", status, width),
                _line("Line Total", _peso(row.get("total_amount") or 0), width),
            ]
        )

    lines.extend(
        [
            divider,
            "SUMMARY",
            _line("Total Wash Qty", report.get("total_wash_qty") or 0, width),
            _line("Total Dry Qty", report.get("total_dry_qty") or 0, width),
            _line("Total Product Qty", report.get("total_product_qty") or 0, width),
            _line("Total Service Qty", report.get("total_service_qty") or 0, width),
            divider,
            _line("TOTAL", _peso(report.get("total_amount") or 0), width),
            divider,
        ]
    )

    if _receipt_enabled(config, "common.generated_footer"):
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    bottom_spacing = int(config.get("bottom_spacing_lines", 6))
    lines.extend([""] * bottom_spacing)
    return "\n".join(lines)


@reports_bp.route("/expenses/manual", methods=["POST"])
def add_manual_expense():
    data = request.get_json() or {}
    amount = data.get("amount")
    expense_name = str(data.get("expense_name") or "").strip()
    quantity_raw = data.get("quantity")
    quantity = None
    if amount is None:
        return jsonify({"error": "amount is required"}), 400

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400

    if amount <= 0:
        return jsonify({"error": "amount must be greater than zero"}), 400

    if quantity_raw not in (None, ""):
        try:
            quantity = int(quantity_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "quantity must be a whole number"}), 400
        if quantity <= 0:
            return jsonify({"error": "quantity must be greater than zero"}), 400

    note_parts = []
    if expense_name:
        if quantity:
            note_parts.append(f"{expense_name} x{quantity}")
        else:
            note_parts.append(expense_name)

    free_note = str(data.get("note") or "").strip()
    if free_note:
        note_parts.append(free_note)

    normalized_note = " - ".join(note_parts) if note_parts else None

    expense_id = create_manual_expense(
        amount=amount,
        note=normalized_note,
        expense_at=data.get("expense_at"),
        shift_id=data.get("shift_id"),
        employee_id=data.get("employee_id"),
    )
    return jsonify({
        "status": "ok",
        "expense_id": expense_id,
        "expense_name": expense_name or None,
        "quantity": quantity,
        "amount": amount,
    }), 201


@reports_bp.route("/expenses/manual", methods=["GET"])
def get_manual_expenses():
    day = request.args.get("date")
    shift_id = request.args.get("shift_id")
    return jsonify({"expenses": list_manual_expenses(date_str=day, shift_id=shift_id)})


@reports_bp.route("/expenses/manual/<expense_id>", methods=["PATCH", "PUT"])
def update_manual_expense_route(expense_id):
    guard = require_admin_pin()
    if guard:
        return guard

    data = request.get_json(silent=True) or {}

    try:
        updated = update_manual_expense(
            expense_id,
            amount=data.get("amount") if "amount" in data else None,
            note=data.get("note") if "note" in data else None,
            expense_at=data.get("expense_at") if "expense_at" in data else None,
            shift_id=data.get("shift_id") if "shift_id" in data else None,
            employee_id=data.get("employee_id") if "employee_id" in data else None,
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid expense update payload"}), 400

    if not updated:
        return jsonify({"error": "Expense not found"}), 404

    return jsonify({"status": "ok", "expense": updated})


@reports_bp.route("/reports/print-jobs", methods=["GET"])
def get_print_jobs():
    guard = require_admin_pin()
    if guard:
        return guard

    limit = request.args.get("limit", 100)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(limit, 500))
    return jsonify({"print_jobs": list_print_jobs(limit=limit)})


@reports_bp.route("/reports/shift/<shift_id>/receipt")
def print_shift_receipt(shift_id):
    payload = _build_shift_receipt_data(shift_id)
    if not payload:
        return jsonify({"error": "Shift not found"}), 404

    config = get_receipt_format_config()
    payload["top_spacing_lines"] = config.get("top_spacing_lines", 3)
    payload["bottom_spacing_lines"] = config.get("bottom_spacing_lines", 6)
    payload["top_padding_px"] = config.get("top_padding_px", 4)
    payload["bottom_padding_px"] = config.get("bottom_padding_px", 4)

    printed_by = request.args.get("printed_by")
    log_print_job("shift", shift_id, printed_by=printed_by)

    receipt_text = _render_receipt_text(payload)
    return render_template("receipt_print.html", report=payload, receipt_text=receipt_text)


@reports_bp.route("/reports/day/<day_str>/receipt")
def print_day_receipt(day_str):
    try:
        datetime.strptime(day_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format; use YYYY-MM-DD"}), 400

    payload = _build_day_receipt_data(day_str)
    config = get_receipt_format_config()
    payload["top_spacing_lines"] = config.get("top_spacing_lines", 3)
    payload["bottom_spacing_lines"] = config.get("bottom_spacing_lines", 6)
    payload["top_padding_px"] = config.get("top_padding_px", 4)
    payload["bottom_padding_px"] = config.get("bottom_padding_px", 4)

    printed_by = request.args.get("printed_by")
    log_print_job("day", day_str, printed_by=printed_by)

    receipt_text = _render_receipt_text(payload)
    return render_template("receipt_print.html", report=payload, receipt_text=receipt_text)


@reports_bp.route("/reports/shifts/recent/receipt")
def preview_recent_shifts_summary_receipt():
    count = request.args.get("count")

    payload = _build_recent_shifts_summary_receipt_data(count)
    if not payload:
        return jsonify({"error": "No completed shifts found for summary receipt"}), 404

    config = get_receipt_format_config()
    payload["top_spacing_lines"] = config.get("top_spacing_lines", 3)
    payload["bottom_spacing_lines"] = config.get("bottom_spacing_lines", 6)
    payload["top_padding_px"] = config.get("top_padding_px", 4)
    payload["bottom_padding_px"] = config.get("bottom_padding_px", 4)

    receipt_text = _render_recent_shifts_summary_receipt_text(payload)
    return render_template(
        "receipt_print.html",
        report=payload,
        receipt_text=receipt_text,
    )


@reports_bp.route("/reports/transaction/<transaction_id>/print", methods=["POST"])
def print_transaction_receipt_direct(transaction_id):
    payload = _build_transaction_receipt_data(transaction_id)
    if not payload:
        return jsonify({"error": "Transaction not found"}), 404

    data = request.get_json(silent=True) or {}
    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    log_print_job("transaction", transaction_id, printed_by=printed_by)

    try:
        result = _send_to_cups(
            _render_transaction_receipt_text(payload),
            title=f"LaundryLink Txn {transaction_id[:8]}",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "transaction",
            "reference_id": transaction_id,
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/transactions/bulk/print", methods=["POST"])
def print_bulk_transaction_receipt_direct():
    data = request.get_json(silent=True) or {}
    transaction_ids = data.get("transaction_ids") if isinstance(data.get("transaction_ids"), list) else []

    payload = _build_bulk_transaction_receipt_data(transaction_ids)
    if not payload:
        return jsonify({"error": "No transactions found for bulk receipt"}), 404

    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    ref_ids = [str(tx.get("id") or "").strip() for tx in payload.get("transactions") or []]
    log_print_job("bulk_transaction", ",".join(ref_ids[:20]), printed_by=printed_by)

    try:
        result = _send_to_cups(
            _render_bulk_transaction_receipt_text(payload),
            title=f"LaundryLink Bulk {payload.get('transaction_count') or 0} Txns",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "bulk_transaction",
            "transaction_count": payload.get("transaction_count") or 0,
            "total_amount": payload.get("total_amount") or 0,
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/job-order/<job_order_id>/print", methods=["POST"])
def print_job_order_receipt_direct(job_order_id):
    payload = _build_job_order_receipt_data(job_order_id)
    if not payload:
        return jsonify({"error": "Job order not found"}), 404

    data = request.get_json(silent=True) or {}
    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    log_print_job("job_order", job_order_id, printed_by=printed_by)

    try:
        result = _send_to_cups(
            _render_job_order_receipt_text(payload),
            title=f"LaundryLink Job Order {str(payload.get('job_order_no') or job_order_id)[:16]}",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "job_order",
            "reference_id": job_order_id,
            "job_order_no": payload.get("job_order_no"),
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/job-orders/bulk/print", methods=["POST"])
def print_bulk_job_order_receipt_direct():
    data = request.get_json(silent=True) or {}
    job_order_ids = data.get("job_order_ids") if isinstance(data.get("job_order_ids"), list) else []

    payload = _build_bulk_job_order_receipt_data(job_order_ids)
    if not payload:
        return jsonify({"error": "No job orders found for combined receipt"}), 404

    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    ref_ids = [str(row.get("id") or "").strip() for row in payload.get("orders") or []]
    log_print_job("bulk_job_order", ",".join(ref_ids[:20]), printed_by=printed_by)

    try:
        result = _send_to_cups(
            _render_bulk_job_order_receipt_text(payload),
            title=f"LaundryLink Job Orders {payload.get('job_order_count') or 0}",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "bulk_job_order",
            "job_order_count": payload.get("job_order_count") or 0,
            "total_amount": payload.get("total_amount") or 0,
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/shifts/recent/print", methods=["POST"])
def print_recent_shifts_summary_direct():
    data = request.get_json(silent=True) or {}
    count = data.get("count") if "count" in data else request.args.get("count")

    payload = _build_recent_shifts_summary_receipt_data(count)
    if not payload:
        return jsonify({"error": "No completed shifts found for summary receipt"}), 404

    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    log_print_job(
        "recent_shifts_summary",
        str(payload.get("requested_count") or payload.get("actual_count") or "0"),
        printed_by=printed_by,
    )

    try:
        result = _send_to_cups(
            _render_recent_shifts_summary_receipt_text(payload),
            title=f"LaundryLink Last {payload.get('actual_count') or 0} Shifts",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "recent_shifts_summary",
            "requested_count": payload.get("requested_count") or 0,
            "actual_count": payload.get("actual_count") or 0,
            "total_sales": payload.get("total_sales") or 0,
            "total_expenses": payload.get("total_expenses") or 0,
            "net_sales": payload.get("net_sales") or 0,
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/shifts/summary/print", methods=["POST"])
def print_shifts_summary_direct():
    data = request.get_json(silent=True) or {}
    shift_ids = data.get("shift_ids") if isinstance(data.get("shift_ids"), list) else []
    if not shift_ids:
        return jsonify({"error": "No shift IDs specified"}), 400

    payload = _build_shifts_summary_receipt_data_by_ids(
        shift_ids,
        custom_title=f"SELECTED {len(shift_ids)}"
    )
    if not payload:
        return jsonify({"error": "No shifts found for selected IDs"}), 404

    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    log_print_job(
        "recent_shifts_summary",
        f"selected:{len(shift_ids)}",
        printed_by=printed_by,
    )

    try:
        result = _send_to_cups(
            _render_recent_shifts_summary_receipt_text(payload),
            title=f"LaundryLink Summary {payload.get('actual_count') or 0} Shifts",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "recent_shifts_summary",
            "actual_count": payload.get("actual_count") or 0,
            "total_sales": payload.get("total_sales") or 0,
            "total_expenses": payload.get("total_expenses") or 0,
            "net_sales": payload.get("net_sales") or 0,
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/shifts/summary/preview", methods=["GET"])
def preview_shifts_summary_receipt():
    shift_ids_str = request.args.get("shift_ids") or ""
    shift_ids = [s.strip() for s in shift_ids_str.split(",") if s.strip()]
    if not shift_ids:
        return jsonify({"error": "No shift IDs specified"}), 400

    payload = _build_shifts_summary_receipt_data_by_ids(
        shift_ids,
        custom_title=f"SELECTED {len(shift_ids)}"
    )
    if not payload:
        return jsonify({"error": "No shifts found for selected IDs"}), 404

    config = get_receipt_format_config()
    payload["top_spacing_lines"] = config.get("top_spacing_lines", 3)
    payload["bottom_spacing_lines"] = config.get("bottom_spacing_lines", 6)
    payload["top_padding_px"] = config.get("top_padding_px", 4)
    payload["bottom_padding_px"] = config.get("bottom_padding_px", 4)

    receipt_text = _render_recent_shifts_summary_receipt_text(payload)
    return render_template(
        "receipt_print.html",
        report=payload,
        receipt_text=receipt_text,
    )


@reports_bp.route("/reports/printers", methods=["GET"])
def list_printers():
    printers = _discover_cups_printers()
    return jsonify(
        {
            "printers": printers,
            "default": _get_default_printer_name(),
        }
    )


@reports_bp.route("/reports/shift/<shift_id>/print", methods=["POST"])
def print_shift_receipt_direct(shift_id):
    payload = _build_shift_receipt_data(shift_id)
    if not payload:
        return jsonify({"error": "Shift not found"}), 404

    data = request.get_json(silent=True) or {}
    overrides = data.get("overrides") if isinstance(data, dict) else None
    if overrides:
        guard = require_admin_pin()
        if guard:
            return guard
        payload = _apply_receipt_overrides(payload, overrides)

    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    log_print_job("shift", shift_id, printed_by=printed_by)

    try:
        result = _send_to_cups(
            _render_receipt_text(payload),
            title=f"LaundryLink Shift {shift_id}",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "shift",
            "reference_id": shift_id,
            "printer": result["printer"],
            "job": result["job"],
        }
    )


@reports_bp.route("/reports/day/<day_str>/print", methods=["POST"])
def print_day_receipt_direct(day_str):
    try:
        datetime.strptime(day_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format; use YYYY-MM-DD"}), 400

    payload = _build_day_receipt_data(day_str)
    data = request.get_json(silent=True) or {}
    overrides = data.get("overrides") if isinstance(data, dict) else None
    if overrides:
        guard = require_admin_pin()
        if guard:
            return guard
        payload = _apply_receipt_overrides(payload, overrides)

    printed_by = data.get("printed_by") or request.args.get("printed_by")
    printer_name = data.get("printer") or request.args.get("printer")
    copies = data.get("copies") or request.args.get("copies") or 1

    log_print_job("day", day_str, printed_by=printed_by)

    try:
        result = _send_to_cups(
            _render_receipt_text(payload),
            title=f"LaundryLink Day {day_str}",
            printer_name=printer_name,
            copies=copies,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "report_type": "day",
            "reference_id": day_str,
            "printer": result["printer"],
            "job": result["job"],
        }
    )
