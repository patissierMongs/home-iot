"""
Integrated Life Analytics Engine.

Pulls ALL data sources from InfluxDB, aligns by calendar day, and produces
cross-dimensional statistical analysis: correlations, feature importance,
anomaly detection, lagged effects, day clustering, trend detection.

This is the analytical core — not individual metric queries, but the
synthesis layer that finds relationships BETWEEN data sources.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .config import settings

log = logging.getLogger(__name__)

SEOUL = timezone(timedelta(hours=9))


class LifeAnalytics:
    """Unified analytics across all data sources."""

    def __init__(self):
        from influxdb_client import InfluxDBClient
        self._client = InfluxDBClient(
            url=settings.influx_url, token=settings.influx_token, org=settings.influx_org
        )
        self._query = self._client.query_api()
        self._df: pd.DataFrame | None = None  # cached daily matrix

    def close(self):
        self._client.close()

    # ================================================================
    # PHASE 1: Build unified daily matrix
    # ================================================================

    def _flux(self, query: str) -> list[dict]:
        tables = self._query.query(query)
        rows = []
        for table in tables:
            for record in table.records:
                v = record.values
                rows.append({
                    "time": v.get("_time"),
                    "value": v.get("_value"),
                    "field": v.get("_field"),
                    "measurement": v.get("_measurement"),
                    **{k: v2 for k, v2 in v.items()
                       if k not in ("_time", "_value", "_field", "_measurement", "result", "table", "_start", "_stop")},
                })
        return rows

    def build_daily_matrix(self, days: int = 365) -> pd.DataFrame:
        """
        Align ALL data sources by calendar day into a single DataFrame.
        Each row = one day. Columns = metrics from all sources.
        """
        daily: dict[str, dict[str, float]] = defaultdict(dict)
        bucket = settings.influx_bucket

        # --- Samsung Health ---
        # Heart rate (daily avg)
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="samsung_hr" and r._field=="bpm") |> aggregateWindow(every:1d,fn:mean,createEmpty:false)'):
            if r["time"]: daily[str(r["time"])[:10]]["hr_avg"] = float(r["value"])

        # Stress
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="samsung_stress" and r._field=="score" and r._value>0) |> aggregateWindow(every:1d,fn:mean,createEmpty:false)'):
            if r["time"]: daily[str(r["time"])[:10]]["stress"] = float(r["value"])

        # SpO2
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="samsung_spo2" and r._field=="spo2") |> aggregateWindow(every:1d,fn:mean,createEmpty:false)'):
            if r["time"]: daily[str(r["time"])[:10]]["spo2"] = float(r["value"])

        # Steps
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="samsung_steps" and r._field=="count") |> aggregateWindow(every:1d,fn:max,createEmpty:false)'):
            if r["time"]: daily[str(r["time"])[:10]]["steps"] = float(r["value"])

        # --- Sleep (SaA, daily aggregated) ---
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="sleep_session" and r._field=="hours" and r._value>=0) |> timeShift(duration:-12h) |> aggregateWindow(every:1d,fn:sum,createEmpty:false)'):
            if r["time"] and r["value"] and float(r["value"]) > 0:
                daily[str(r["time"])[:10]]["sleep_hours"] = float(r["value"])

        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="sleep_session" and r._field=="deep_sleep" and r._value>=0) |> timeShift(duration:-12h) |> aggregateWindow(every:1d,fn:mean,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["deep_sleep_pct"] = float(r["value"])

        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="sleep_session" and r._field=="cycles" and r._value>=0) |> timeShift(duration:-12h) |> aggregateWindow(every:1d,fn:sum,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["sleep_cycles"] = float(r["value"])

        # --- Google Fit daily (steps, calories, HR) ---
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="gfit_daily" and r._field=="calories") |> aggregateWindow(every:1d,fn:sum,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["calories"] = float(r["value"])

        # --- Environment ---
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="°C" and r.entity_id=="keompyuteo_onseubdo_temperature" and r._field=="value") |> aggregateWindow(every:1d,fn:mean,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["room_temp"] = float(r["value"])

        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="%" and r.entity_id=="keompyuteo_onseubdo_humidity" and r._field=="value") |> aggregateWindow(every:1d,fn:mean,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["room_humid"] = float(r["value"])

        # --- Location ---
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="timeline_visit" and r._field=="marker") |> aggregateWindow(every:1d,fn:count,createEmpty:false)'):
            if r["time"]: daily[str(r["time"])[:10]]["place_visits"] = float(r["value"])

        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="timeline_activity" and r._field=="distance_m") |> aggregateWindow(every:1d,fn:sum,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["travel_km"] = float(r["value"]) / 1000

        # --- Activity (PC) ---
        for r in self._flux(f'from(bucket:"{bucket}") |> range(start:-{days}d) |> filter(fn:(r)=>r._measurement=="activity_window" and r._field=="duration_s") |> aggregateWindow(every:1d,fn:sum,createEmpty:false)'):
            if r["time"] and r["value"]: daily[str(r["time"])[:10]]["pc_active_min"] = float(r["value"]) / 60

        # Build DataFrame
        df = pd.DataFrame.from_dict(daily, orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df = df.sort_index()

        # Add day-of-week
        df["dow"] = df.index.dayofweek  # 0=Mon, 6=Sun
        df["is_weekend"] = (df["dow"] >= 5).astype(int)

        self._df = df
        return df

    # ================================================================
    # PHASE 2: Cross-correlation analysis
    # ================================================================

    def correlation_matrix(self, min_pairs: int = 20) -> dict[str, Any]:
        """Full pairwise Pearson correlation with p-values. Only pairs with enough data."""
        df = self._ensure_df()
        numeric = df.select_dtypes(include=[np.number]).drop(columns=["dow", "is_weekend"], errors="ignore")
        cols = numeric.columns.tolist()

        results = []
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                x = numeric[cols[i]]
                y = numeric[cols[j]]
                mask = x.notna() & y.notna()
                n = mask.sum()
                if n < min_pairs:
                    continue
                r, p = stats.pearsonr(x[mask], y[mask])
                results.append({
                    "var1": cols[i], "var2": cols[j],
                    "r": round(r, 4), "p": round(p, 6), "n": int(n),
                    "strength": "strong" if abs(r) > 0.5 else "moderate" if abs(r) > 0.3 else "weak",
                    "significant": p < 0.05,
                })

        results.sort(key=lambda x: -abs(x["r"]))
        return {
            "total_pairs": len(results),
            "significant_pairs": sum(1 for r in results if r["significant"]),
            "top_correlations": results[:20],
            "columns": cols,
            "days_in_matrix": len(df),
        }

    # ================================================================
    # PHASE 3: Target predictor analysis
    # ================================================================

    def predict_target(self, target: str = "sleep_hours", top_n: int = 10) -> dict[str, Any]:
        """Which variables best predict the target? Includes lagged (yesterday's) effects."""
        df = self._ensure_df()
        if target not in df.columns:
            return {"error": "target not found", "available": df.columns.tolist()}

        numeric = df.select_dtypes(include=[np.number]).drop(columns=["dow", "is_weekend"], errors="ignore")
        y = numeric[target]

        results = []
        for col in numeric.columns:
            if col == target:
                continue

            # Same-day correlation
            x = numeric[col]
            mask = x.notna() & y.notna()
            n = mask.sum()
            if n < 15:
                continue
            r, p = stats.pearsonr(x[mask], y[mask])
            results.append({
                "predictor": col, "lag": 0,
                "r": round(r, 4), "p": round(p, 6), "n": int(n),
            })

            # Lagged (yesterday's predictor → today's target)
            x_lag = x.shift(1)
            mask_lag = x_lag.notna() & y.notna()
            n_lag = mask_lag.sum()
            if n_lag >= 15:
                r_lag, p_lag = stats.pearsonr(x_lag[mask_lag], y[mask_lag])
                if abs(r_lag) > 0.1:
                    results.append({
                        "predictor": col + " (t-1)", "lag": 1,
                        "r": round(r_lag, 4), "p": round(p_lag, 6), "n": int(n_lag),
                    })

        results.sort(key=lambda x: -abs(x["r"]))
        return {
            "target": target,
            "top_predictors": results[:top_n],
            "interpretation": self._interpret_predictors(target, results[:5]),
        }

    def _interpret_predictors(self, target: str, top: list) -> str:
        if not top:
            return "Not enough data."
        lines = []
        for p in top:
            direction = "increases" if p["r"] > 0 else "decreases"
            lag_note = " (next-day effect)" if p["lag"] == 1 else ""
            lines.append(
                f"{p['predictor']}{lag_note}: r={p['r']}, "
                f"when this goes up, {target} {direction} (p={p['p']})"
            )
        return "; ".join(lines)

    # ================================================================
    # PHASE 4: Anomaly detection
    # ================================================================

    def detect_anomalies(self, threshold_sigma: float = 2.0) -> dict[str, Any]:
        """Find days where any metric deviates >Nσ from mean."""
        df = self._ensure_df()
        numeric = df.select_dtypes(include=[np.number]).drop(columns=["dow", "is_weekend"], errors="ignore")

        anomalies = []
        for col in numeric.columns:
            series = numeric[col].dropna()
            if len(series) < 10:
                continue
            mean = series.mean()
            std = series.std()
            if std == 0:
                continue

            for idx, val in series.items():
                z = (val - mean) / std
                if abs(z) > threshold_sigma:
                    # What else happened that day?
                    day_data = df.loc[idx].dropna().to_dict()
                    anomalies.append({
                        "date": str(idx.date()),
                        "metric": col,
                        "value": round(float(val), 2),
                        "mean": round(float(mean), 2),
                        "z_score": round(float(z), 2),
                        "direction": "high" if z > 0 else "low",
                        "context": {k: round(float(v), 2) if isinstance(v, (int, float, np.floating)) else v
                                    for k, v in day_data.items() if k != col and k not in ("dow", "is_weekend")},
                    })

        anomalies.sort(key=lambda x: -abs(x["z_score"]))
        return {
            "threshold_sigma": threshold_sigma,
            "total_anomalies": len(anomalies),
            "top_anomalies": anomalies[:20],
        }

    # ================================================================
    # PHASE 5: Day clustering
    # ================================================================

    def cluster_days(self, n_clusters: int = 4) -> dict[str, Any]:
        """Cluster days into lifestyle types based on all metrics."""
        df = self._ensure_df()
        numeric = df.select_dtypes(include=[np.number]).drop(columns=["dow", "is_weekend"], errors="ignore")
        clean = numeric.dropna(thresh=len(numeric.columns) // 2)
        if len(clean) < n_clusters * 3:
            return {"error": "not enough complete days for clustering"}

        filled = clean.fillna(clean.median())
        scaler = StandardScaler()
        scaled = scaler.fit_transform(filled)

        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km.fit_predict(scaled)

        clusters = {}
        for i in range(n_clusters):
            mask = labels == i
            cluster_data = filled[mask]
            profile = {}
            for col in filled.columns:
                profile[col] = round(float(cluster_data[col].mean()), 2)
            clusters[f"cluster_{i}"] = {
                "count": int(mask.sum()),
                "pct": round(float(mask.sum()) / len(labels) * 100, 1),
                "profile": profile,
            }

        return {
            "n_clusters": n_clusters,
            "total_days": len(labels),
            "clusters": clusters,
        }

    # ================================================================
    # PHASE 6: Weekend vs weekday comparison
    # ================================================================

    def weekday_vs_weekend(self) -> dict[str, Any]:
        """Compare all metrics: weekdays vs weekends."""
        df = self._ensure_df()
        numeric = df.select_dtypes(include=[np.number]).drop(columns=["dow", "is_weekend"], errors="ignore")

        results = []
        for col in numeric.columns:
            wd = numeric.loc[df["is_weekend"] == 0, col].dropna()
            we = numeric.loc[df["is_weekend"] == 1, col].dropna()
            if len(wd) < 5 or len(we) < 5:
                continue
            t_stat, p_val = stats.ttest_ind(wd, we, equal_var=False)
            diff_pct = ((we.mean() - wd.mean()) / wd.mean() * 100) if wd.mean() != 0 else 0
            results.append({
                "metric": col,
                "weekday_avg": round(float(wd.mean()), 2),
                "weekend_avg": round(float(we.mean()), 2),
                "diff_pct": round(float(diff_pct), 1),
                "p_value": round(float(p_val), 4),
                "significant": p_val < 0.05,
            })

        results.sort(key=lambda x: -abs(x["diff_pct"]))
        return {"comparisons": results}

    # ================================================================
    # PHASE 7: Trend detection
    # ================================================================

    def detect_trends(self, window: int = 30) -> dict[str, Any]:
        """Detect improving/worsening trends over recent N days vs prior period."""
        df = self._ensure_df()
        numeric = df.select_dtypes(include=[np.number]).drop(columns=["dow", "is_weekend"], errors="ignore")

        if len(df) < window * 2:
            return {"error": "not enough data for trend detection"}

        recent = numeric.iloc[-window:]
        prior = numeric.iloc[-window * 2:-window]

        trends = []
        for col in numeric.columns:
            r_mean = recent[col].dropna().mean()
            p_mean = prior[col].dropna().mean()
            if pd.isna(r_mean) or pd.isna(p_mean) or p_mean == 0:
                continue
            change_pct = (r_mean - p_mean) / abs(p_mean) * 100
            trends.append({
                "metric": col,
                "recent_avg": round(float(r_mean), 2),
                "prior_avg": round(float(p_mean), 2),
                "change_pct": round(float(change_pct), 1),
                "direction": "improving" if change_pct > 5 else "declining" if change_pct < -5 else "stable",
            })

        trends.sort(key=lambda x: -abs(x["change_pct"]))
        return {"window_days": window, "trends": trends}

    # ================================================================
    # MASTER REPORT
    # ================================================================

    def generate_full_report(self, days: int = 365) -> dict[str, Any]:
        """Run ALL analyses and produce a comprehensive report."""
        log.info("Building daily matrix...")
        df = self.build_daily_matrix(days)
        log.info(f"Matrix: {len(df)} days x {len(df.columns)} columns")

        report = {
            "matrix_shape": {"days": len(df), "metrics": len(df.columns)},
            "columns": df.columns.tolist(),
            "date_range": {"from": str(df.index.min().date()), "to": str(df.index.max().date())},
            "coverage": {col: int(df[col].notna().sum()) for col in df.columns},
        }

        log.info("Computing correlations...")
        report["correlations"] = self.correlation_matrix()

        log.info("Finding sleep predictors...")
        report["sleep_predictors"] = self.predict_target("sleep_hours")

        log.info("Finding HR predictors...")
        report["hr_predictors"] = self.predict_target("hr_avg")

        log.info("Detecting anomalies...")
        report["anomalies"] = self.detect_anomalies()

        log.info("Clustering days...")
        report["clusters"] = self.cluster_days()

        log.info("Weekday vs weekend...")
        report["weekday_weekend"] = self.weekday_vs_weekend()

        log.info("Detecting trends...")
        report["trends_30d"] = self.detect_trends(30)
        report["trends_90d"] = self.detect_trends(90)

        return report

    # ================================================================
    # Helpers
    # ================================================================

    def _ensure_df(self) -> pd.DataFrame:
        if self._df is None:
            self.build_daily_matrix()
        return self._df


    # ================================================================
    # PHASE 8: Write results to InfluxDB (for Grafana)
    # ================================================================

    def publish_to_influxdb(self, report: dict[str, Any]) -> int:
        """Write analysis results back to InfluxDB so Grafana can query them natively."""
        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS

        write_api = self._client.write_api(write_options=SYNCHRONOUS)
        points = []
        now = datetime.now(timezone.utc)

        # Correlations
        for c in report.get("correlations", {}).get("top_correlations", []):
            p = (Point("analytics_correlation")
                 .tag("var1", c["var1"]).tag("var2", c["var2"])
                 .tag("significant", "yes" if c["significant"] else "no")
                 .tag("strength", c["strength"])
                 .field("r", float(c["r"]))
                 .field("p_value", float(c["p"]))
                 .field("n", int(c["n"]))
                 .field("abs_r", abs(float(c["r"])))
                 .time(now))
            points.append(p)

        # Sleep predictors
        for p_data in report.get("sleep_predictors", {}).get("top_predictors", []):
            p = (Point("analytics_predictor")
                 .tag("target", "sleep_hours")
                 .tag("predictor", p_data["predictor"])
                 .tag("lag", str(p_data["lag"]))
                 .field("r", float(p_data["r"]))
                 .field("p_value", float(p_data["p"]))
                 .field("n", int(p_data["n"]))
                 .field("abs_r", abs(float(p_data["r"])))
                 .time(now))
            points.append(p)

        # Anomalies
        for a in report.get("anomalies", {}).get("top_anomalies", []):
            try:
                ts = datetime.strptime(a["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except:
                continue
            p = (Point("analytics_anomaly")
                 .tag("metric", a["metric"])
                 .tag("direction", a["direction"])
                 .field("value", float(a["value"]))
                 .field("mean", float(a["mean"]))
                 .field("z_score", float(a["z_score"]))
                 .time(ts))
            points.append(p)

        # Trends
        for t in report.get("trends_30d", {}).get("trends", []):
            p = (Point("analytics_trend")
                 .tag("metric", t["metric"])
                 .tag("direction", t["direction"])
                 .tag("window", "30d")
                 .field("recent_avg", float(t["recent_avg"]))
                 .field("prior_avg", float(t["prior_avg"]))
                 .field("change_pct", float(t["change_pct"]))
                 .time(now))
            points.append(p)

        # Clusters
        for name, cl in report.get("clusters", {}).get("clusters", {}).items():
            p = (Point("analytics_cluster")
                 .tag("cluster", name)
                 .field("count", int(cl["count"]))
                 .field("pct", float(cl["pct"]))
                 .time(now))
            for k, v in cl.get("profile", {}).items():
                p = p.field("avg_" + k, float(v))
            points.append(p)

        # Weekday vs weekend
        for w in report.get("weekday_weekend", {}).get("comparisons", []):
            p = (Point("analytics_weekday_weekend")
                 .tag("metric", w["metric"])
                 .tag("significant", "yes" if w["significant"] else "no")
                 .field("weekday_avg", float(w["weekday_avg"]))
                 .field("weekend_avg", float(w["weekend_avg"]))
                 .field("diff_pct", float(w["diff_pct"]))
                 .field("p_value", float(w["p_value"]))
                 .time(now))
            points.append(p)

        # Write
        for i in range(0, len(points), 5000):
            write_api.write(bucket=settings.influx_bucket, record=points[i:i+5000])

        return len(points)


# === CLI runner ===
def main():
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    engine = LifeAnalytics()
    report = engine.generate_full_report(365)

    # Write to InfluxDB for Grafana
    n = engine.publish_to_influxdb(report)
    log.info(f"Published {n} analytics points to InfluxDB")

    engine.close()
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)[:3000])
    print(f"\n... ({n} points published to InfluxDB for Grafana)")


if __name__ == "__main__":
    main()
