import os
import logging

import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px

from datetime import date, timedelta
from dotenv import load_dotenv


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Data Quality Firewall — Audit History",
    page_icon="📜",
    layout="wide"
)

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================
# 2. STYLING
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
        padding: 18px;
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
# 4. DATA RETRIEVAL
# ============================================================

@st.cache_data(ttl=10)
def fetch_audit_history():
    conn = None
    try:
        conn = get_db_connection()
        query = """
            SELECT
                cr.result_id,
                cr.run_id,
                ma.schema_name,
                ma.table_name,
                qc.check_type,
                qc.severity,
                cr.status,
                cr.observed_value,
                cr.expected_value,
                cr.message,
                cr.started_at
            FROM check_results cr
            JOIN quality_checks qc ON cr.check_id = qc.check_id
            JOIN monitored_assets ma ON qc.asset_id = ma.asset_id
            ORDER BY cr.started_at DESC, cr.result_id DESC;
        """
        return pd.read_sql(query, conn)
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================
# 5. PAGE HEADER
# ============================================================

st.title("📜 Execution Audit History")
st.caption(
    "Historical execution records, data quality outcomes, "
    "and operational performance."
)

header_col1, header_col2 = st.columns([5, 1])
with header_col2:
    if st.button("↻ Refresh Data", use_container_width=True):
        fetch_audit_history.clear()
        st.rerun()

st.divider()


# ============================================================
# 6. LOAD DATA & INITIAL SANITIZATION
# ============================================================

try:
    df_history = fetch_audit_history()
except Exception as e:
    logger.exception("Failed to load audit history.")
    st.error(f"Unable to retrieve audit history: {e}")
    st.stop()

if df_history.empty:
    st.info(
        "No audit execution records are available yet. "
        "Records will appear after your firewall executes checks."
    )
    st.stop()

df_history["started_at"] = pd.to_datetime(df_history["started_at"], errors="coerce")
df_history["status"] = df_history["status"].astype(str).str.upper()
df_history["check_type"] = df_history["check_type"].astype(str).str.lower()


# ============================================================
# 7. FILTERS
# ============================================================

st.markdown('<div class="section-label">Audit filters</div>', unsafe_allow_html=True)

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    status_options = sorted(df_history["status"].dropna().unique())
    selected_status = st.multiselect("Execution Status", status_options, default=status_options)

with filter_col2:
    table_options = sorted(df_history["table_name"].dropna().unique())
    selected_tables = st.multiselect("Monitored Tables", table_options, default=table_options)

with filter_col3:
    check_options = sorted(df_history["check_type"].dropna().unique())
    selected_checks = st.multiselect("Check Type", check_options, default=check_options)

filter_col4, filter_col5 = st.columns([1, 2])

with filter_col4:
    severity_options = sorted(df_history["severity"].dropna().unique())
    selected_severity = st.multiselect("Severity", severity_options, default=severity_options)

with filter_col5:
    search_term = st.text_input("Search audit records", placeholder="Search run ID, message, or table...")


# ============================================================
# 8. APPLY FILTERS
# ============================================================

filtered_df = df_history[
    df_history["status"].isin(selected_status)
    & df_history["table_name"].isin(selected_tables)
    & df_history["check_type"].isin(selected_checks)
    & df_history["severity"].isin(selected_severity)
].copy()

if search_term:
    search_mask = (
        filtered_df["run_id"].astype(str).str.contains(search_term, case=False, na=False)
        | filtered_df["message"].astype(str).str.contains(search_term, case=False, na=False)
        | filtered_df["table_name"].astype(str).str.contains(search_term, case=False, na=False)
    )
    filtered_df = filtered_df[search_mask]


# ============================================================
# 9. DATE FILTER
# ============================================================

st.divider()
st.markdown("### 📅 Execution Period")

valid_dates = filtered_df["started_at"].dropna()

if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
    with date_col2:
        end_date = st.date_input("To", value=max_date, min_value=min_date, max_value=max_date)

    if start_date > end_date:
        st.error("Start date cannot be later than end date.")
        st.stop()

    filtered_df = filtered_df[
        (filtered_df["started_at"].dt.date >= start_date)
        & (filtered_df["started_at"].dt.date <= end_date)
    ]


# ============================================================
# 10. EXECUTION METRICS
# ============================================================

st.divider()
st.markdown("### 📊 Execution Performance")

total_executions = len(filtered_df)
passes = int((filtered_df["status"] == "PASS").sum())
failures = int((filtered_df["status"] == "FAIL").sum())
errors = int((filtered_df["status"] == "ERROR").sum())
unique_runs = filtered_df["run_id"].nunique()

pass_rate = (passes / total_executions * 100) if total_executions > 0 else 0

metric_cols = st.columns(5)
metric_cols[0].metric("Check Executions", f"{total_executions:,}")
metric_cols[1].metric("Unique Runs", f"{unique_runs:,}")
metric_cols[2].metric("Pass Rate", f"{pass_rate:.1f}%")
metric_cols[3].metric("Failures", f"{failures:,}")
metric_cols[4].metric("System Errors", f"{errors:,}")

