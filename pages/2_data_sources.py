import os
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
    page_title="Data Quality Firewall | Data Sources",
    page_icon="🔌",
    layout="wide"
)

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================
# 2. VISUAL DESIGN
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
        min-height: 115px;
    }

    div[data-testid="stMetricLabel"] {
        color: #A0A9B8;
        font-size: 13px;
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

    missing_vars = [
        var for var in required_vars
        if not os.getenv(var)
    ]

    if missing_vars:
        raise ValueError(
            f"Missing database configuration: {', '.join(missing_vars)}"
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
# 4. DATABASE QUERY HELPERS
# ============================================================

def fetch_dataframe(conn, query, params=None):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        records = cursor.fetchall()
        return pd.DataFrame(records)
    finally:
        cursor.close()


def validate_table_exists(conn, schema_name, table_name):
    """
    Validate that a table or view exists in the connected
    database environment (case-insensitive).
    """
    query = """
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE LOWER(table_schema) = LOWER(%s)
          AND LOWER(table_name) = LOWER(%s)
          AND table_type IN ('BASE TABLE', 'VIEW');
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (schema_name, table_name))
        result = cursor.fetchone()
        return result["table_count"] > 0
    finally:
        cursor.close()


def table_already_registered(conn, source_id, schema_name, table_name):
    """Prevent duplicate dataset registrations."""
    query = """
        SELECT COUNT(*) AS existing_count
        FROM monitored_assets
        WHERE source_id = %s
          AND LOWER(schema_name) = LOWER(%s)
          AND LOWER(table_name) = LOWER(%s);
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (source_id, schema_name, table_name))
        result = cursor.fetchone()
        return result["existing_count"] > 0
    finally:
        cursor.close()


def update_asset_status(conn, asset_id, active):
    """Activate or deactivate an existing monitored asset."""
    query = """
        UPDATE monitored_assets
        SET is_active = %s
        WHERE asset_id = %s;
    """
    cursor = conn.cursor()
    try:
        cursor.execute(query, (active, asset_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ============================================================
# 5. PAGE HEADER
# ============================================================

st.title("🔌 Data Sources & Monitored Assets")
st.caption(
    "Manage registered data sources, control monitored datasets, "
    "and configure the assets protected by your Data Quality Firewall."
)
st.divider()


# ============================================================
# 6. MAIN APPLICATION
# ============================================================

conn = None

try:
    conn = get_db_connection()

    # --------------------------------------------------------
    # FETCH DATA SOURCES & MONITORED ASSETS
    # --------------------------------------------------------
    sources_query = """
        SELECT
            source_id,
            source_name,
            source_type,
            is_active,
            created_at
        FROM data_sources
        ORDER BY source_id DESC;
    """
    sources_df = fetch_dataframe(conn, sources_query)

    assets_query = """
        SELECT
            ma.asset_id,
            ma.source_id,
            ds.source_name,
            ma.schema_name,
            ma.table_name,
            ma.expected_cadence,
            ma.is_active,
            ma.created_at
        FROM monitored_assets ma
        INNER JOIN data_sources ds ON ma.source_id = ds.source_id
        ORDER BY ma.asset_id DESC;
    """
    assets_df = fetch_dataframe(conn, assets_query)

    # Normalise boolean fields
    if not assets_df.empty:
        assets_df["is_active"] = assets_df["is_active"].fillna(False).astype(bool)

    if not sources_df.empty:
        sources_df["is_active"] = sources_df["is_active"].fillna(False).astype(bool)

    # --------------------------------------------------------
    # CALCULATE METRICS
    # --------------------------------------------------------
    total_sources = len(sources_df)
    active_sources = int(sources_df["is_active"].sum()) if not sources_df.empty else 0

    total_assets = len(assets_df)
    active_assets = int(assets_df["is_active"].sum()) if not assets_df.empty else 0
    inactive_assets = total_assets - active_assets

    # ========================================================
    # 7. CONNECTION ENVIRONMENT
    # ========================================================
    st.subheader("Connection Environment")
    st.markdown(
        '<div class="section-description">'
        'Current database connection used by the monitoring application.'
        '</div>',
        unsafe_allow_html=True
    )

    host = os.getenv("MYSQL_HOST", "Not configured")
    database = os.getenv("MYSQL_DATABASE", "Not configured")
    port = os.getenv("MYSQL_PORT", "4000")

    env_col1, env_col2, env_col3 = st.columns(3)
    with env_col1:
        st.metric("Connection Status", "CONNECTED", delta="Database session established")
    with env_col2:
        st.metric("Database", database)
    with env_col3:
        st.metric("Port", port)

    st.caption(f"Configured host: {host} · Credentials managed via environment variables.")
    st.info(
        "This connection represents the application's configured "
        "TiDB/MySQL environment. Registered source records are "
        "metadata entries and do not independently establish "
        "connections to other databases."
    )
    st.divider()

    # ========================================================
    # 8. REGISTERED DATA SOURCES
    # ========================================================
    st.subheader("Registered Data Sources")
    st.markdown(
        '<div class="section-description">'
        'View the data systems registered in your monitoring environment.'
        '</div>',
        unsafe_allow_html=True
    )

    source_col1, source_col2, source_col3 = st.columns(3)
    with source_col1:
        st.metric("Total Sources", total_sources)
    with source_col2:
        st.metric("Active Sources", active_sources)
    with source_col3:
        st.metric("Registered Assets", total_assets)

    if sources_df.empty:
        st.info("No data sources have been registered yet.")
    else:
        display_sources = sources_df.rename(
            columns={
                "source_id": "Source ID",
                "source_name": "Source Name",
                "source_type": "Source Type",
                "is_active": "Active",
                "created_at": "Registered At"
            }
        )

        st.dataframe(
            display_sources,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Source ID": st.column_config.NumberColumn("Source ID", format="%d"),
                "Source Name": "Data Source",
                "Source Type": "Technology",
                "Active": st.column_config.CheckboxColumn("Active", disabled=True),
                "Registered At": st.column_config.DatetimeColumn("Registration Date", format="DD MMM YYYY, HH:mm")
            }
        )

    st.divider()

    # ========================================================
    # 9. MONITORED ASSET INVENTORY
    # ========================================================
    st.subheader("Monitored Assets")
    st.markdown(
        '<div class="section-description">'
        'Explore and manage the datasets currently protected by the firewall.'
        '</div>',
        unsafe_allow_html=True
    )

    metric1, metric2, metric3 = st.columns(3)
    with metric1:
        st.metric("Total Datasets", total_assets)
    with metric2:
        st.metric("Active Datasets", active_assets, delta="Included in monitoring")
    with metric3:
        st.metric("Inactive Datasets", inactive_assets, delta="Excluded from monitoring", delta_color="off")

    if assets_df.empty:
        st.info("No monitored datasets have been registered.")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            search_asset = st.text_input("Search datasets", placeholder="Search table or schema...", key="asset_search")
        with filter_col2:
            status_filter = st.selectbox("Asset Status", ["All", "Active", "Inactive"])
        with filter_col3:
            cadence_options = ["All"] + sorted(assets_df["expected_cadence"].dropna().unique().tolist())
            cadence_filter = st.selectbox("Expected Frequency", cadence_options)

        filtered_assets = assets_df.copy()

        if search_asset.strip():
            search_value = search_asset.strip().lower()
            filtered_assets = filtered_assets[
                filtered_assets.apply(
                    lambda row: (
                        search_value in str(row["table_name"]).lower()
                        or search_value in str(row["schema_name"]).lower()
                        or search_value in str(row["source_name"]).lower()
                    ),
                    axis=1
                )
            ]

        if status_filter == "Active":
            filtered_assets = filtered_assets[filtered_assets["is_active"]]
        elif status_filter == "Inactive":
            filtered_assets = filtered_assets[~filtered_assets["is_active"]]

        if cadence_filter != "All":
            filtered_assets = filtered_assets[filtered_assets["expected_cadence"] == cadence_filter]

        st.caption(f"Displaying {len(filtered_assets)} of {total_assets} datasets.")

        if filtered_assets.empty:
            st.info("No datasets match your current filters.")
        else:
            display_assets = filtered_assets[
                ["asset_id", "source_name", "schema_name", "table_name", "expected_cadence", "is_active", "created_at"]
            ].rename(
                columns={
                    "asset_id": "Asset ID",
                    "source_name": "Data Source",
                    "schema_name": "Database / Schema",
                    "table_name": "Table Name",
                    "expected_cadence": "Expected Frequency",
                    "is_active": "Active",
                    "created_at": "Registered At"
                }
            )

            st.dataframe(
                display_assets,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Asset ID": st.column_config.NumberColumn("Asset ID", format="%d"),
                    "Data Source": "Source",
                    "Database / Schema": "Database / Schema",
                    "Table Name": "Dataset",
                    "Expected Frequency": "Cadence",
                    "Active": st.column_config.CheckboxColumn("Monitoring Active", disabled=True),
                    "Registered At": st.column_config.DatetimeColumn("Registration Date", format="DD MMM YYYY, HH:mm")
                }
            )

    st.divider()

    # ========================================================
    # 10. ASSET ACTIVATION MANAGEMENT
    # ========================================================
    st.subheader("Asset Monitoring Controls")
    st.markdown(
        '<div class="section-description">'
        'Temporarily include or exclude registered datasets from monitoring.'
        '</div>',
        unsafe_allow_html=True
    )

    if assets_df.empty:
        st.info("Register a dataset before using asset controls.")
    else:
        asset_labels = {
            row["asset_id"]: f'{row["schema_name"]}.{row["table_name"]} ({"Active" if row["is_active"] else "Inactive"})'
            for _, row in assets_df.iterrows()
        }

        with st.form("asset_status_form"):
            selected_asset_id = st.selectbox(
                "Select Dataset",
                options=list(asset_labels.keys()),
                format_func=lambda x: asset_labels[x]
            )

            selected_asset = assets_df[assets_df["asset_id"] == selected_asset_id].iloc[0]
            current_status = bool(selected_asset["is_active"])

            desired_status = st.radio(
                "Monitoring Status",
                options=["Active", "Inactive"],
                index=0 if current_status else 1,
                horizontal=True
            )

            status_submitted = st.form_submit_button(
                "Update Monitoring Status",
                type="primary",
                use_container_width=True
            )

            if status_submitted:
                new_status = desired_status == "Active"
                if new_status == current_status:
                    st.info("The selected dataset already has this status.")
                else:
                    try:
                        update_asset_status(conn, selected_asset_id, new_status)
                        st.success(f"Monitoring status updated for `{selected_asset['table_name']}`.")
                        st.rerun()
                    except Exception as e:
                        logger.exception("Asset status update failed.")
                        st.error("Unable to update the dataset status.")
                        with st.expander("Technical details"):
                            st.code(f"{type(e).__name__}: {e}")

    st.divider()

    # ========================================================
    # 11. REGISTER NEW MONITORED DATASET
    # ========================================================
    st.subheader("➕ Register New Monitored Dataset")
    st.markdown(
        '<div class="section-description">'
        'Add an existing database table to the firewall monitoring environment.'
        '</div>',
        unsafe_allow_html=True
    )

    if sources_df.empty:
        st.warning("You need at least one registered data source before registering monitored datasets.")
    else:
        active_source_df = sources_df[sources_df["is_active"]]

        if active_source_df.empty:
            st.warning("There are no active data sources available. Activate a source before registering a dataset.")
        else:
            source_options = {
                row["source_id"]: row["source_name"]
                for _, row in active_source_df.iterrows()
            }

            with st.form("register_table_form"):
                form_col1, form_col2 = st.columns(2)
                with form_col1:
                    selected_source_id = st.selectbox(
                        "Target Data Source",
                        options=list(source_options.keys()),
                        format_func=lambda x: source_options[x]
                    )
                    input_schema = st.text_input(
                        "Database / Schema Name",
                        value=os.getenv("MYSQL_DATABASE", ""),
                        help="Enter the database containing the target dataset."
                    )
                with form_col2:
                    input_table = st.text_input("Table Name", placeholder="e.g. customer_orders")
                    cadence = st.selectbox("Expected Data Arrival Frequency", options=["hourly", "daily", "weekly"], index=1)

                st.caption("The selected table must already exist and be accessible through the configured database connection.")
                st.divider()

                submitted = st.form_submit_button("➕ Register Monitored Dataset", type="primary", use_container_width=True)

                if submitted:
                    clean_schema = input_schema.strip()
                    clean_table = input_table.strip()

                    # Prevent leading digits or invalid SQL identifier characters
                    identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

                    if not clean_schema or not clean_table:
                        st.error("Database/schema and table name are required.")
                    elif not identifier_pattern.fullmatch(clean_schema) or not identifier_pattern.fullmatch(clean_table):
                        st.error("Use valid database and table identifiers (must start with a letter/underscore).")
                    else:
                        try:
                            if not validate_table_exists(conn, clean_schema, clean_table):
                                st.error(f"Dataset `{clean_schema}.{clean_table}` could not be found in the connected database.")
                            elif table_already_registered(conn, selected_source_id, clean_schema, clean_table):
                                st.warning("This dataset is already registered under the selected source.")
                            else:
                                insert_query = """
                                    INSERT INTO monitored_assets (source_id, schema_name, table_name, expected_cadence, is_active)
                                    VALUES (%s, %s, %s, %s, TRUE);
                                """
                                cursor = conn.cursor()
                                try:
                                    cursor.execute(insert_query, (selected_source_id, clean_schema, clean_table, cadence))
                                    conn.commit()
                                except Exception:
                                    conn.rollback()
                                    raise
                                finally:
                                    cursor.close()

                                st.success(f"Successfully registered `{clean_schema}.{clean_table}`.")
                                st.rerun()

                        except Exception as e:
                            logger.exception("Failed to register monitored dataset.")
                            st.error("The dataset could not be registered.")
                            with st.expander("Technical error details"):
                                st.code(f"{type(e).__name__}: {e}")

    st.divider()
    st.caption("DATA QUALITY FIREWALL · DATA SOURCE MANAGEMENT")

except Exception as e:
    logger.exception("Data Sources page failed to load.")
    st.error("Unable to load the Data Sources page. Verify the database connection and configuration.")
    with st.expander("Technical error details"):
        st.code(f"{type(e).__name__}: {e}")

finally:
    if conn is not None and conn.is_connected():
        conn.close()