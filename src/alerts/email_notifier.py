import os
import html
import logging
import smtplib
import mysql.connector

from email.message import EmailMessage
from dotenv import load_dotenv

from src.config.settings_manager import get_all_settings

load_dotenv()
logger = logging.getLogger(__name__)


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_db_connection():
    required = [
        "MYSQL_HOST",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE"
    ]

    missing = [key for key in required if not os.getenv(key)]

    if missing:
        raise ValueError(
            f"Missing database environment variables: {', '.join(missing)}"
        )

    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        port=int(os.getenv("MYSQL_PORT", 4000)),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
        ssl_disabled=False,
        connection_timeout=10
    )


# --------------------------------------------------
# LOAD NOTIFICATION SETTINGS
# --------------------------------------------------

def get_notification_settings():
    conn = None
    try:
        conn = get_db_connection()
        return get_all_settings(conn)
    finally:
        if conn and conn.is_connected():
            conn.close()


# --------------------------------------------------
# SEVERITY FILTER
# --------------------------------------------------

SEVERITY_LEVELS = {
    "INFO": 1,
    "WARNING": 2,
    "CRITICAL": 3
}


def should_send_alert(severity: str, minimum_severity: str) -> bool:
    severity = str(severity).upper()
    minimum_severity = str(minimum_severity).upper()

    if severity not in SEVERITY_LEVELS:
        logger.warning(
            "Unknown incident severity '%s'. Notification suppressed.",
            severity
        )
        return False

    if minimum_severity not in SEVERITY_LEVELS:
        logger.error(
            "Invalid minimum alert severity '%s'. Notification suppressed.",
            minimum_severity
        )
        return False

    return SEVERITY_LEVELS[severity] >= SEVERITY_LEVELS[minimum_severity]


# --------------------------------------------------
# SEND INCIDENT ALERT
# --------------------------------------------------

def send_incident_alert(
    table_name: str,
    check_type: str,
    observed_value: str,
    expected_value: str,
    message: str,
    severity: str = "CRITICAL",
    incident_status: str = "OPEN",
    settings: dict = None
) -> bool:
    """
    Send an incident notification through SMTP.
    Notification preferences are loaded dynamically from TiDB.

    Returns:
        True: SMTP server accepted the message.
        False: Notification was disabled, filtered, misconfigured, or failed.
    """

        # Load settings only if the caller did not provide them.
    try:
        if settings is None:
            settings = get_notification_settings()

    except Exception:
        logger.exception(
            "Unable to load notification settings. "
            "Email dispatch suppressed."
        )
        return False

    if not settings.get("email_alerts_enabled", True):
        logger.info("Email notifications are disabled.")
        return False

    # Apply severity filtering to new incident alerts.
    # Recovery notifications should not be suppressed by this filter.
    if incident_status != "RESOLVED":
        minimum_severity = settings.get(
            "minimum_alert_severity", "CRITICAL"
        )

        if not should_send_alert(severity, minimum_severity):
            logger.info(
                "Alert suppressed by severity threshold: %s",
                severity
            )
            return False

    # 4. Load SMTP Configuration
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    recipient_email = (
        settings.get("alert_recipient_email")
        or os.getenv("ALERT_RECIPIENT_EMAIL")
    )

    if not all([smtp_server, smtp_user, smtp_password, recipient_email]):
        logger.warning("SMTP configuration incomplete. Alert not dispatched.")
        return False

    # 5. Escape Untrusted HTML Values & Preserve Line Breaks
    safe_table = html.escape(str(table_name))
    safe_check = html.escape(str(check_type))
    safe_observed = html.escape(str(observed_value))
    safe_expected = html.escape(str(expected_value))
    safe_message = html.escape(str(message)).replace("\n", "<br>")
    safe_severity = html.escape(str(severity))
    safe_status = html.escape(str(incident_status))

    subject = (
        f"[{severity}] Data Quality Firewall | "
        f"{table_name} | {check_type}"
    )

    # 6. Plain Text Payload
    plain_text = f"""DATA QUALITY FIREWALL INCIDENT

Status: {incident_status}
Severity: {severity}
Table: {table_name}
Check: {check_type}

Observed: {observed_value}
Expected: {expected_value}

Details:
{message}
"""

    # 7. HTML Payload
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #202124;">
        <div style="
            max-width: 600px;
            margin: auto;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
        ">
            <div style="background: #172554; color: white; padding: 22px;">
                <h2 style="margin: 0;">Data Quality Firewall</h2>
                <p style="margin-bottom: 0;">Data integrity notification</p>
            </div>

            <div style="padding: 24px;">
                <h3 style="color: #b91c1c;">
                    {safe_severity} — {safe_status}
                </h3>

                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            <strong>Dataset</strong>
                        </td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            {safe_table}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            <strong>Check</strong>
                        </td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            {safe_check}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            <strong>Observed</strong>
                        </td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            {safe_observed}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            <strong>Expected</strong>
                        </td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            {safe_expected}
                        </td>
                    </tr>
                </table>

                <div style="
                    margin-top: 20px;
                    padding: 15px;
                    background: #fef2f2;
                    border-left: 4px solid #dc2626;
                ">
                    <strong>Incident details</strong>
                    <p style="margin-bottom: 0;">{safe_message}</p>
                </div>

                <p style="margin-top: 25px; color: #6b7280; font-size: 12px;">
                    Automated notification from Data Quality Firewall.
                    Please investigate the affected data pipeline.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    # 8. Build Message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient_email

    msg.set_content(plain_text)
    msg.add_alternative(html_content, subtype="html")

    # 9. Dispatch Email
    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        logger.info(
            "Incident notification accepted by SMTP server. Table=%s Check=%s Severity=%s",
            table_name,
            check_type,
            severity
        )
        return True

    except Exception:
        logger.exception("Incident notification dispatch failed.")
        return False