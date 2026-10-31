import os
import sys
import time
import signal
import logging
import threading

from datetime import datetime
import mysql.connector
from dotenv import load_dotenv

# ============================================================
# PROJECT PATH RESOLUTION
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.monitoring.runner import run_all_checks

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

IS_DEV = os.getenv("ENVIRONMENT", "production").lower() == "development"
MIN_INTERVAL = 1 if IS_DEV else 10

INTERVAL_SECONDS = max(
    MIN_INTERVAL,
    int(os.getenv("CHECK_INTERVAL_SECONDS", 3600))
)

RUNNING = True

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("data_quality_firewall")

# ============================================================
# SIGNAL HANDLERS (THREAD-SAFE)
# ============================================================

def handle_shutdown_signal(signum, frame):
    global RUNNING
    logger.info("Termination signal received (%s). Stopping daemon cleanly...", signum)
    RUNNING = False

# Only attach signal handlers if running on the main thread
if threading.current_thread() is threading.main_thread():
    try:
        signal.signal(signal.SIGINT, handle_shutdown_signal)
        signal.signal(signal.SIGTERM, handle_shutdown_signal)
    except (ValueError, AttributeError):
        pass

# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
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
# MONITORING CYCLE
# ============================================================

def execute_monitoring_cycle():
    conn = None
    cycle_start = time.monotonic()

    try:
        conn = get_db_connection()
        results = run_all_checks(conn)

        pass_count = sum(1 for r in results if r["status"] == "PASS")
        fail_count = sum(1 for r in results if r["status"] == "FAIL")
        error_count = sum(1 for r in results if r["status"] == "ERROR")

        duration = time.monotonic() - cycle_start

        logger.info(
            "Monitoring cycle completed | Total: %s | Passed: %s | Failed: %s | Errors: %s | Duration: %.2f seconds",
            len(results), pass_count, fail_count, error_count, duration
        )
        return results

    except Exception:
        logger.exception("Monitoring cycle failed.")
        return []

    finally:
        if conn is not None and conn.is_connected():
            conn.close()

# ============================================================
# SCHEDULER DAEMON
# ============================================================

def start_daemon():
    logger.info("=" * 60)
    logger.info("DATA QUALITY FIREWALL — AUTOMATED MONITORING ONLINE")
    logger.info("Monitoring interval: %s seconds", INTERVAL_SECONDS)
    logger.info("=" * 60)

    while RUNNING:
        cycle_start = time.monotonic()
        logger.info("Starting monitoring cycle.")

        execute_monitoring_cycle()

        if not RUNNING:
            break

        execution_time = time.monotonic() - cycle_start
        sleep_time = max(0.0, INTERVAL_SECONDS - execution_time)

        logger.info("Next monitoring cycle in %.2f seconds.", sleep_time)

        sleep_chunk = 0.5
        slept = 0.0
        while RUNNING and slept < sleep_time:
            time.sleep(min(sleep_chunk, sleep_time - slept))
            slept += sleep_chunk

    logger.info("Scheduler daemon shut down complete.")

# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":
    start_daemon()