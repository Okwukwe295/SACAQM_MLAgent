"""Offline eligibility audit for the frozen WP03 held-out cohort."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.ingest import digest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "20260301_20261119T2200Z_v1"
MODEL = ROOT / "results/wp03" / VERSION / "local_through_september"
DATA = ROOT / "data/derived" / VERSION
MANIFEST = ROOT / "results/coverage" / VERSION / "manifest.json"
STATIONS = ROOT / "data/derived/agent_exports/station_sensor_map.csv"
OUT = ROOT / "results/agent/controlled_pilot"
KEY = ["sensor", "start"]
THRESHOLD = 60.0
BLOCKED = {"665034ff099ab1a7fbcfbd2a", "665036ec099ab1a7fbcfbd30"}
SEED = "sacaqm-controlled-pilot-v1"
CONFIGURATIONS = {
    (arm, model)
    for arm in ("temporal", "temporal_spatial")
    for model in ("logistic", "forest", "boosting", "svm")
}
REPLAY_COLUMNS = [
    "event_id", "station_id", "agent_decision", "agent_confidence", "replay_status"
]
BLOCKER = "Historical tool context incomplete and Moonshot LLM calls require approval."


def read_verified(path, expected, hashes):
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"Frozen input hash mismatch: {path}")
    hashes[path.relative_to(ROOT).as_posix()] = actual


def load_cohort(design):
    partition = pd.read_csv(MODEL / "partition.csv", parse_dates=["start", "decision", "evidence_start"])
    predictions = pd.read_csv(MODEL / "predictions.csv", parse_dates=["start", "end"])
    events = pd.read_csv(DATA / "events.csv", parse_dates=["start", "end", "decision", "evidence_start"])
    held_out = partition.loc[partition.partition.eq("test")].merge(
        events, on=KEY + ["decision", "evidence_start"], validate="one_to_one"
    )
    if (
        partition.duplicated(KEY).any()
        or design["test"] != 297
        or partition.partition.eq("test").sum() != len(held_out)
        or len(held_out) != 297
        or not held_out.label.isin(["real", "fake"]).all()
        or not held_out.start.ge(pd.Timestamp(design["boundary"])).all()
        or not held_out.decision.le(pd.Timestamp("2026-10-01")).all()
    ):
        raise ValueError("Unexpected WP03 held-out partition")
    joined = predictions.merge(held_out[KEY + ["end", "label"]], validate="many_to_one")
    configs = set(zip(predictions.arm, predictions.model))
    if (
        len(joined) != len(predictions)
        or len(predictions) != len(held_out) * len(CONFIGURATIONS)
        or predictions.duplicated(KEY + ["arm", "model"]).any()
        or configs != CONFIGURATIONS
        or not predictions.prediction.isin([0, 1]).all()
    ):
        raise ValueError("Frozen predictions do not cover the held-out partition and all configurations")
    return held_out, predictions


def station_identity(sensor, mapping, metadata):
    matches = mapping.loc[mapping.sensor_id.eq(sensor)]
    if len(matches) != 1:
        return "", "sensor_mapping_missing_or_ambiguous"
    station = matches.iloc[0]
    if station.station_id in BLOCKED:
        return station.station_id, "blocked_station"
    if mapping.station_id.eq(station.station_id).sum() != 1:
        return station.station_id, "station_has_multiple_sensors"
    site = metadata.loc[metadata.sensor_id.eq(sensor), ["latitude", "longitude"]].drop_duplicates()
    coordinates = ["latitude", "longitude"]
    if len(site) != 1 or not (site.iloc[0] - station[coordinates]).abs().le(0.0001).all():
        return station.station_id, "station_coordinates_missing_or_inconsistent"
    return station.station_id, ""


def load_windows(paths, events):
    needed = pd.MultiIndex.from_tuples(
        [(event.sensor, hour) for event in events.itertuples()
         for hour in pd.date_range(event.start, event.end, freq="h")],
        names=["sensor_id", "hour"],
    ).unique()
    parts = []
    for path in paths:
        raw = pd.read_csv(path, usecols=["sensor_id", "timestamp", "pm2p5"], dtype={"sensor_id": str})
        raw.sensor_id = raw.sensor_id.str.strip().str.upper()
        raw.timestamp = pd.to_datetime(raw.timestamp, utc=True).dt.tz_localize(None)
        raw.pm2p5 = pd.to_numeric(raw.pm2p5, errors="coerce")
        raw["hour"] = raw.timestamp.dt.floor("h")
        parts.append(raw.loc[pd.MultiIndex.from_frame(raw[["sensor_id", "hour"]]).isin(needed)])
    rows = pd.concat(parts)
    return dict(tuple(rows.groupby(["sensor_id", "hour"])))


def assess_hours(sensor, start, end, windows, hourly):
    """Find the first observed eligible hour under a fixed hour-end schedule."""
    missing = []
    for hour in pd.date_range(start, end, freq="h"):
        key = (sensor, hour)
        raw = windows.get(key)
        if raw is None or not hourly.get(key, False):
            missing.append("missing_raw_or_frozen_spike_hour")
            continue
        timestamp = raw.timestamp.max()
        values = raw.loc[raw.timestamp.eq(timestamp), "pm2p5"].drop_duplicates()
        if len(values) != 1 or not 0 <= values.iloc[0] < float("inf"):
            missing.append("missing_or_conflicting_latest_pm25")
            continue
        value = values.iloc[0]
        if value >= THRESHOLD:
            return {
                "eligibility": "eligible",
                "eligibility_reason": "latest_point_at_or_above_threshold",
                "trigger_hour": hour,
                "evaluation_end_exclusive": hour + pd.Timedelta(hours=1),
                "latest_reading_time": timestamp,
                "latest_pm25": value,
                "earlier_unresolved_hours": len(missing),
            }
    if missing:
        return {"eligibility": "missing_data", "eligibility_reason": "|".join(sorted(set(missing)))}
    return {"eligibility": "ineligible", "eligibility_reason": "all_latest_points_below_threshold"}


def select_events(eligibility):
    pool = eligibility.loc[eligibility.eligibility.eq("eligible")].copy()
    pool["selection_hash"] = pool.event_id.map(
        lambda event_id: hashlib.sha256(f"{SEED}|{event_id}".encode()).hexdigest()
    )
    pool = pool.sort_values(["selection_hash", "event_id"])
    balanced = pool.groupby("proxy_label", sort=False).head(15)
    fill = pool.loc[~pool.index.isin(balanced.index)].head(30 - len(balanced))
    selected = pd.concat([balanced, fill]).sort_values(["selection_hash", "event_id"])
    return selected.assign(selection_rank=range(1, len(selected) + 1))


def run():
    manifest = json.loads(MANIFEST.read_text())
    design = json.loads((MODEL / "design.json").read_text())
    paths = [MANIFEST, STATIONS, *(MODEL / f for f in ("design.json", "partition.csv", "predictions.csv"))]
    hashes = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    read_verified(DATA / "events.csv", design["dataset_hash"], hashes)
    hourly_path = DATA / "hourly.csv.gz"
    read_verified(hourly_path, manifest["outputs"][hourly_path.name], hashes)
    raw_paths = []
    for name, expected in manifest["inputs"].items():
        read_verified(ROOT / name, expected, hashes)
        if name.startswith("raw_data/"):
            raw_paths.append(ROOT / name)

    events, predictions = load_cohort(design)
    raw_windows = load_windows(raw_paths, events)
    hourly = pd.read_csv(hourly_path, usecols=["sensor", "timestamp", "spike"], parse_dates=["timestamp"])
    hourly = hourly.set_index(["sensor", "timestamp"], verify_integrity=True).spike.eq(True)
    mapping = pd.read_csv(STATIONS, dtype={"station_id": str, "sensor_id": str}).drop_duplicates()
    metadata = pd.read_csv(ROOT / "sacaqm_dashboard_sensor_metadata.csv", dtype={"sensor_id": str})
    for frame in (mapping, metadata):
        frame.sensor_id = frame.sensor_id.str.strip().str.upper()

    records = []
    for event in events.sort_values(KEY).itertuples():
        station, issue = station_identity(event.sensor, mapping, metadata)
        if issue:
            status = "ineligible" if issue == "blocked_station" else "missing_data"
            audit = {"eligibility": status, "eligibility_reason": issue}
        else:
            audit = assess_hours(event.sensor, event.start, event.end, raw_windows, hourly)
        records.append({
            "event_id": f"{event.sensor}|{event.start.isoformat()}",
            "sensor": event.sensor, "station_id": station, "start": event.start, "end": event.end,
            "proxy_label": event.label, **audit,
        })
    audit = pd.DataFrame(records).reindex(columns=[
        "event_id", "sensor", "station_id", "start", "end", "proxy_label", "eligibility",
        "eligibility_reason", "trigger_hour", "evaluation_end_exclusive", "latest_reading_time",
        "latest_pm25", "earlier_unresolved_hours",
    ])
    selected = select_events(audit)
    replay = pd.DataFrame(columns=REPLAY_COLUMNS)
    comparison = predictions.drop(columns=["end", "label"]).merge(audit, on=KEY, validate="many_to_one")
    comparison["selected"] = comparison.event_id.isin(selected.event_id)
    comparison["replay_status"] = comparison.selected.map({True: "blocked", False: "not_selected"})
    comparison["replay_limitation"] = comparison.selected.map({True: BLOCKER, False: ""})
    comparison[["agent_decision", "agent_confidence", "decision_disagreement"]] = pd.NA
    counts = audit.eligibility.value_counts().reindex(["eligible", "ineligible", "missing_data"], fill_value=0)
    summary = {
        "held_out_events": len(audit),
        "eligibility_basis": "Conditional on frozen clock, archived station identity and an available isolated monitor slot",
        "eligibility_counts": {key: int(value) for key, value in counts.items()},
        "eligibility_reasons": audit.eligibility_reason.value_counts().to_dict(),
        "selected_events": len(selected),
        "selected_by_proxy_label": selected.proxy_label.value_counts().to_dict(),
        "selection": f"SHA-256 of {SEED}|event_id; first 15 of each proxy class, then fill in hash order to 30",
        "replayed_events": len(replay),
        "genuine_agent_decisions_obtained": False,
        "agent_invoked": False,
        "comparison_rows": len(comparison),
        "blocker": BLOCKER,
        "input_sha256": hashes,
    }
    for name, expected in hashes.items():
        read_verified(ROOT / name, expected, hashes)
    OUT.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUT / "eligibility.csv", index=False)
    selected.to_csv(OUT / "selected_events.csv", index=False)
    replay.to_csv(OUT / "replay_results.csv", index=False)
    comparison.sort_values(KEY + ["arm", "model"]).to_csv(OUT / "comparison.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
