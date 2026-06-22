import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import threading
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from flask import render_template

from database import get_email_settings, get_day_change_time, list_low_stock_products
from routes.reports import _build_day_receipt_data

email_scheduler = BackgroundScheduler(daemon=True)

# We need the Flask app context to render templates
_app = None


def init_email_scheduler(app):
    global _app
    _app = app
    refresh_email_schedule()


def refresh_email_schedule():
    """Reads settings from DB and schedules/reschedules the email job."""
    settings = get_email_settings()

    if email_scheduler.get_job("automated_email_job"):
        email_scheduler.remove_job("automated_email_job")

    if not settings.get("enabled"):
        return

    time_str = settings.get("time", "08:00")
    try:
        hour, minute = map(int, time_str.split(":"))
    except ValueError:
        hour, minute = 8, 0

    freq = settings.get("frequency", "daily")

    if freq in ("daily", "daily_current"):
        email_scheduler.add_job(
            send_automated_report,
            "cron",
            hour=hour,
            minute=minute,
            id="automated_email_job",
            replace_existing=True,
        )
    elif freq == "weekly":
        # Send every Monday
        email_scheduler.add_job(
            send_automated_report,
            "cron",
            day_of_week="mon",
            hour=hour,
            minute=minute,
            id="automated_email_job",
            replace_existing=True,
        )
    elif freq == "monthly":
        # Send on the 1st of every month
        email_scheduler.add_job(
            send_automated_report,
            "cron",
            day=1,
            hour=hour,
            minute=minute,
            id="automated_email_job",
            replace_existing=True,
        )

    if not email_scheduler.running:
        email_scheduler.start()
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Email scheduler started ({freq} at {time_str})"
        )
    else:
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Email scheduler rescheduled ({freq} at {time_str})"
        )


# ---------------------------------------------------------------------------
# Report aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate_days(day_list):
    """
    Given a list of YYYY-MM-DD strings, fetch each day's receipt data and
    sum all numeric fields.  Returns a merged dict ready for the template.
    """
    accumulated = None
    for day_str in day_list:
        try:
            day_data = _build_day_receipt_data(day_str)
        except Exception:
            continue

        if accumulated is None:
            accumulated = dict(day_data)
            continue

        numeric_keys = [
            "gross_collected", "total_sales", "machine_revenue",
            "cash_sales", "cash_revenue", "product_revenue",
            "service_revenue", "manual_expenses", "cogs_total",
            "total_expenses", "net_sales", "transaction_count",
            "gcash_revenue", "gcash_job_order_count",
            "post_cycle_transfer_amount", "post_cycle_transfer_count",
            "job_order_count", "job_order_used_count", "job_order_open_count",
            "job_order_total_amount", "products_used", "services_used",
            "job_order_promo_count",
        ]
        for k in numeric_keys:
            accumulated[k] = int(accumulated.get(k) or 0) + int(day_data.get(k) or 0)

        # Aggregate machine_usage_breakdown
        day_mub = day_data.get("machine_usage_breakdown") or []
        acc_mub = accumulated.get("machine_usage_breakdown") or []
        mub_map = {row["machine_type"]: dict(row) for row in acc_mub}
        for row in day_mub:
            m_type = row["machine_type"]
            if m_type in mub_map:
                mub_map[m_type]["count"] = int(mub_map[m_type].get("count") or 0) + int(row.get("count") or 0)
                mub_map[m_type]["revenue"] = int(mub_map[m_type].get("revenue") or 0) + int(row.get("revenue") or 0)
            else:
                mub_map[m_type] = dict(row)

        def _type_rank(machine_type):
            if machine_type == "washer":
                return 0
            if machine_type == "dryer":
                return 1
            return 2

        accumulated["machine_usage_breakdown"] = sorted(
            mub_map.values(),
            key=lambda row: (_type_rank(row.get("machine_type")), str(row.get("machine_type_label") or "").lower())
        )

        # Aggregate job_order_promo_breakdown
        day_pbd = day_data.get("job_order_promo_breakdown") or []
        acc_pbd = accumulated.get("job_order_promo_breakdown") or []
        pbd_map = {row["name"]: dict(row) for row in acc_pbd}
        for row in day_pbd:
            name = row["name"]
            if name in pbd_map:
                pbd_map[name]["count"] = int(pbd_map[name].get("count") or 0) + int(row.get("count") or 0)
            else:
                pbd_map[name] = dict(row)

        accumulated["job_order_promo_breakdown"] = sorted(
            pbd_map.values(),
            key=lambda row: str(row.get("name")).lower()
        )

    return accumulated


