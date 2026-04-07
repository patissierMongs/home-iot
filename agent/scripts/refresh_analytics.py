#!/usr/bin/env python3
"""Run analytics engine and publish results to InfluxDB for Grafana.
Schedule: daily via cron or systemd timer.
  0 6 * * * cd /home/yuyu/home-iot/agent && uv run python scripts/refresh_analytics.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
from home_iot.analytics import LifeAnalytics

engine = LifeAnalytics()
report = engine.generate_full_report(365)
n = engine.publish_to_influxdb(report)
engine.close()

corr = report["correlations"]["significant_pairs"]
anom = report["anomalies"]["total_anomalies"]
logging.info(f"Done: {n} points published. {corr} significant correlations, {anom} anomalies.")
