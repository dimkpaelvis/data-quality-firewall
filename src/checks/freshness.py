import re
from datetime import datetime


def quote_identifier(identifier: str) -> str:
    """
    Validate and safely quote a SQL identifier.

    Parameterised SQL cannot be used for table or column names,
    so identifiers must be validated before interpolation.
    """
    if not identifier or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")

    return f"`{identifier}`"


def check_freshness(
    connection,
    schema_name: str,
    table_name: str,
    timestamp_col: str,
    max_allowed_hours: int = 24,
    target_time: datetime = None
) -> dict:
    """
    Evaluate whether the latest timestamp meets the freshness threshold.
    """
    cursor = None

    try:
        if max_allowed_hours < 0:
            raise ValueError("Freshness threshold cannot be negative.")

        schema = quote_identifier(schema_name)
        table = quote_identifier(table_name)
        column = quote_identifier(timestamp_col)

        if target_time is None:
            target_time = datetime.now()

        query = f"""
            SELECT MAX({column}) AS max_ts
            FROM {schema}.{table};
        """

        cursor = connection.cursor(dictionary=True)
        cursor.execute(query)

        result = cursor.fetchone()
        max_ts = result["max_ts"] if result else None

        # Empty table or NULL timestamps
        if max_ts is None:
            return {
                "check_type": "freshness",
                "status": "FAIL",
                "observed_value": "No valid timestamps found",
                "expected_value": f"<= {max_allowed_hours} hours old",
                "message": (
                    f"No valid timestamps were found in "
                    f"{schema_name}.{table_name}.{timestamp_col}."
                )
            }

        # Normalize timezone awareness to avoid TypeError on subtraction
        if hasattr(max_ts, "tzinfo") and max_ts.tzinfo is not None:
            max_ts = max_ts.replace(tzinfo=None)
        if hasattr(target_time, "tzinfo") and target_time.tzinfo is not None:
            target_time = target_time.replace(tzinfo=None)

        # Calculate age
        time_diff = target_time - max_ts
        hours_delay = time_diff.total_seconds() / 3600

        # Evaluate result
        if hours_delay < 0:
            status = "FAIL"
            message = (
                f"Future timestamp detected. Latest timestamp "
                f"is {abs(hours_delay):.2f} hours ahead of evaluation time."
            )
        elif hours_delay <= max_allowed_hours:
            status = "PASS"
            message = (
                f"Data is fresh. Latest record is "
                f"{hours_delay:.2f} hours old."
            )
        else:
            status = "FAIL"
            message = (
                f"Stale data detected. Latest record is "
                f"{hours_delay:.2f} hours old, exceeding the "
                f"{max_allowed_hours}-hour threshold."
            )

        return {
            "check_type": "freshness",
            "status": status,
            "observed_value": f"{hours_delay:.2f} hours old ({max_ts})",
            "expected_value": f"<= {max_allowed_hours} hours old",
            "message": message
        }

    except Exception as e:
        return {
            "check_type": "freshness",
            "status": "ERROR",
            "observed_value": "Execution Failure",
            "expected_value": f"<= {max_allowed_hours} hours old",
            "message": f"{type(e).__name__}: {str(e)}"
        }

    finally:
        if cursor:
            cursor.close()