
import json
import uuid
import logging

from datetime import datetime, date

from src.alerts.email_notifier import send_incident_alert
from src.checks.freshness import check_freshness
from src.checks.volume import check_volume
from src.checks.uniqueness import check_uniqueness
from src.config.settings_manager import get_all_settings

logger = logging.getLogger(__name__)


def run_all_checks(
    connection,
    target_time: datetime = None,
    target_date: date = None
) -> list:
    """
    Execute enabled data quality checks.

    Responsibilities:
    1. Retrieve active rules.
    2. Execute individual checks.
    3. Persist check results.
    4. Manage incident lifecycle.
    5. Dispatch notifications on incident state transitions.
    """

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    logger.info("Starting monitoring run %s", run_id)

    cursor = connection.cursor(dictionary=True)
    outcomes = []

    # ----------------------------------------------------
    # 1. LOAD SETTINGS ONCE PER RUN
    # ----------------------------------------------------

    try:
        settings = get_all_settings(connection)

    except Exception:
        logger.exception(
            "Unable to load system settings. "
            "Using safe fallback settings for this run."
        )

        # Continue monitoring, but fail closed for notifications
        # and automatic incident resolution.
        settings = {
            "email_alerts_enabled": False,
            "alert_recipient_email": "",
            "minimum_alert_severity": "CRITICAL",
            "slack_alerts_enabled": False,
            "auto_resolve_incidents": False
        }

    auto_resolve = bool(
        settings.get("auto_resolve_incidents", True)
    )

    try:

        # ====================================================
        # 2. FETCH ENABLED QUALITY RULES
        # ====================================================

        query = """
            SELECT
                qc.check_id,
                qc.check_type,
                qc.configuration_json,
                qc.severity,
                ma.asset_id,
                ma.schema_name,
                ma.table_name
            FROM quality_checks qc
            INNER JOIN monitored_assets ma
                ON qc.asset_id = ma.asset_id
            WHERE qc.is_enabled = TRUE
              AND ma.is_active = TRUE
            ORDER BY qc.check_id ASC;
        """

        cursor.execute(query)
        active_checks = cursor.fetchall()

        # ====================================================
        # 3. EXECUTE EACH CHECK
        # ====================================================

        for check in active_checks:

            check_id = check["check_id"]
            check_type = check["check_type"]
            schema_name = check["schema_name"]
            table_name = check["table_name"]
            severity = check["severity"]

            result = None

            try:

                # --------------------------------------------
                # PARSE CONFIGURATION
                # --------------------------------------------

                config = check["configuration_json"]

                if isinstance(config, str):
                    config = json.loads(config)

                if not isinstance(config, dict):
                    raise ValueError(
                        "Rule configuration must be a JSON object."
                    )

                # --------------------------------------------
                # ROUTE TO CHECK MODULE
                # --------------------------------------------

                if check_type == "freshness":

                    result = check_freshness(
                        connection=connection,
                        schema_name=schema_name,
                        table_name=table_name,
                        timestamp_col=config["timestamp_col"],
                        max_allowed_hours=config.get(
                            "max_allowed_hours", 24
                        ),
                        target_time=target_time
                    )

                elif check_type == "volume":

                    result = check_volume(
                        connection=connection,
                        schema_name=schema_name,
                        table_name=table_name,
                        date_col=config["date_col"],
                        min_rows=config.get("min_rows", 0),
                        max_rows=config.get("max_rows", 999999),
                        target_date=target_date
                    )

                elif check_type == "uniqueness":

                    result = check_uniqueness(
                        connection=connection,
                        schema_name=schema_name,
                        table_name=table_name,
                        key_col=config["key_col"],
                        date_col=config.get("date_col"),
                        target_date=target_date
                    )

                else:
                    raise ValueError(
                        f"Unsupported check type: {check_type}"
                    )

            except Exception as e:

                logger.exception(
                    "Failed to execute check ID %s",
                    check_id
                )

                result = {
                    "check_type": check_type,
                    "status": "ERROR",
                    "observed_value": "Execution Failure",
                    "expected_value": "Valid check execution",
                    "message": f"{type(e).__name__}: {str(e)}"
                }

            # --------------------------------------------
            # ENRICH RESULT METADATA
            # --------------------------------------------

            result.update({
                "check_id": check_id,
                "run_id": run_id,
                "asset_id": check["asset_id"],
                "schema_name": schema_name,
                "table_name": table_name,
                "severity": severity
            })

            # =================================================
            # 4. PERSIST CHECK RESULT
            # =================================================

            try:

                insert_result_sql = """
                    INSERT INTO check_results (
                        check_id,
                        run_id,
                        status,
                        observed_value,
                        expected_value,
                        message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s);
                """

                cursor.execute(
                    insert_result_sql,
                    (
                        check_id,
                        run_id,
                        result["status"],
                        result["observed_value"],
                        result["expected_value"],
                        result["message"]
                    )
                )

                # =============================================
                # 5. INCIDENT LIFECYCLE MANAGEMENT
                # =============================================

                dedup_key = f"{table_name}_check_{check_id}"

                cursor.execute(
                    """
                    SELECT status
                    FROM incidents
                    WHERE deduplication_key = %s;
                    """,
                    (dedup_key,)
                )

                existing_incident = cursor.fetchone()

                previous_status = (
                    existing_incident["status"]
                    if existing_incident else None
                )

                notification_event = None

                # --------------------------------------------
                # FAILURE OR EXECUTION ERROR
                # --------------------------------------------

                if result["status"] in ("FAIL", "ERROR"):

                    cursor.execute(
                        """
                        INSERT INTO incidents (
                            check_id,
                            deduplication_key,
                            status
                        )
                        VALUES (%s, %s, 'OPEN')

                        ON DUPLICATE KEY UPDATE
                            last_detected_at = CURRENT_TIMESTAMP,
                            status = IF(
                                status = 'RESOLVED',
                                'OPEN',
                                status
                            ),
                            resolved_at = NULL;
                        """,
                        (check_id, dedup_key)
                    )

                    # Notify only for a new incident or a reopen.
                    # An acknowledged incident remains acknowledged
                    # and does not generate repeated notifications.

                    if previous_status is None or previous_status == "RESOLVED":
                        notification_event = "OPEN"

                # --------------------------------------------
                # SUCCESS
                # --------------------------------------------

                elif result["status"] == "PASS":

                    if (
                        auto_resolve
                        and previous_status in ("OPEN", "ACKNOWLEDGED")
                    ):

                        cursor.execute(
                            """
                            UPDATE incidents
                            SET
                                status = 'RESOLVED',
                                resolved_at = CURRENT_TIMESTAMP
                            WHERE deduplication_key = %s
                              AND status IN ('OPEN', 'ACKNOWLEDGED');
                            """,
                            (dedup_key,)
                        )

                        notification_event = "RESOLVED"

                # =============================================
                # 6. COMMIT DATABASE TRANSACTION
                # =============================================

                connection.commit()

                # =============================================
                # 7. DISPATCH NOTIFICATIONS POST-COMMIT
                # =============================================

                full_table_identifier = (
                    f"{schema_name}.{table_name}"
                )

                if notification_event == "OPEN":

                    send_incident_alert(
                        table_name=full_table_identifier,
                        check_type=check_type,
                        observed_value=result["observed_value"],
                        expected_value=result["expected_value"],
                        message=result["message"],
                        severity=severity,
                        incident_status="OPEN",
                        settings=settings
                    )

                elif notification_event == "RESOLVED":

                    send_incident_alert(
                        table_name=full_table_identifier,
                        check_type=check_type,
                        observed_value=result["observed_value"],
                        expected_value=result["expected_value"],
                        message=(
                            "The monitoring rule has passed again. "
                            "The previously active incident has been resolved."
                        ),
                        severity=severity,
                        incident_status="RESOLVED",
                        settings=settings
                    )

                outcomes.append(result)

            except Exception:

                connection.rollback()

                logger.exception(
                    "Failed to persist result for check ID %s",
                    check_id
                )

                outcomes.append({
                    "check_id": check_id,
                    "run_id": run_id,
                    "table_name": table_name,
                    "check_type": check_type,
                    "severity": severity,
                    "status": "ERROR",
                    "observed_value": "Persistence Failure",
                    "expected_value": "Successful result persistence",
                    "message": "The check result could not be saved."
                })

        return outcomes

    except Exception:

        connection.rollback()

        logger.exception(
            "Monitoring run %s failed.",
            run_id
        )

        return outcomes

    finally:
        cursor.close()
