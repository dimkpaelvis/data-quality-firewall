import os
from datetime import datetime, date
from dotenv import load_dotenv
import mysql.connector
from src.monitoring.runner import run_all_checks

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "user": os.getenv("MYSQL_USER"),
    "port": int(os.getenv("MYSQL_PORT", 4000)),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "ssl_disabled": False
}

conn = mysql.connector.connect(**DB_CONFIG)

# Simulate evaluation time
test_target_time = datetime(2026, 10, 27, 12, 0, 0)
test_target_date = date(2026, 10, 26)

print("--- RUNNING MONITORING ENGINE ---")
results = run_all_checks(conn, target_time=test_target_time, target_date=test_target_date)

for r in results:
    print(r)

conn.close()