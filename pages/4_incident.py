import os
import logging

import streamlit as st
import pandas as pd
import mysql.connector

from datetime import datetime
from dotenv import load_dotenv


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Data Quality Firewall | Incidents",
    page_icon="🚨",
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
        max-width: 1600px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    div[data-testid="stMetric"] {
        background: #171B24;
        border: 1px solid #292F3B;
        border-radius: 12px;
        padding: 18px;
        min-height: 110px;
    }

    div[data-testid="stMetricLabel"] {
        color: #A0A9B8;
        font-size: 13px;
    }

    div[data-testid="stMetricValue"] {
        color: #F3F4F6;
        font-weight: 700;
    }

    .section-description {
        color: #929BAA;
        font-size: 13px;
        margin-top: -8px;
        margin-bottom: 16px;
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
    required_vars = [
        "MYSQL_HOST",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE"
    ]

    missing = [
        var for var in required_vars
        if not os.getenv(var)
    ]

    if missing:
        raise ValueError(
            f"Missing environment variables: {', '.join(missing)}"
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
# 4. DATABASE HELPERS
# ============================================================

def fetch_dataframe(conn, query, params=None):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        records = cursor.fetchall()
        return pd.DataFrame(records)
    finally:
        cursor.close()


def update_incident(conn, incident_id, new_status, resolution_note):
    query = """
        UPDATE incidents
        SET
            status = %s,
            resolution_note = %s,
            resolved_at = %s
        WHERE incident_id = %s
          AND status != 'RESOLVED';
    """

    resolved_time = datetime.now() if new_status == "RESOLVED" else None
    cursor = conn.cursor()

    try:
        cursor.execute(
            query,
            (
                new_status,
                resolution_note,
                resolved_time,
                incident_id
            )
        )

        if cursor.rowcount == 0:
            conn.rollback()
            raise ValueError(
                "Incident was already resolved or no longer exists."
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ============================================================
# 5. PAGE HEADER
# ============================================================

st.title("🚨 Incident Management & Triage")
st.caption(
    "Investigate data quality failures, acknowledge active alerts, "
    "and document incident resolutions."
)
st.divider()


# ============================================================
# 6. MAIN APPLICATION
# ============================================================

conn = None

try:
    conn = get_db_connection()

    # --------------------------------------------------------
    # FETCH INCIDENT HISTORY
    # --------------------------------------------------------
    incidents_query = """
        SELECT
            i.incident_id,
            i.check_id,
            ds.source_name,
            ma.schema_name,
            ma.table_name,
            qc.check_type,
            qc.severity,
            i.deduplication_key,
            i.status,
            i.first_detected_at,
            i.last_detected_at,
            i.resolved_at,
            i.resolution_note
        FROM incidents i
        INNER JOIN quality_checks qc ON i.check_id = qc.check_id
        INNER JOIN monitored_assets ma ON qc.asset_id = ma.asset_id
        LEFT JOIN data_sources ds ON ma.source_id = ds.source_id
        ORDER BY i.incident_id DESC;
    """

    df_incidents = fetch_dataframe(conn, incidents_query)

    # ========================================================
    # 7. INCIDENT METRICS
    # ========================================================
    st.subheader("Incident Overview")

    if df_incidents.empty:
        total_incidents = 0
        open_count = 0
        acknowledged_count = 0
        resolved_count = 0
        critical_count = 0
    else:
        total_incidents = len(df_incidents)
        open_count = int((df_incidents["status"] == "OPEN").sum())
        acknowledged_count = int((df_incidents["status"] == "ACKNOWLEDGED").sum())
        resolved_count = int((df_incidents["status"] == "RESOLVED").sum())
        critical_count = int(
            (
                (df_incidents["severity"] == "CRITICAL") &
                (df_incidents["status"] != "RESOLVED")
            ).sum()
        )

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Incidents", total_incidents)
    with col2:
        st.metric(
            "Open",
            open_count,
            delta="Requires attention" if open_count else "Clear",
            delta_color="inverse" if open_count else "normal"
        )
    with col3:
        st.metric("Acknowledged", acknowledged_count)
    with col4:
        st.metric("Resolved", resolved_count)
    with col5:
        st.metric(
            "Critical Active",
            critical_count,
            delta="Priority investigation" if critical_count else "None",
            delta_color="inverse" if critical_count else "normal"
        )

    st.divider()

    # ========================================================
    # 8. ACTIVE INCIDENT SUMMARY
    # ========================================================
    st.subheader("🚨 Active Incident Summary")

    if df_incidents.empty:
        st.success("No incidents recorded. Your monitoring pipeline is clean.")
    elif open_count == 0 and acknowledged_count == 0:
        st.success("All recorded incidents have been resolved.")
    else:
        active_incidents = df_incidents[
            df_incidents["status"].isin(["OPEN", "ACKNOWLEDGED"])
        ]
        critical_active = active_incidents[
            active_incidents["severity"] == "CRITICAL"
        ]

        if not critical_active.empty:
            st.error(f"{len(critical_active)} active critical incident(s) require immediate investigation.")
        elif open_count > 0:
            st.warning(f"{open_count} incident(s) are awaiting acknowledgement.")
        else:
            st.info("Active incidents have been acknowledged. Review remediation progress.")

        priority_view = active_incidents[
            [
                "incident_id",
                "table_name",
                "check_type",
                "severity",
                "status",
                "first_detected_at",
                "last_detected_at"
            ]
        ].copy().rename(
            columns={
                "incident_id": "Incident ID",
                "table_name": "Dataset",
                "check_type": "Check Type",
                "severity": "Severity",
                "status": "Status",
                "first_detected_at": "First Detected",
                "last_detected_at": "Last Detected"
            }
        )

        st.dataframe(
            priority_view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Incident ID": st.column_config.NumberColumn("Incident ID", format="%d"),
                "Dataset": st.column_config.TextColumn("Dataset"),
                "Check Type": st.column_config.TextColumn("Check Type"),
                "Severity": st.column_config.TextColumn("Severity"),
                "Status": st.column_config.TextColumn("Status"),
                "First Detected": st.column_config.DatetimeColumn("First Detected", format="DD MMM YYYY, HH:mm"),
                "Last Detected": st.column_config.DatetimeColumn("Last Detected", format="DD MMM YYYY, HH:mm")
            }
        )

    st.divider()

    # ========================================================
    # 9. INCIDENT HISTORY & FILTERING
    # ========================================================
    st.subheader("📋 Incident History")
    st.markdown(
        '<div class="section-description">'
        'Search, filter, and review previously detected data quality incidents.'
        '</div>',
        unsafe_allow_html=True
    )

    if not df_incidents.empty:
        filter1, filter2, filter3 = st.columns(3)
        with filter1:
            status_filter = st.selectbox("Incident Status", ["All", "OPEN", "ACKNOWLEDGED", "RESOLVED"])
        with filter2:
            severity_filter = st.selectbox("Severity", ["All", "CRITICAL", "WARNING", "INFO"])
        with filter3:
            type_filter = st.selectbox("Validation Type", ["All", "freshness", "volume", "uniqueness"])

        search_term = st.text_input("Search Dataset / Source / Incident ID", placeholder="Search incidents...")

        filtered_df = df_incidents.copy()

        if status_filter != "All":
            filtered_df = filtered_df[filtered_df["status"] == status_filter]

        if severity_filter != "All":
            filtered_df = filtered_df[filtered_df["severity"] == severity_filter]

        if type_filter != "All":
            filtered_df = filtered_df[filtered_df["check_type"] == type_filter]

        if search_term.strip():
            term = search_term.strip()
            search_mask = (
                filtered_df["table_name"].astype(str).str.contains(term, case=False, na=False) |
                filtered_df["source_name"].astype(str).str.contains(term, case=False, na=False) |
                filtered_df["incident_id"].astype(str).str.contains(term, case=False, na=False)
            )
            filtered_df = filtered_df[search_mask]

        st.caption(f"Displaying {len(filtered_df)} of {total_incidents} incidents.")

        if filtered_df.empty:
            st.info("No incidents match your selected filters.")
        else:
            history_view = filtered_df[
                [
                    "incident_id",
                    "source_name",
                    "schema_name",
                    "table_name",
                    "check_type",
                    "severity",
                    "status",
                    "first_detected_at",
                    "last_detected_at",
                    "resolved_at"
                ]
            ].copy().rename(
                columns={
                    "incident_id": "Incident ID",
                    "source_name": "Data Source",
                    "schema_name": "Schema",
                    "table_name": "Dataset",
                    "check_type": "Check Type",
                    "severity": "Severity",
                    "status": "Status",
                    "first_detected_at": "First Detected",
                    "last_detected_at": "Last Detected",
                    "resolved_at": "Resolved At"
                }
            )

            st.dataframe(
                history_view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Incident ID": st.column_config.NumberColumn("Incident ID", format="%d"),
                    "Data Source": "Source",
                    "Schema": "Schema",
                    "Dataset": "Dataset",
                    "Check Type": "Check Type",
                    "Severity": "Severity",
                    "Status": "Status",
                    "First Detected": st.column_config.DatetimeColumn("First Detected", format="DD MMM YYYY, HH:mm"),
                    "Last Detected": st.column_config.DatetimeColumn("Last Detected", format="DD MMM YYYY, HH:mm"),
                    "Resolved At": st.column_config.DatetimeColumn("Resolved At", format="DD MMM YYYY, HH:mm")
                }
            )
    else:
        st.info("Incident history will appear here when a quality check fails.")

    st.divider()

    # ========================================================
    # 10. INCIDENT INVESTIGATION
    # ========================================================
    st.subheader("🔍 Incident Investigation")
    st.markdown(
        '<div class="section-description">'
        'Select an incident to inspect failure details and historical check results.'
        '</div>',
        unsafe_allow_html=True
    )

    if df_incidents.empty:
        st.info("No incidents available for investigation.")
    else:
        incident_options = {
            int(row["incident_id"]): f'#{row["incident_id"]} | {row["table_name"]} | {row["check_type"]} | {row["severity"]} | {row["status"]}'
            for _, row in df_incidents.iterrows()
        }

        selected_incident_id = st.selectbox(
            "Select Incident",
            options=list(incident_options.keys()),
            format_func=lambda x: incident_options[x],
            key="investigation_incident"
        )

        selected_incident = df_incidents[df_incidents["incident_id"] == selected_incident_id].iloc[0]

        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            st.markdown("##### Incident Information")
            st.write(f"**Incident ID:** #{selected_incident['incident_id']}")
            st.write(f"**Source:** {selected_incident['source_name']}")
            st.write(f"**Dataset:** `{selected_incident['schema_name']}.{selected_incident['table_name']}`")
            st.write(f"**Validation:** {str(selected_incident['check_type']).title()}")
            st.write(f"**Severity:** {selected_incident['severity']}")
            st.write(f"**Current Status:** {selected_incident['status']}")

        with detail_col2:
            st.markdown("##### Detection Timeline")
            st.write(f"**First Detected:** {selected_incident['first_detected_at']}")
            st.write(f"**Last Detected:** {selected_incident['last_detected_at']}")
            st.write(f"**Resolved At:** {selected_incident['resolved_at'] or 'Not resolved'}")
            if selected_incident["resolution_note"]:
                st.write(f"**Resolution Note:** {selected_incident['resolution_note']}")

        # ----------------------------------------------------
        # FETCH HISTORICAL CHECK RESULTS
        # ----------------------------------------------------
        st.markdown("##### Historical Validation Results")

        results_query = """
            SELECT
                result_id,
                run_id,
                status,
                observed_value,
                expected_value,
                message,
                started_at
            FROM check_results
            WHERE check_id = %s
            ORDER BY result_id DESC
            LIMIT 20;
        """

        results_df = fetch_dataframe(
            conn,
            results_query,
            (int(selected_incident["check_id"]),)
        )

        if results_df.empty:
            st.info("No historical validation results available.")
        else:
            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "result_id": st.column_config.NumberColumn("Result ID", format="%d"),
                    "run_id": st.column_config.TextColumn("Run ID"),
                    "status": st.column_config.TextColumn("Status"),
                    "observed_value": st.column_config.TextColumn("Observed"),
                    "expected_value": st.column_config.TextColumn("Expected"),
                    "message": st.column_config.TextColumn("Details", width="large"),
                    "started_at": st.column_config.DatetimeColumn("Execution Time", format="DD MMM YYYY, HH:mm")
                }
            )

            latest_result = results_df.iloc[0]
            with st.expander("Latest Failure Details", expanded=True):
                st.write(f"**Observed:** {latest_result['observed_value']}")
                st.write(f"**Expected:** {latest_result['expected_value']}")
                st.write(f"**Details:** {latest_result['message']}")

    st.divider()

    # ========================================================
    # 11. INCIDENT TRIAGE
    # ========================================================
    st.subheader("🛠️ Incident Triage & Resolution")
    st.markdown(
        '<div class="section-description">'
        'Acknowledge active incidents or formally record their resolution.'
        '</div>',
        unsafe_allow_html=True
    )

    if df_incidents.empty:
        st.info("There are no incidents available for triage.")
    else:
        active_incidents = df_incidents[
            df_incidents["status"].isin(["OPEN", "ACKNOWLEDGED"])
        ]

        if active_incidents.empty:
            st.success("All incidents have been resolved. No further triage required.")
        else:
            triage_options = {
                int(row["incident_id"]): f'#{row["incident_id"]} | {row["table_name"]} | {row["check_type"]} | {row["status"]}'
                for _, row in active_incidents.iterrows()
            }

            selected_triage_id = st.selectbox(
                "Select Incident for Triage",
                options=list(triage_options.keys()),
                format_func=lambda x: triage_options[x],
                key="triage_incident"
            )

            triage_row = active_incidents[
                active_incidents["incident_id"] == selected_triage_id
            ].iloc[0]

            st.write(f"**Incident:** #{selected_triage_id}")
            st.write(f"**Affected Dataset:** `{triage_row['schema_name']}.{triage_row['table_name']}`")
            st.write(f"**Severity:** {triage_row['severity']}")
            st.write(f"**Current Status:** {triage_row['status']}")

            with st.form("incident_triage_form"):
                new_status = st.selectbox("Update Incident Status", ["ACKNOWLEDGED", "RESOLVED"])
                resolution_note = st.text_area(
                    "Investigation / Resolution Notes",
                    placeholder="Describe what happened, what was investigated, and how the issue was fixed...",
                    height=130
                )

                submit_triage = st.form_submit_button("Update Incident", type="primary", use_container_width=True)

                if submit_triage:
                    if new_status == "RESOLVED" and not resolution_note.strip():
                        st.error("A resolution note is required before closing an incident.")
                    else:
                        try:
                            update_incident(
                                conn,
                                selected_triage_id,
                                new_status,
                                resolution_note.strip()
                            )
                            st.success(f"Incident #{selected_triage_id} updated to {new_status}.")
                            st.rerun()
                        except Exception as e:
                            logger.exception("Incident triage update failed.")
                            st.error("Unable to update the selected incident.")
                            st.code(str(e))

    st.divider()
    st.caption("DATA QUALITY FIREWALL · INCIDENT MANAGEMENT & TRIAGE")

except Exception as e:
    logger.exception("Incident management page failed.")
    st.error("Unable to load Incident Management. Check database connection.")
    with st.expander("Technical details"):
        st.code(f"{type(e).__name__}: {e}")

finally:
    if conn is not None and conn.is_connected():
        conn.close()