import re
from datetime import date, datetime, time, timedelta


def quote_identifier(identifier: str) -> str:
    if not identifier or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")

    return f"`{identifier}`"


def check_volume(
    connection,
    schema_name: str,
    table_name: str,
    date_col: str,
    min_rows: int,
    max_rows: int,
    target_date: date = None
) -> dict:
    """
    Evaluate whether the daily row count falls within expected bounds.
    """
    cursor = None

    try:
        if min_rows < 0:
            raise ValueError("Minimum row count cannot be negative.")

        if max_rows < min_rows:
            raise ValueError("Maximum row count cannot be less than minimum row count.")

        # Normalize target_date input (handle None, datetime, or date)
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, datetime):
            target_date = target_date.date()

        schema = quote_identifier(schema_name)
        table = quote_identifier(table_name)
        column = quote_identifier(date_col)

        start_datetime = datetime.combine(target_date, time.min)
        end_datetime = start_datetime + timedelta(days=1)

        query = f"""
            SELECT COUNT(*) AS row_cnt
            FROM {schema}.{table}
            WHERE {column} >= %s
              AND {column} < %s;
        """

        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (start_datetime, end_datetime))

        result = cursor.fetchone()
        actual_rows = int(result["row_cnt"] if result else 0)

        # Evaluate volume bounds
        if min_rows <= actual_rows <= max_rows:
            status = "PASS"
            message = f"Volume is healthy. Found {actual_rows:,} rows on {target_date}."
        elif actual_rows < min_rows:
            status = "FAIL"
            message = (
                f"Low volume anomaly. Found {actual_rows:,} rows on {target_date}; "
                f"expected at least {min_rows:,}."
            )
        else:
            status = "FAIL"
            message = (
                f"High volume anomaly. Found {actual_rows:,} rows on {target_date}; "
                f"expected no more than {max_rows:,}."
            )

        return {
            "check_type": "volume",
            "status": status,
            "observed_value": f"{actual_rows:,} rows",
            "expected_value": f"Between {min_rows:,} and {max_rows:,} rows",
            "message": message
        }

    except Exception as e:
        return {
            "check_type": "volume",
            "status": "ERROR",
            "observed_value": "Execution Failure",
            "expected_value": f"Between {min_rows} and {max_rows} rows",
            "message": f"{type(e).__name__}: {str(e)}"
        }

    finally:
        if cursor:
            cursor.close()