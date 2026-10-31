import os
import logging

import streamlit as st
import mysql.connector

from dotenv import load_dotenv
from src.config.settings_manager import (
    get_all_settings,
    save_all_settings
)

# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Data Quality Firewall — Settings",
    page_icon="⚙️",
    layout="wide"
)

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================
# 2. CUSTOM STYLING
# ============================================================

st.markdown("""
<style>
    .stApp {
        background-color: #0E1117;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1600px;
    }

    .section-label {
        color: #8B95A5;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        margin-bottom: 8px;
    }

    div[data-testid="stMetric"] {
        background: #171B24;
        border: 1px solid #292F3B;
        padding: 17px;
        border-radius: 12px;
        min-height: 110px;
    }

    div[data-testid="stMetricLabel"] {
        color: #A0A9B8;
        font-size: 0.85rem;
    }

    div[data-testid="stMetricValue"] {
        color: #F3F4F6;
        font-weight: 700;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #292F3B;
        border-radius: 10px;
        overflow: hidden;
    }

    hr {
        border-color: #292F3B;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 3. DATABASE CONNECTION
# ============================================================

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


# ============================================================
# 4. LOAD PERSISTENT SETTINGS
# ============================================================

conn = None

try:
    conn = get_db_connection()
    settings = get_all_settings(conn)
except Exception as e:
    logger.exception("Failed to load persistent system settings.")
    st.error(f"Unable to load system settings: {e}")
    st.stop()
finally:
    if conn and conn.is_connected():
        conn.close()


# ============================================================
# 5. PAGE HEADER
# ============================================================

st.title("⚙️ System Configuration")
st.caption(
    "Manage persistent notification preferences "
    "and monitoring behaviour."
)
st.divider()


# ============================================================
# 6. CONFIGURATION OVERVIEW
# ============================================================

st.markdown('<div class="section-label">System Overview</div>', unsafe_allow_html=True)

overview_col1, overview_col2, overview_col3 = st.columns(3)

with overview_col1:
    st.metric(
        "Storage Engine",
        "TiDB Database",
        help="Settings are saved directly to system_settings table."
    )

with overview_col2:
    st.metric(
        "Email Alert Status",
        "Active" if settings["email_alerts_enabled"] else "Inactive"
    )

with overview_col3:
    st.metric(
        "Alert Severity",
        settings["minimum_alert_severity"]
    )

st.divider()


# ============================================================
# 7. NOTIFICATION SETTINGS FORM
# ============================================================

st.markdown('<div class="section-label">01 / Configuration Form</div>', unsafe_allow_html=True)

with st.form("system_settings_form"):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### ✉️ Email Notifications")
        email_alerts = st.checkbox(
            "Enable Email Notifications",
            value=bool(settings["email_alerts_enabled"])
        )
        alert_email = st.text_input(
            "Alert Recipient Email",
            value=settings["alert_recipient_email"],
            placeholder="alerts@company.com"
        )

    with col2:
        st.markdown("#### 💬 Slack Notifications")
        slack_alerts = st.checkbox(
            "Enable Slack Notifications",
            value=bool(settings["slack_alerts_enabled"])
        )
        st.info(
            "Slack webhook credentials are configured "
            "separately through environment secrets."
        )

    st.divider()

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("#### 🚨 Alert Threshold")
        min_severity = st.selectbox(
            "Minimum Alert Severity",
            ["CRITICAL", "WARNING", "INFO"],
            index=["CRITICAL", "WARNING", "INFO"].index(settings["minimum_alert_severity"])
        )

    with col4:
        st.markdown("#### ⚡ Incident Behaviour")
        auto_resolve = st.checkbox(
            "Auto-resolve incidents when checks pass",
            value=bool(settings["auto_resolve_incidents"])
        )

    submitted = st.form_submit_button(
        "Save System Settings",
        type="primary",
        use_container_width=True
    )

    if submitted:
        valid_input = True

        if email_alerts:
            if not alert_email.strip():
                st.error("An email address is required when email alerts are enabled.")
                valid_input = False
            elif "@" not in alert_email or "." not in alert_email.split("@")[-1]:
                st.error("Enter a valid recipient email address.")
                valid_input = False

        if valid_input:
            new_settings = {
                "email_alerts_enabled": email_alerts,
                "alert_recipient_email": alert_email.strip(),
                "minimum_alert_severity": min_severity,
                "slack_alerts_enabled": slack_alerts,
                "auto_resolve_incidents": auto_resolve
            }

            conn = None
            try:
                conn = get_db_connection()
                save_all_settings(conn, new_settings)
                st.success("System settings successfully saved to TiDB.")
                st.rerun()
            except Exception as e:
                logger.exception("Failed to save updated settings.")
                st.error(f"Failed to save settings: {e}")
            finally:
                if conn and conn.is_connected():
                    conn.close()


# ============================================================
# 8. DATABASE CONNECTION DIAGNOSTICS
# ============================================================

st.divider()
st.markdown('<div class="section-label">02 / Infrastructure</div>', unsafe_allow_html=True)

st.subheader("🔌 Database Connection Diagnostics")

if st.button("Test Database Connection"):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                VERSION() AS version,
                DATABASE() AS current_db,
                NOW() AS server_time
        """)
        db_info = cursor.fetchone()
        cursor.close()

        st.success("Database connection successful.")

        diag_col1, diag_col2, diag_col3 = st.columns(3)
        diag_col1.metric("Connected Database", db_info["current_db"])
        diag_col2.metric("Database Version", str(db_info["version"])[:20])
        diag_col3.metric("Server Time", str(db_info["server_time"]))

    except Exception as e:
        logger.exception("Settings diagnostic check failed.")
        st.error(f"Database diagnostic failed: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================
# 9. CURRENT CONFIGURATION STATUS
# ============================================================

st.divider()
st.markdown('<div class="section-label">03 / Active Settings State</div>', unsafe_allow_html=True)

status_col1, status_col2 = st.columns(2)

with status_col1:
    st.write(
        "**Email Notifications:**",
        "Enabled" if settings["email_alerts_enabled"] else "Disabled"
    )
    if settings["email_alerts_enabled"]:
        st.write("**Recipient Email:**", f"`{settings['alert_recipient_email']}`")

    st.write(
        "**Slack Notifications:**",
        "Enabled" if settings["slack_alerts_enabled"] else "Disabled"
    )

with status_col2:
    st.write(
        "**Minimum Severity:**",
        f"`{settings['minimum_alert_severity']}`"
    )
    st.write(
        "**Auto Resolution:**",
        "Enabled" if settings["auto_resolve_incidents"] else "Disabled"
    )

st.divider()
st.caption("DATA QUALITY FIREWALL · PERSISTENT SYSTEM CONFIGURATION")