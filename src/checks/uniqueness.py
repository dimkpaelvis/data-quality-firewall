import re
from datetime import date, datetime, time, timedelta


def quote_identifier(identifier: str) -> str:
    if not identifier or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")

    return f"`{identifier}`"


def check_uniqueness(
    connection,
    schema_name: str,
    table_name: str,
    key_col: str,
    date_col: str = None,
    target_date: date = None
) -> dict:
    """
    Evaluate uniqueness of a business key.

    Reports duplicate excess rows and NULL key values separately.
    """
    cursor = None

    try:
        schema = quote_identifier(schema_name)
        table = quote_identifier(table_name)
        key = quote_identifier(key_col)

        where_clause = ""
        params = ()

        # Normalize date boundary in Python if date_col is specified
        if date_col:
            if target_date is None:
                target_date = date.today()
            elif isinstance(target_date, datetime):
                target_date = target_date.date()

            start_datetime = datetime.combine(target_date, time.min)
            end_datetime = start_datetime + timedelta(days=1)

            date_column = quote_identifier(date_col)
            where_clause = f"""
                WHERE {date_column} >= %s
                  AND {date_column} < %s
            """
            params = (start_datetime, end_datetime)

        query = f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT({key}) AS non_null_rows,
                COUNT(DISTINCT {key}) AS distinct_keys
            FROM {schema}.{table}
            {where_clause};
        """

        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)

        result = cursor.fetchone()

        total_rows = int(result["total_rows"] if result and result["total_rows"] else 0)
        non_null_rows = int(result["non_null_rows"] if result and result["non_null_rows"] else 0)
        distinct_keys = int(result["distinct_keys"] if result and result["distinct_keys"] else 0)

        duplicate_count = non_null_rows - distinct_keys
        null_count = total_rows - non_null_rows

        # Evaluate result
        if duplicate_count == 0 and null_count == 0:
            status = "PASS"
            message = (
                f"Uniqueness is healthy. No duplicate or NULL "
                f"keys found in `{key_col}`."
            )
        else:
            status = "FAIL"
            message = (
                f"Uniqueness violation detected in `{key_col}`. "
                f"Found {duplicate_count:,} duplicate excess rows "
                f"and {null_count:,} NULL keys."
            )

        return {
            "check_type": "uniqueness",
            "status": status,
            "observed_value": (
                f"{duplicate_count:,} duplicate excess rows; "
                f"{null_count:,} NULL keys"
            ),
            "expected_value": "0 duplicate excess rows and 0 NULL keys",
            "message": message
        }

    except Exception as e:
        return {
            "check_type": "uniqueness",
            "status": "ERROR",
            "observed_value": "Execution Failure",
            "expected_value": "0 duplicate excess rows and 0 NULL keys",
            "message": f"{type(e).__name__}: {str(e)}"
        }

    finally:
        if cursor:
            cursor.close()