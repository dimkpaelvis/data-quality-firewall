import os
import logging

import streamlit as st
import pandas as pd
import mysql.connector

from dotenv import load_dotenv
from datetime import datetime


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Data Quality Firewall — Overview",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================
# 2. GLOBAL STYLING
# ============================================================

st.markdown("""
<style>
    /* Main application background */
    .stApp {
        background-color: #0E1117;
    }

    /* Main content spacing */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1600px;
    }

    /* Main headings */
    h1, h2, h3 {
        letter-spacing: -0.5px;
    }

    /* KPI cards */
    div[data-testid="stMetric"] {
        background-color: #171B24;
        border: 1px solid #292F3B;
        padding: 20px 20px;
        border-radius: 12px;
        min-height: 125px;
    }

    div[data-testid="stMetricLabel"] {
        color: #A0A9B8;
        font-size: 13px;
        font-weight: 500;
    }

    div[data-testid="stMetricValue"] {
        color: #F3F4F6;
        font-weight: 700;
    }

    div[data-testid="stMetricDelta"] {
        font-size: 12px;
    }

    /* Section spacing */
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.8rem;
    }

    /* Dataframes */
    div[data-testid="stDataFrame"] {
        border: 1px solid #292F3B;
        border-radius: 10px;
        overflow: hidden;
    }

    /* Dividers */
    hr {
        border-color: #292F3B;
    }

    /* Dashboard information panels */
    .info-panel {
        background: #171B24;
        border: 1px solid #292F3B;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 10px;
    }

    .panel-label {
        color: #A0A9B8;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    .panel-description {
        color: #929BAA;
        font-size: 12px;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 3. DATABASE CONNECTION
# ============================================================

def get_db_connection():
    required_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        raise ValueError(f"Missing database configuration: {', '.join(missing_vars)}")

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
# 4. PAGE HEADER
# ============================================================

st.title("🛡️ Data Quality Firewall")
st.caption(
    "Central monitoring and data integrity intelligence "
    "for your connected data pipelines."
)

header_col1, header_col2 = st.columns([5, 1])
with header_col2:
    st.markdown(
        """
        <div style="
            text-align:right;
            color:#929BAA;
            font-size:12px;
            padding-top:12px;
        ">
            ● MONITORING ACTIVE
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()


# ============================================================
# 5. LIVE OVERVIEW DASHBOARD
# ============================================================

@st.fragment(run_every=30)
def render_live_overview():
    conn = None

    try:
        conn = get_db_connection()

        # ----------------------------------------------------
        # A. FETCH CORE METRICS
        # ----------------------------------------------------
        incident_df = pd.read_sql(
            "SELECT COUNT(*) AS incident_count FROM incidents WHERE status IN ('OPEN', 'ACKNOWLEDGED');",
            conn
        )
        unresolved_count = int(incident_df["incident_count"].iloc[0])

        assets_df = pd.read_sql(
            "SELECT COUNT(*) AS asset_count FROM monitored_assets WHERE is_active = TRUE;",
            conn
        )
        asset_count = int(assets_df["asset_count"].iloc[0])

        rules_df = pd.read_sql(
            "SELECT COUNT(*) AS rule_count FROM quality_checks WHERE is_enabled = TRUE;",
            conn
        )
        active_rules = int(rules_df["rule_count"].iloc[0])

        # ----------------------------------------------------
        # B. FETCH LAST 100 AUDIT RESULTS
        # ----------------------------------------------------
        recent_metrics_df = pd.read_sql(
            "SELECT status, started_at FROM check_results ORDER BY result_id DESC LIMIT 100;",
            conn
        )

        total_checks = len(recent_metrics_df)

        if total_checks > 0:
            passed_checks = int((recent_metrics_df["status"] == "PASS").sum())
            failed_checks = int((recent_metrics_df["status"] == "FAIL").sum())
            error_checks = int((recent_metrics_df["status"] == "ERROR").sum())
            health_score = round((passed_checks / total_checks) * 100, 1)
        else:
            health_score = None
            passed_checks = 0
            failed_checks = 0
            error_checks = 0

        # ----------------------------------------------------
        # C. FETCH LATEST EXECUTION
        # ----------------------------------------------------
        latest_run_df = pd.read_sql(
            "SELECT run_id, started_at FROM check_results ORDER BY result_id DESC LIMIT 1;",
            conn
        )

        # ----------------------------------------------------
        # D. DETERMINE OVERALL STATUS
        # ----------------------------------------------------
        if total_checks == 0:
            system_status = "NO DATA"
            health_description = "Awaiting first audit execution"
        elif unresolved_count > 0:
            system_status = "ATTENTION REQUIRED"
            health_description = f"{unresolved_count} unresolved incidents"
        elif error_checks > 0:
            system_status = "CHECK ERRORS"
            health_description = f"{error_checks} execution errors in recent checks"
        elif failed_checks > 0:
            system_status = "CHECKS FAILING"
            health_description = f"{failed_checks} recent checks failed"
        else:
            system_status = "HEALTHY"
            health_description = "All recent checks passing"

        # ====================================================
        # 6. KPI CARDS
        # ====================================================
        st.subheader("System Overview")
        st.caption("A high-level view of your monitored data environment.")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if health_score is not None:
                col1.metric(
                    "CHECK PASS RATE",
                    f"{health_score}%",
                    delta=f"{passed_checks}/{total_checks} passed",
                    delta_color="normal"
                )
            else:
                col1.metric("CHECK PASS RATE", "N/A", delta="No audit history")

        with col2:
            col2.metric(
                "UNRESOLVED INCIDENTS",
                f"{unresolved_count:,}",
                delta="Investigation required" if unresolved_count > 0 else "No open incidents",
                delta_color="inverse" if unresolved_count > 0 else "normal"
            )

        with col3:
            col3.metric(
                "MONITORED ASSETS",
                f"{asset_count:,}",
                delta=f"{active_rules:,} active rules"
            )

        with col4:
            if not latest_run_df.empty:
                raw_last_run = latest_run_df["started_at"].iloc[0]
                formatted_last_run = (
                    raw_last_run.strftime("%d %b %Y, %H:%M")
                    if hasattr(raw_last_run, "strftime")
                    else str(raw_last_run)
                )
                col4.metric("LAST EXECUTION", formatted_last_run, delta="Latest recorded check")
            else:
                col4.metric("LAST EXECUTION", "Never", delta="Awaiting first run")

        # ----------------------------------------------------
        # SYSTEM STATUS PANEL
        # ----------------------------------------------------
        st.markdown("### System Integrity Status")

        if system_status == "HEALTHY":
            status_color = "#4ADE80"
            status_background = "#123D2B"
        elif system_status == "NO DATA":
            status_color = "#A0A9B8"
            status_background = "#292F3B"
        elif system_status == "ATTENTION REQUIRED":
            status_color = "#F87171"
            status_background = "#451D24"
        else:
            status_color = "#FACC15"
            status_background = "#443313"

        st.markdown(
            f"""
            <div class="info-panel" style="
                display:flex;
                justify-content:space-between;
                align-items:center;
                flex-wrap:wrap;
                gap:12px;
            ">
                <div>
                    <div class="panel-label">CURRENT MONITORING STATUS</div>
                    <div style="color:{status_color}; font-size:22px; font-weight:700; margin-top:8px;">
                        ● {system_status}
                    </div>
                    <div class="panel-description">{health_description}</div>
                </div>
                <div style="
                    background:{status_background};
                    color:{status_color};
                    padding:10px 16px;
                    border-radius:8px;
                    font-size:12px;
                    font-weight:700;
                ">
                    {system_status}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.caption(
            "Check pass rate represents the percentage of recent "
            "configured checks passing. It is not a guarantee of "
            "financial or source-to-dashboard reconciliation."
        )

        st.divider()

        # ====================================================
        # 7. EXECUTION ANALYTICS
        # ====================================================
        st.subheader("Audit Performance")
        st.caption("Distribution of your most recent 100 check executions.")

        chart_col1, chart_col2 = st.columns([1.5, 1])

        with chart_col1:
            chart_data = pd.DataFrame({
                "Result": ["PASS", "FAIL", "ERROR"],
                "Count": [passed_checks, failed_checks, error_checks]
            }).set_index("Result")

            st.bar_chart(chart_data, y="Count", color="#38BDF8", height=260)

        with chart_col2:
            st.markdown("#### Execution Breakdown")
            breakdown = [
                ("Passed", passed_checks, "#4ADE80"),
                ("Failed", failed_checks, "#F87171"),
                ("Errors", error_checks, "#FACC15")
            ]

            for label, value, color in breakdown:
                percentage = (value / total_checks * 100) if total_checks > 0 else 0
                st.markdown(
                    f"""
                    <div style="margin-bottom:22px;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:7px;">
                            <span style="color:#A0A9B8; font-size:13px;">{label}</span>
                            <span style="color:#F3F4F6; font-weight:700;">{value:,} ({percentage:.1f}%)</span>
                        </div>
                        <div style="background:#292F3B; height:7px; border-radius:10px; overflow:hidden;">
                            <div style="background:{color}; width:{percentage}%; height:7px; border-radius:10px;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        st.divider()

        # ====================================================
        # 8. ACTIVE INCIDENTS
        # ====================================================
        st.subheader("🚨 Active Incidents")
        st.caption("Data quality violations that require investigation.")

        incidents_query = """
            SELECT
                i.incident_id,
                ma.table_name,
                qc.check_type,
                qc.severity,
                i.status,
                i.first_detected_at,
                i.last_detected_at
            FROM incidents i
            INNER JOIN quality_checks qc ON i.check_id = qc.check_id
            INNER JOIN monitored_assets ma ON qc.asset_id = ma.asset_id
            WHERE i.status IN ('OPEN', 'ACKNOWLEDGED')
            ORDER BY
                CASE
                    WHEN qc.severity = 'CRITICAL' THEN 1
                    WHEN qc.severity = 'WARNING' THEN 2
                    ELSE 3
                END,
                i.last_detected_at DESC
            LIMIT 20;
        """
        incidents_df = pd.read_sql(incidents_query, conn)

        if incidents_df.empty:
            st.success("No unresolved incidents. There are currently no outstanding recorded violations.")
        else:
            st.dataframe(
                incidents_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "incident_id": st.column_config.NumberColumn("Incident ID", format="%d"),
                    "table_name": st.column_config.TextColumn("Affected Dataset"),
                    "check_type": st.column_config.TextColumn("Detection Type"),
                    "severity": st.column_config.TextColumn("Severity"),
                    "status": st.column_config.TextColumn("Incident Status"),
                    "first_detected_at": st.column_config.DatetimeColumn("First Detected", format="DD MMM YYYY, HH:mm"),
                    "last_detected_at": st.column_config.DatetimeColumn("Last Detected", format="DD MMM YYYY, HH:mm")
                }
            )

        st.divider()

        # ====================================================
        # 9. RECENT AUDIT ACTIVITY
        # ====================================================
        st.subheader("📋 Recent Audit Activity")
        st.caption("The latest recorded executions across monitored datasets.")

        recent_results_query = """
            SELECT
                cr.result_id,
                cr.run_id,
                ma.table_name,
                qc.check_type,
                qc.severity,
                cr.status,
                cr.observed_value,
                cr.expected_value,
                cr.message,
                cr.started_at
            FROM check_results cr
            INNER JOIN quality_checks qc ON cr.check_id = qc.check_id
            INNER JOIN monitored_assets ma ON qc.asset_id = ma.asset_id
            ORDER BY cr.result_id DESC
            LIMIT 15;
        """
        recent_results = pd.read_sql(recent_results_query, conn)

        if recent_results.empty:
            st.info("No audit activity has been recorded yet.")
        else:
            st.dataframe(
                recent_results,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "result_id": st.column_config.NumberColumn("Result ID", format="%d"),
                    "run_id": st.column_config.TextColumn("Execution ID"),
                    "table_name": st.column_config.TextColumn("Dataset"),
                    "check_type": st.column_config.TextColumn("Check Type"),
                    "severity": st.column_config.TextColumn("Severity"),
                    "status": st.column_config.TextColumn("Result"),
                    "observed_value": st.column_config.TextColumn("Observed Value", width="medium"),
                    "expected_value": st.column_config.TextColumn("Expected Value", width="medium"),
                    "message": st.column_config.TextColumn("Execution Details", width="large"),
                    "started_at": st.column_config.DatetimeColumn("Execution Time", format="DD MMM YYYY, HH:mm")
                }
            )

        # ----------------------------------------------------
        # LAST UPDATED
        # ----------------------------------------------------
        st.divider()
        st.markdown(
            f"""
            <div style="
                display:flex;
                justify-content:space-between;
                color:#929BAA;
                font-size:11px;
            ">
                <span>DATA QUALITY FIREWALL · MONITORING OVERVIEW</span>
                <span>Last refreshed: {datetime.now().strftime("%d %b %Y, %H:%M:%S")}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        logger.exception("Overview dashboard failed.")
        st.error("Unable to retrieve monitoring information. Check the database connection and application logs.")
        st.caption(f"Technical details: {type(e).__name__}: {str(e)}")

    finally:
        if conn is not None and conn.is_connected():
            conn.close()


# ============================================================
# 10. RENDER DASHBOARD
# ============================================================

render_live_overview()