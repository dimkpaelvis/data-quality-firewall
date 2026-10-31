# 🛡️ Data Quality Firewall

An enterprise-grade, lightweight data observability engine designed to intercept stale, anomalous, or duplicate data before it reaches production analytics or downstream BI dashboards.

---

## 🏗️ Architecture & Features

* **Modular Rules Engine (`src/checks/`)**: Decoupled Python guard functions validating data freshness, volume drops/spikes, and primary key uniqueness.
* **Metadata & Audit Layer (`TiDB / MySQL`)**: Persists execution metrics (`check_results`) and manages deduplicated incident lifecycles (`incidents`).
* **Automated Daemon (`scheduler.py`)**: Continuously runs configured rules on a custom interval with automated connection management.
* **Transactional Email Alerts (`email_notifier.py`)**: Instant HTML email notifications dispatched directly to team leads when critical rules fail.
* **Real-time Dashboard (`Streamlit`)**: Complete administrative suite with auto-refreshing fragments for system health, rule configuration, triage workflows, and execution history.

---

## 🛠️ Tech Stack

* **Language**: Python 3.10+
* **Database / Metadata Storage**: TiDB Cloud (MySQL-compatible)
* **Frontend UI**: Streamlit
* **Core Libraries**: `mysql-connector-python`, `pandas`, `python-dotenv`

---

## 🚀 Quickstart Guide

### 1. Clone & Setup Environment
```bash
git clone [https://github.com/your-username/data-quality-firewall.git](https://github.com/your-username/data-quality-firewall.git)
cd data-quality-firewall
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt