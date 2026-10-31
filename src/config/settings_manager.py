import json
import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------
# DEFAULT SETTINGS
# --------------------------------------------------

DEFAULT_SETTINGS = {
    "email_alerts_enabled": True,
    "alert_recipient_email": "",
    "minimum_alert_severity": "CRITICAL",
    "slack_alerts_enabled": False,
    "auto_resolve_incidents": True,
}


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def _parse_setting_value(raw_value):
    """Safely deserialize JSON string setting values with plain-text fallback."""
    if not isinstance(raw_value, str):
        return raw_value

    try:
        return json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        # Fallback to returning raw string if value was not JSON-encoded
        return raw_value


# --------------------------------------------------
# LOAD SETTINGS
# --------------------------------------------------

def get_all_settings(connection):
    """
    Fetch all system settings from database merged with defaults.
    """
    settings = DEFAULT_SETTINGS.copy()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT setting_key, setting_value
            FROM system_settings
        """)
        rows = cursor.fetchall()

        for row in rows:
            key = row["setting_key"]
            if key in settings:
                settings[key] = _parse_setting_value(row["setting_value"])

        return settings
    finally:
        cursor.close()


# --------------------------------------------------
# GET ONE SETTING
# --------------------------------------------------

def get_setting(connection, setting_key, default=None):
    """
    Retrieve a single setting value. Falls back to DEFAULT_SETTINGS
    if available, then the explicit default argument.
    """
    fallback_default = DEFAULT_SETTINGS.get(setting_key, default)
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT setting_value
            FROM system_settings
            WHERE setting_key = %s
        """, (setting_key,))

        row = cursor.fetchone()
        if not row:
            return fallback_default

        parsed = _parse_setting_value(row["setting_value"])
        return parsed if parsed is not None else fallback_default
    finally:
        cursor.close()


# --------------------------------------------------
# SAVE ONE SETTING
# --------------------------------------------------

def save_setting(connection, setting_key, setting_value):
    """
    Persist or update a single setting key-value pair.
    """
    if setting_key not in DEFAULT_SETTINGS:
        raise ValueError(f"Unknown system setting: {setting_key}")

    serialized_value = json.dumps(setting_value)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO system_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);
        """, (setting_key, serialized_value))

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


# --------------------------------------------------
# SAVE MULTIPLE SETTINGS
# --------------------------------------------------

def save_all_settings(connection, settings):
    """
    Batch update multiple system settings in a single atomic transaction.
    """
    unknown_keys = set(settings) - set(DEFAULT_SETTINGS)
    if unknown_keys:
        raise ValueError(f"Unknown settings: {', '.join(unknown_keys)}")

    params = [
        (key, json.dumps(value))
        for key, value in settings.items()
    ]

    cursor = connection.cursor()

    try:
        cursor.executemany("""
            INSERT INTO system_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);
        """, params)

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()