if total_executions == 0:
    st.warning("No records match the selected filters.")
    st.stop()


# ============================================================
# 11. EXECUTION OUTCOME CHARTS
# ============================================================

st.divider()
st.markdown("### 📈 Execution Analytics")

chart_col1, chart_col2 = st.columns(2)

COLOR_MAP = {
    "PASS": "#4ADE80",
    "FAIL": "#F87171",
    "ERROR": "#FACC15"
}

with chart_col1:
    st.markdown("**Execution Outcome Distribution**")
    outcome_df = (
        filtered_df["status"]
        .value_counts()
        .rename_axis("Status")
        .reset_index(name="Executions")
    )

    fig_outcome = px.pie(
        outcome_df,
        names="Status",
        values="Executions",
        hole=0.65,
        color="Status",
        color_discrete_map=COLOR_MAP
    )
    fig_outcome.update_layout(
        height=340,
        margin=dict(t=20, b=20, l=10, r=10),
        legend_title_text="Outcome",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#A0A9B8")
    )
    st.plotly_chart(fig_outcome, use_container_width=True)

with chart_col2:
    st.markdown("**Execution Volume Over Time**")
    trend_df = filtered_df.dropna(subset=["started_at"]).copy()

    if not trend_df.empty:
        trend_df["Date"] = trend_df["started_at"].dt.date
        daily_df = (
            trend_df.groupby(["Date", "status"])
            .size()
            .reset_index(name="Executions")
        )

        fig_trend = px.line(
            daily_df,
            x="Date",
            y="Executions",
            color="status",
            markers=True,
            color_discrete_map=COLOR_MAP
        )
        fig_trend.update_layout(
            height=340,
            margin=dict(t=20, b=20, l=10, r=10),
            xaxis_title="Execution Date",
            yaxis_title="Number of Checks",
            legend_title_text="Status",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#A0A9B8"),
            xaxis=dict(gridcolor="#292F3B"),
            yaxis=dict(gridcolor="#292F3B")
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No valid timestamps available for trend analysis.")


# ============================================================
# 12. AUDIT EXECUTION LOG
# ============================================================

st.divider()
st.markdown("### 📋 Audit Execution Log")

display_df = filtered_df[
    [
        "result_id",
        "run_id",
        "schema_name",
        "table_name",
        "check_type",
        "severity",
        "status",
        "observed_value",
        "expected_value",
        "started_at"
    ]
].copy().rename(columns={
    "result_id": "Result ID",
    "run_id": "Run ID",
    "schema_name": "Schema",
    "table_name": "Table",
    "check_type": "Check",
    "severity": "Severity",
    "status": "Status",
    "observed_value": "Observed",
    "expected_value": "Expected",
    "started_at": "Execution Time"
})

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=450,
    column_config={
        "Result ID": st.column_config.NumberColumn("Result ID", format="%d"),
        "Run ID": st.column_config.TextColumn("Run ID"),
        "Schema": st.column_config.TextColumn("Schema"),
        "Table": st.column_config.TextColumn("Table"),
        "Check": st.column_config.TextColumn("Check Type"),
        "Severity": st.column_config.TextColumn("Severity"),
        "Status": st.column_config.TextColumn("Status"),
        "Observed": st.column_config.TextColumn("Observed"),
        "Expected": st.column_config.TextColumn("Expected"),
        "Execution Time": st.column_config.DatetimeColumn("Execution Time", format="DD MMM YYYY, HH:mm")
    }
)


# ============================================================
# 13. EXECUTION INVESTIGATION
# ============================================================

st.divider()
st.markdown("### 🔍 Execution Investigation")

result_options = filtered_df["result_id"].tolist()

selected_result_id = st.selectbox(
    "Select an execution record",
    result_options,
    format_func=lambda x: (
        f"Result #{x} — "
        f"{filtered_df.loc[filtered_df['result_id'] == x, 'status'].iloc[0]} — "
        f"{filtered_df.loc[filtered_df['result_id'] == x, 'check_type'].iloc[0]}"
    )
)

selected_result = filtered_df[filtered_df["result_id"] == selected_result_id].iloc[0]

detail_col1, detail_col2 = st.columns(2)

with detail_col1:
    st.markdown("**Execution Details**")
    st.write(f"**Run ID:** `{selected_result['run_id']}`")
    st.write(f"**Table:** `{selected_result['schema_name']}.{selected_result['table_name']}`")
    st.write(f"**Check:** `{selected_result['check_type']}`")
    st.write(f"**Severity:** `{selected_result['severity']}`")
    st.write(f"**Status:** `{selected_result['status']}`")
    st.write(f"**Executed:** {selected_result['started_at']}")

with detail_col2:
    st.markdown("**Validation Results**")
    st.write(f"**Observed Value:** {selected_result['observed_value']}")
    st.write(f"**Expected Value:** {selected_result['expected_value']}")
    st.write("**Diagnostic Message:**")
    message = selected_result["message"]
    if pd.notna(message) and str(message).strip():
        st.info(str(message))
    else:
        st.caption("No diagnostic message was recorded.")

st.divider()
st.caption(
    "DATA QUALITY FIREWALL · EXECUTION AUDIT HISTORY"
)