import os
import json
import re
import logging

import streamlit as st
import pandas as pd
import mysql.connector

from dotenv import load_dotenv


# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Data Quality Firewall | Rules",
    page_icon="⚙️",
    layout="wide"
)

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================
# 2. CUSTOM UI STYLING
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


def get_table_columns(conn, schema_name, table_name):
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE LOWER(table_schema) = LOWER(%s)
          AND LOWER(table_name) = LOWER(%s)
        ORDER BY ordinal_position;
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (schema_name, table_name))
        results = cursor.fetchall()
        return [row["column_name"] for row in results]
    finally:
        cursor.close()


def parse_configuration(config):
    if isinstance(config, dict):
        return config
    if isinstance(config, str) and config.strip():
        try:
            return json.loads(config)
        except Exception:
            return {}
    return {}


def save_rule(conn, asset_id, check_type, config_payload, severity):
    query = """
        INSERT INTO quality_checks (
            asset_id,
            check_type,
            configuration_json,
            severity,
            is_enabled
        )
        VALUES (%s, %s, %s, %s, TRUE);
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            query,
            (
                asset_id,
                check_type,
                json.dumps(config_payload),
                severity
            )
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def update_rule(conn, check_id, config_payload, severity):
    query = """
        UPDATE quality_checks
        SET configuration_json = %s,
            severity = %s
        WHERE check_id = %s;
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            query,
            (
                json.dumps(config_payload),
                severity,
                check_id
            )
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def update_rule_status(conn, check_id, enabled):
    query = """
        UPDATE quality_checks
        SET is_enabled = %s
        WHERE check_id = %s;
    """
    cursor = conn.cursor()
    try:
        cursor.execute(query, (enabled, check_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ============================================================
# 5. RULE DEFINITIONS
# ============================================================

CHECK_DESCRIPTIONS = {
    "freshness": (
        "Detects stale datasets by measuring the age "
        "of the latest available timestamp."
    ),
    "volume": (
        "Detects unexpected changes in daily dataset "
        "volume, including missing or excessive records."
    ),
    "uniqueness": (
        "Detects duplicate business keys that could "
        "inflate revenue or distort downstream analysis."
    )
}


# ============================================================
# 6. PAGE HEADER
# ============================================================

st.title("⚙️ Rule Configuration Engine")
st.caption(
    "Configure, deploy, and manage data quality guardrails "
    "across your monitored datasets."
)
st.divider()


# ============================================================
# 7. MAIN APPLICATION
# ============================================================

conn = None

try:
    conn = get_db_connection()

    # --------------------------------------------------------
    # FETCH RULES & ASSETS
    # --------------------------------------------------------
    rules_query = """
        SELECT
            qc.check_id,
            qc.asset_id,
            ds.source_name,
            ma.schema_name,
            ma.table_name,
            qc.check_type,
            qc.severity,
            qc.is_enabled,
            qc.configuration_json,
            qc.created_at
        FROM quality_checks qc
        INNER JOIN monitored_assets ma ON qc.asset_id = ma.asset_id
        LEFT JOIN data_sources ds ON ma.source_id = ds.source_id
        ORDER BY qc.check_id DESC;
    """
    rules_df = fetch_dataframe(conn, rules_query)

    assets_query = """
        SELECT
            ma.asset_id,
            ma.schema_name,
            ma.table_name,
            ds.source_name
        FROM monitored_assets ma
        LEFT JOIN data_sources ds ON ma.source_id = ds.source_id
        WHERE ma.is_active = TRUE
        ORDER BY ma.table_name ASC;
    """
    assets_df = fetch_dataframe(conn, assets_query)

    if not rules_df.empty:
        rules_df["is_enabled"] = rules_df["is_enabled"].fillna(False).astype(bool)

    # ========================================================
    # 8. RULE PERFORMANCE SUMMARY
    # ========================================================
    st.subheader("Rule Monitoring Overview")

    total_rules = len(rules_df)
    enabled_rules = int(rules_df["is_enabled"].sum()) if not rules_df.empty else 0
    disabled_rules = total_rules - enabled_rules
    critical_rules = int((rules_df["severity"] == "CRITICAL").sum()) if not rules_df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Rules", total_rules)
    with col2:
        st.metric("Enabled Rules", enabled_rules, delta="Currently active")
    with col3:
        st.metric("Disabled Rules", disabled_rules, delta="Paused", delta_color="off")
    with col4:
        st.metric("Critical Rules", critical_rules)

    st.divider()

    # ========================================================
    # 9. EXISTING RULE INVENTORY
    # ========================================================
    st.subheader("📋 Registered Quality Rules")
    st.markdown(
        '<div class="section-description">'
        'Review all configured validation rules and their deployment status.'
        '</div>',
        unsafe_allow_html=True
    )

    if rules_df.empty:
        st.info("No quality rules have been configured yet. Create your first rule below.")
    else:
        filter1, filter2, filter3 = st.columns(3)
        with filter1:
            type_filter = st.selectbox("Check Type", ["All", "freshness", "volume", "uniqueness"])
        with filter2:
            severity_filter = st.selectbox("Severity", ["All", "CRITICAL", "WARNING", "INFO"])
        with filter3:
            status_filter = st.selectbox("Deployment Status", ["All", "Enabled", "Disabled"])

        filtered_rules = rules_df.copy()

        if type_filter != "All":
            filtered_rules = filtered_rules[filtered_rules["check_type"] == type_filter]

        if severity_filter != "All":
            filtered_rules = filtered_rules[filtered_rules["severity"] == severity_filter]

        if status_filter == "Enabled":
            filtered_rules = filtered_rules[filtered_rules["is_enabled"]]
        elif status_filter == "Disabled":
            filtered_rules = filtered_rules[~filtered_rules["is_enabled"]]

        st.caption(f"Displaying {len(filtered_rules)} of {total_rules} rules.")

        if filtered_rules.empty:
            st.info("No rules match the selected filters.")
        else:
            display_rules = filtered_rules[
                [
                    "check_id", "source_name", "schema_name", "table_name",
                    "check_type", "severity", "is_enabled", "configuration_json", "created_at"
                ]
            ].copy().rename(
                columns={
                    "check_id": "Rule ID",
                    "source_name": "Data Source",
                    "schema_name": "Schema",
                    "table_name": "Dataset",
                    "check_type": "Validation Type",
                    "severity": "Severity",
                    "is_enabled": "Enabled",
                    "configuration_json": "Configuration",
                    "created_at": "Created At"
                }
            )

            display_rules["Configuration"] = display_rules["Configuration"].apply(
                lambda x: json.dumps(parse_configuration(x), separators=(",", ":"))
            )

            st.dataframe(
                display_rules,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rule ID": st.column_config.NumberColumn("Rule ID", format="%d"),
                    "Enabled": st.column_config.CheckboxColumn("Enabled", disabled=True),
                    "Configuration": st.column_config.TextColumn("Configuration", width="large"),
                    "Created At": st.column_config.DatetimeColumn("Created At", format="DD MMM YYYY, HH:mm")
                }
            )

    st.divider()

    # ========================================================
    # 10. CREATE NEW RULE
    # ========================================================
    st.subheader("➕ Create New Quality Rule")
    st.markdown(
        '<div class="section-description">'
        'Define a new validation rule and deploy it to an active dataset.'
        '</div>',
        unsafe_allow_html=True
    )

    if assets_df.empty:
        st.warning("No active monitored datasets are available. Register a dataset first on the Data Sources page.")
    else:
        asset_options = {
            row["asset_id"]: f'{row["source_name"]} | {row["schema_name"]}.{row["table_name"]}'
            for _, row in assets_df.iterrows()
        }

        selected_asset_id = st.selectbox(
            "Select Target Dataset",
            options=list(asset_options.keys()),
            format_func=lambda x: asset_options[x],
            key="new_rule_asset"
        )

        selected_asset = assets_df[assets_df["asset_id"] == selected_asset_id].iloc[0]
        selected_schema = selected_asset["schema_name"]
        selected_table = selected_asset["table_name"]

        available_columns = get_table_columns(conn, selected_schema, selected_table)

        if not available_columns:
            st.error("Unable to retrieve columns for the selected dataset. Check database permissions.")
        else:
            check_type = st.selectbox(
                "Select Validation Type",
                options=["freshness", "volume", "uniqueness"],
                format_func=lambda x: x.title(),
                key="new_rule_type"
            )

            st.info(CHECK_DESCRIPTIONS[check_type])

            # ------------------------------------------------
            # FRESHNESS CREATION
            # ------------------------------------------------
            if check_type == "freshness":
                with st.form("freshness_rule_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        timestamp_col = st.selectbox("Timestamp Column", available_columns, key="new_freshness_column")
                    with col2:
                        max_allowed_hours = st.number_input("Maximum Allowed Data Age (Hours)", min_value=1, max_value=8760, value=24)

                    severity = st.selectbox("Severity Level", ["CRITICAL", "WARNING", "INFO"], key="freshness_severity")
                    submit = st.form_submit_button("Deploy Freshness Rule", type="primary", use_container_width=True)

                    if submit:
                        config_payload = {
                            "timestamp_col": timestamp_col,
                            "max_allowed_hours": int(max_allowed_hours)
                        }
                        try:
                            save_rule(conn, selected_asset_id, check_type, config_payload, severity)
                            st.success("Freshness rule successfully deployed.")
                            st.rerun()
                        except Exception as e:
                            logger.exception("Freshness rule creation failed.")
                            st.error("Unable to save freshness rule.")
                            st.code(str(e))

            # ------------------------------------------------
            # VOLUME CREATION
            # ------------------------------------------------
            elif check_type == "volume":
                with st.form("volume_rule_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        date_col = st.selectbox("Date / Timestamp Column", available_columns, key="new_volume_column")
                        min_rows = st.number_input("Minimum Expected Rows", min_value=0, value=100, step=10)
                    with col2:
                        max_rows = st.number_input("Maximum Expected Rows", min_value=1, value=10000, step=100)
                        severity = st.selectbox("Severity Level", ["CRITICAL", "WARNING", "INFO"], key="volume_severity")

                    submit = st.form_submit_button("Deploy Volume Rule", type="primary", use_container_width=True)

                    if submit:
                        if max_rows < min_rows:
                            st.error("Maximum rows cannot be lower than minimum rows.")
                        else:
                            config_payload = {
                                "date_col": date_col,
                                "min_rows": int(min_rows),
                                "max_rows": int(max_rows)
                            }
                            try:
                                save_rule(conn, selected_asset_id, check_type, config_payload, severity)
                                st.success("Volume rule successfully deployed.")
                                st.rerun()
                            except Exception as e:
                                logger.exception("Volume rule creation failed.")
                                st.error("Unable to save volume rule.")
                                st.code(str(e))

            # ------------------------------------------------
            # UNIQUENESS CREATION
            # ------------------------------------------------
            elif check_type == "uniqueness":
                with st.form("uniqueness_rule_form"):
                    key_col = st.selectbox("Business Key / Unique Identifier", available_columns, key="new_uniqueness_key")
                    use_date_filter = st.checkbox("Limit uniqueness check to a specific date column", value=True)

                    date_col = None
                    if use_date_filter:
                        date_col = st.selectbox("Date / Timestamp Column", available_columns, key="new_uniqueness_date")

                    severity = st.selectbox("Severity Level", ["CRITICAL", "WARNING", "INFO"], key="uniqueness_severity")
                    submit = st.form_submit_button("Deploy Uniqueness Rule", type="primary", use_container_width=True)

                    if submit:
                        config_payload = {"key_col": key_col}
                        if date_col:
                            config_payload["date_col"] = date_col

                        try:
                            save_rule(conn, selected_asset_id, check_type, config_payload, severity)
                            st.success("Uniqueness rule successfully deployed.")
                            st.rerun()
                        except Exception as e:
                            logger.exception("Uniqueness rule creation failed.")
                            st.error("Unable to save uniqueness rule.")
                            st.code(str(e))

    st.divider()

    # ========================================================
    # 11. EDIT EXISTING RULE
    # ========================================================
    st.subheader("✏️ Modify Existing Rule")
    st.markdown(
        '<div class="section-description">'
        'Update the configuration or severity of an existing rule.'
        '</div>',
        unsafe_allow_html=True
    )

    if rules_df.empty:
        st.info("Create a rule before attempting to modify one.")
    else:
        rule_options = {
            int(row["check_id"]): f'Rule #{row["check_id"]} | {row["table_name"]} | {row["check_type"]}'
            for _, row in rules_df.iterrows()
        }

        selected_rule_id = st.selectbox(
            "Select Rule to Modify",
            options=list(rule_options.keys()),
            format_func=lambda x: rule_options[x],
            key="edit_rule_selector"
        )

        selected_rule = rules_df[rules_df["check_id"] == selected_rule_id].iloc[0]

        try:
            current_config = parse_configuration(selected_rule["configuration_json"])
            edit_columns = get_table_columns(conn, selected_rule["schema_name"], selected_rule["table_name"])

            if not edit_columns:
                st.error("Unable to retrieve target dataset's columns.")
            else:
                edit_type = selected_rule["check_type"]

                with st.form(f"edit_rule_form_{selected_rule_id}"):
                    st.caption(f"Dataset: `{selected_rule['schema_name']}.{selected_rule['table_name']}`")
                    st.write(f"Validation type: **{edit_type.title()}**")

                    edit_severity = st.selectbox(
                        "Severity Level",
                        ["CRITICAL", "WARNING", "INFO"],
                        index=["CRITICAL", "WARNING", "INFO"].index(selected_rule["severity"]),
                        key=f"edit_sev_{selected_rule_id}"
                    )

                    # Freshness Editing
                    if edit_type == "freshness":
                        old_column = current_config.get("timestamp_col", edit_columns[0])
                        edit_column = st.selectbox(
                            "Timestamp Column",
                            edit_columns,
                            index=edit_columns.index(old_column) if old_column in edit_columns else 0,
                            key=f"edit_col_{selected_rule_id}"
                        )
                        edit_threshold = st.number_input(
                            "Maximum Allowed Hours",
                            min_value=1,
                            max_value=8760,
                            value=int(current_config.get("max_allowed_hours", 24)),
                            key=f"edit_hrs_{selected_rule_id}"
                        )
                        edit_config = {
                            "timestamp_col": edit_column,
                            "max_allowed_hours": int(edit_threshold)
                        }

                    # Volume Editing
                    elif edit_type == "volume":
                        old_column = current_config.get("date_col", edit_columns[0])
                        edit_column = st.selectbox(
                            "Date / Timestamp Column",
                            edit_columns,
                            index=edit_columns.index(old_column) if old_column in edit_columns else 0,
                            key=f"edit_vol_col_{selected_rule_id}"
                        )
                        edit_min = st.number_input(
                            "Minimum Expected Rows",
                            min_value=0,
                            value=int(current_config.get("min_rows", 100)),
                            key=f"edit_min_{selected_rule_id}"
                        )
                        edit_max = st.number_input(
                            "Maximum Expected Rows",
                            min_value=1,
                            value=int(current_config.get("max_rows", 10000)),
                            key=f"edit_max_{selected_rule_id}"
                        )
                        edit_config = {
                            "date_col": edit_column,
                            "min_rows": int(edit_min),
                            "max_rows": int(edit_max)
                        }

                    # Uniqueness Editing
                    elif edit_type == "uniqueness":
                        old_key = current_config.get("key_col", edit_columns[0])
                        edit_key = st.selectbox(
                            "Business Key Column",
                            edit_columns,
                            index=edit_columns.index(old_key) if old_key in edit_columns else 0,
                            key=f"edit_key_{selected_rule_id}"
                        )
                        old_date = current_config.get("date_col")
                        use_date = st.checkbox("Use date filtering", value=old_date is not None, key=f"edit_udate_{selected_rule_id}")

                        edit_date = None
                        if use_date:
                            edit_date = st.selectbox(
                                "Date / Timestamp Column",
                                edit_columns,
                                index=edit_columns.index(old_date) if old_date in edit_columns else 0,
                                key=f"edit_dcol_{selected_rule_id}"
                            )

                        edit_config = {"key_col": edit_key}
                        if edit_date:
                            edit_config["date_col"] = edit_date

                    else:
                        edit_config = current_config

                    save_changes = st.form_submit_button("Save Rule Changes", type="primary", use_container_width=True)

                    if save_changes:
                        if edit_type == "volume" and edit_config["max_rows"] < edit_config["min_rows"]:
                            st.error("Maximum rows cannot be lower than minimum rows.")
                        else:
                            try:
                                update_rule(conn, selected_rule_id, edit_config, edit_severity)
                                st.success(f"Rule #{selected_rule_id} updated successfully.")
                                st.rerun()
                            except Exception as e:
                                logger.exception("Rule update failed.")
                                st.error("Unable to update the selected rule.")
                                st.code(str(e))

        except Exception as e:
            logger.exception("Rule editor failed to load.")
            st.error("Unable to load the selected rule configuration.")
            st.code(str(e))

    st.divider()

    # ========================================================
    # 12. RULE DEPLOYMENT CONTROLS
    # ========================================================
    st.subheader("Rule Deployment Controls")
    st.markdown(
        '<div class="section-description">'
        'Enable or disable individual rules without deleting their configuration.'
        '</div>',
        unsafe_allow_html=True
    )

    if rules_df.empty:
        st.info("No rules available for deployment management.")
    else:
        deployment_options = {
            int(row["check_id"]): f'Rule #{row["check_id"]} | {row["table_name"]} | {row["check_type"]}'
            for _, row in rules_df.iterrows()
        }

        with st.form("rule_deployment_form"):
            deployment_id = st.selectbox(
                "Select Rule",
                options=list(deployment_options.keys()),
                format_func=lambda x: deployment_options[x]
            )

            current_rule = rules_df[rules_df["check_id"] == deployment_id].iloc[0]
            current_enabled = bool(current_rule["is_enabled"])

            new_status = st.radio(
                "Deployment Status",
                ["Enabled", "Disabled"],
                index=0 if current_enabled else 1,
                horizontal=True
            )

            update_deployment = st.form_submit_button("Update Rule Status", type="primary", use_container_width=True)

            if update_deployment:
                enabled = new_status == "Enabled"
                if enabled == current_enabled:
                    st.info("The selected rule already has this status.")
                else:
                    try:
                        update_rule_status(conn, deployment_id, enabled)
                        st.success(f"Rule #{deployment_id} successfully {new_status.lower()}.")
                        st.rerun()
                    except Exception as e:
                        logger.exception("Rule deployment update failed.")
                        st.error("Unable to update rule deployment status.")
                        st.code(str(e))

    st.divider()
    st.caption("DATA QUALITY FIREWALL · RULE CONFIGURATION ENGINE")

except Exception as e:
    logger.exception("Rule configuration page failed.")
    st.error("Unable to load the Rule Configuration Engine. Check database connection.")
    with st.expander("Technical details"):
        st.code(f"{type(e).__name__}: {e}")

finally:
    if conn is not None and conn.is_connected():
        conn.close()