def _build_weekly_report():
    """Aggregate the previous 7 operational days."""
    today = datetime.now().date()
    days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 8)]
    days.reverse()  # chronological order
    return _aggregate_days(days), days[0], days[-1]


def _build_monthly_report():
    """Aggregate the previous 30 operational days."""
    today = datetime.now().date()
    days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 31)]
    days.reverse()
    return _aggregate_days(days), days[0], days[-1]


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------

def send_automated_report():
    """Gathers data and sends the email using smtplib."""
    settings = get_email_settings()

    if not settings.get("enabled"):
        return

    smtp_email = settings.get("smtp_email")
    smtp_password = settings.get("smtp_password")
    recipients_raw = settings.get("recipients", "")

    if not smtp_email or not smtp_password or not recipients_raw:
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            "Cannot send automated report: missing SMTP config or recipients."
        )
        return

    recipients = [e.strip() for e in recipients_raw.split(",") if e.strip()]
    if not recipients:
        return

    freq = settings.get("frequency", "daily")

    # Per-section include flags passed to the template
    include_flags = {
        "include_revenue_breakdown": settings.get("include_revenue_breakdown", True),
        "include_payment_methods": settings.get("include_payment_methods", True),
        "include_expenses": settings.get("include_expenses", True),
        "include_operational_stats": settings.get("include_operational_stats", True),
        "include_machine_usage": settings.get("include_machine_usage", True),
        "include_low_stock_alerts": settings.get("include_low_stock_alerts", True),
    }

    low_stock_products = []
    if include_flags["include_low_stock_alerts"]:
        low_stock_products = list_low_stock_products()

    with _app.app_context():
        try:
            today = datetime.now()

            if freq == "daily":
                target_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                report_data = _build_day_receipt_data(target_date)
                title = f"Daily Analytics Report — {target_date}"
                period_label = target_date
                subject = f"LaundryLink Daily Report: {target_date}"

            elif freq == "daily_current":
                target_date = today.strftime("%Y-%m-%d")
                report_data = _build_day_receipt_data(target_date)
                title = f"Daily Analytics Report (Current Day) — {target_date}"
                period_label = target_date
                subject = f"LaundryLink Daily Report: {target_date}"

            elif freq == "weekly":
                report_data, start_date, end_date = _build_weekly_report()
                title = f"Weekly Analytics Report — {start_date} to {end_date}"
                period_label = f"{start_date} to {end_date}"
                subject = f"LaundryLink Weekly Report: {start_date} to {end_date}"

            elif freq == "monthly":
                report_data, start_date, end_date = _build_monthly_report()
                title = f"Monthly Analytics Report — {start_date} to {end_date}"
                period_label = f"{start_date} to {end_date}"
                subject = f"LaundryLink Monthly Report: {start_date} to {end_date}"

            else:
                target_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                report_data = _build_day_receipt_data(target_date)
                title = f"Analytics Report — {target_date}"
                period_label = target_date
                subject = f"LaundryLink Report: {target_date}"

            if not report_data:
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    "No report data available; skipping email."
                )
                return

            html_content = render_template(
                "email_report.html",
                report=report_data,
                title=title,
                frequency=freq,
                period_label=period_label,
                include_flags=include_flags,
                low_stock_products=low_stock_products,
            )

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"LaundryLink <{smtp_email}>"
            msg["To"] = ", ".join(recipients)
            msg.set_content(
                f"Please view this email in an HTML compatible client.\n"
                f"This is the LaundryLink {freq} analytics report for {period_label}."
            )
            msg.add_alternative(html_content, subtype="html")

            smtp_host = "smtp.gmail.com"
            smtp_port = 587

            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
            server.quit()

            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Automated {freq} email sent to {len(recipients)} recipient(s)."
            )

        except Exception as e:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Error sending automated email: {e}"
            )
            traceback.print_exc()


def trigger_test_email():
    """Triggers an email send immediately for testing purposes."""
    thread = threading.Thread(target=send_automated_report)
    thread.daemon = True
    thread.start()
