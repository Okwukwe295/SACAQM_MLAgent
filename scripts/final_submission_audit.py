"""Verify frozen research results and assemble Chapter 5 figures from saved data."""

import json
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, balanced_accuracy_score, classification_report,
    confusion_matrix, roc_auc_score,
)

from scripts import agent_comparison as historical
from scripts import agent_controlled_comparison as pilot
from scripts import agent_eligibility_analysis as eligibility


ROOT = pilot.ROOT
VERSION = pilot.VERSION
COVERAGE = ROOT / "results/coverage" / VERSION
HISTORY = ROOT / "results/agent" / VERSION / "export_20261120"
WP02 = ROOT / "wp02"
FIGURES = ROOT / "results/report_figures"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_wp03():
    design = json.loads((pilot.MODEL / "design.json").read_text())
    require(pilot.digest(pilot.DATA / "events.csv") == design["dataset_hash"], "WP03 event file hash differs")
    events, predictions = pilot.load_cohort(design)
    recorded = pd.read_csv(pilot.MODEL / "metrics.csv").set_index(["arm", "model"])
    require(recorded.index.is_unique and set(recorded.index) == pilot.CONFIGURATIONS, "WP03 metric rows differ")
    for key, group in predictions.groupby(["arm", "model"]):
        y = group.label.eq("real").astype(int)
        y_hat = group.prediction
        tn, fp, fn, tp = confusion_matrix(y, y_hat, labels=[0, 1]).ravel()
        report = classification_report(y, y_hat, labels=[0, 1], output_dict=True, zero_division=0)
        metrics = dict(n=len(group), tn=tn, fp=fp, fn=fn, tp=tp,
                       balanced_accuracy=balanced_accuracy_score(y, y_hat),
                       roc_auc=roc_auc_score(y, group.score),
                       ap=average_precision_score(y, group.score))
        for i, label in enumerate(("fake", "real")):
            for metric in ("precision", "recall", "f1-score"):
                metrics[f"{label}_{metric}"] = report[str(i)][metric]
        np.testing.assert_allclose(recorded.loc[key, list(metrics)].astype(float), list(metrics.values()),
                                   rtol=1e-12, atol=1e-12, err_msg=str(key))
    return len(events), len(predictions)


def verify_agent_outputs(work):
    # The historical module roots its reads and writes together. Stage the exact archived inputs.
    archive = ROOT / "data/derived/agent_exports"
    stage = work / "historical"
    target = stage / archive.relative_to(ROOT)
    shutil.copytree(archive, target)
    for path in [pilot.DATA / "events.csv", pilot.MODEL / "design.json", pilot.MODEL / "predictions.csv",
                 COVERAGE / "manifest.json", COVERAGE / "monthly.csv",
                 ROOT / "sacaqm_dashboard_sensor_metadata.csv"]:
        destination = stage / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    original = historical.ingest.ROOT, historical.ingest.DERIVED, historical.ingest.RESULT, historical.OUT
    historical.ingest.ROOT = stage
    historical.ingest.DERIVED = stage / pilot.DATA.relative_to(ROOT)
    historical.ingest.RESULT = stage / COVERAGE.relative_to(ROOT)
    historical.OUT = stage / HISTORY.parent.relative_to(ROOT)
    try:
        historical.compare_exports()
        historical_output = historical.OUT / HISTORY.name
    finally:
        historical.ingest.ROOT, historical.ingest.DERIVED, historical.ingest.RESULT, historical.OUT = original
    history_files = sorted(historical_output.iterdir())
    for path in history_files:
        require(pilot.digest(path) == pilot.digest(HISTORY / path.name), f"Historical output differs: {path.name}")

    original_pilot_out, original_destination = pilot.OUT, eligibility.DESTINATION
    pilot.OUT = work / "controlled"
    eligibility.DESTINATION = work / "eligibility_analysis"
    try:
        pilot.run()
        eligibility.run()
        controlled_files = sorted(pilot.OUT.iterdir())
        analysis_files = sorted(eligibility.DESTINATION.iterdir())
        for actual, archive_dir in [(controlled_files, original_pilot_out), (analysis_files, original_destination)]:
            for path in actual:
                require(pilot.digest(path) == pilot.digest(archive_dir / path.name), f"Controlled output differs: {path.name}")
    finally:
        pilot.OUT, eligibility.DESTINATION = original_pilot_out, original_destination
    return len(history_files), len(controlled_files), len(analysis_files)


def save(fig, filename):
    fig.savefig(FIGURES / filename, dpi=300)
    plt.close(fig)


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=.25)


def grouped_metrics(table, labels, measures, filename, ylabel, ymax=1.05):
    fig, ax = plt.subplots(figsize=(8.5, 4.1), layout="constrained")
    x = np.arange(len(labels))
    width = .72 / len(measures)
    colors = ["#315b86", "#a34513", "#337361"]
    for i, (column, label) in enumerate(measures.items()):
        bars = ax.bar(x + (i - (len(measures) - 1) / 2) * width, table[column], width,
                      color=colors[i], label=label)
        ax.bar_label(bars, labels=[f"{value:.1%}" for value in table[column]], padding=3, fontsize=8)
    ax.set(xticks=x, xticklabels=labels, ylim=(0, ymax), ylabel=ylabel)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    style(ax)
    ax.legend(loc="upper left", ncols=len(measures), frameon=False)
    save(fig, filename)


def build_figures():
    FIGURES.mkdir(parents=True, exist_ok=True)
    monthly = pd.read_csv(COVERAGE / "monthly.csv").query("raw_rows > 0")
    months = pd.to_datetime(monthly.month).dt.strftime("%b")
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 5.3), sharex=True, layout="constrained")
    axes[0].bar(months, monthly.raw_rows / 1000, color="#315b86")
    axes[0].set_ylabel("Archived raw rows (thousands)")
    axes[1].bar(months, monthly.events, color="#337361")
    axes[1].set_ylabel("Reconstructed spike events")
    axes[1].set_xlabel("2026 event-onset or observation month (September through 25 Sep)")
    for ax in axes:
        style(ax)
    save(fig, "data_coverage_and_event_detection.png")

    manifest = json.loads((COVERAGE / "manifest.json").read_text())
    wp02 = json.loads((WP02 / "audit.json").read_text())
    fig, ax = plt.subplots(figsize=(9.5, 2.25), layout="constrained")
    ax.set_axis_off()
    stages = [
        ("Archived measurements", f"{wp02['raw_rows']:,} rows\n{wp02['raw_sensors']} sensor IDs"),
        ("Key and location checks", f"{wp02['extra_keys']:,} extra records\nat repeated keys\n"
         f"{wp02['conflicting_keys']} conflicts, {wp02['located_sensors']} located sensors"),
        ("Hourly reliability", "Five-minute bins\nAt least 10 occupied bins\nper hour"),
        ("Candidate detection", "z > 3 and rise ≥ 10 µg/m³\n" f"{wp02['events']:,} grouped events"),
    ]
    for i, (title, detail) in enumerate(stages):
        x = .125 + .25 * i
        ax.text(x, .68, title, transform=ax.transAxes, ha="center", weight="bold", color="#223d58")
        ax.text(x, .38, detail, transform=ax.transAxes, ha="center", va="center", fontsize=9)
        if i < len(stages) - 1:
            ax.text(x + .125, .68, "→", transform=ax.transAxes, ha="center", color="#627183")
    save(fig, "wp02_cleaning_and_event_detection_workflow.png")

    cohorts = [wp02["labels"], manifest["labels"]]
    fig, ax = plt.subplots(figsize=(8.2, 2.8), layout="constrained")
    left = np.zeros(2)
    for label, display, color in [("real", "Proxy-real", "#006a73"), ("fake", "Proxy-fake", "#9c460d"),
                                  ("uncertain", "Uncertain", "#627183")]:
        counts = [cohort[label] for cohort in cohorts]
        share = np.asarray(counts) / [sum(cohort.values()) for cohort in cohorts]
        bars = ax.barh(["WP02 (Mar–Jul)", "WP03 source (Mar–25 Sep)"], share, left=left,
                       color=color, label=display)
        ax.bar_label(bars, labels=[f"{n:,}" for n in counts], label_type="center", color="white")
        left += share
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set(xlim=(0, 1), xlabel="Share of reconstructed events")
    ax.spines[["top", "right"]].set_visible(False)
    fig.legend(loc="outside upper center", ncols=3, frameon=False)
    save(fig, "proxy_label_distributions_wp02_wp03.png")

    wp02_metrics = pd.read_csv(WP02 / "metrics.csv")
    grouped_metrics(wp02_metrics, ["Future baseline\n(n=141)", "Future tuned\n(n=141)", "Held sensor\n(n=558)"],
                    {"precision": "Precision", "recall": "Recall", "f1": "F1"},
                    "wp02_logistic_regression_proxy_real_metrics.png", "Proxy-real score")
    wp03_metrics = pd.read_csv(pilot.MODEL / "metrics.csv").pivot(index="model", columns="arm", values="balanced_accuracy")
    grouped_metrics(wp03_metrics, ["Boosting", "Random forest", "Logistic regression", "SVM"],
                    {"temporal": "Temporal only", "temporal_spatial": "Temporal + spatial"},
                    "wp03_model_feature_arm_balanced_accuracy.png", "Balanced accuracy against proxy labels")

    sensitivity = pd.read_csv(HISTORY / "clock_sensitivity.csv").sort_values("offset_hours")
    grouped_metrics(sensitivity.assign(
        all_share=sensitivity.unique_pairs / manifest["events"],
        reviewed_share=sensitivity.reviewed_pairs / manifest["events"],
    ), [f"{h:+d} h" if h else "0 h" for h in sensitivity.offset_hours],
        {"all_share": "Unique conditional pairs", "reviewed_share": "Reviewed subset"},
        "agent_historical_clock_sensitivity.png", "Share of reconstructed events", ymax=.038)

    for source, name in [
        (ROOT / "report/figures/confusion_matrices.png", "wp01_historical_confusion_matrices.png"),
        (ROOT / "report/figures/roc_pr_curves.png", "wp01_historical_roc_precision_recall.png"),
        (eligibility.DESTINATION / "pm25_distributions.png", "agent_eligibility_pm25_distributions.png"),
        (eligibility.DESTINATION / "model_comparison.png", "agent_eligibility_frozen_model_comparison.png"),
    ]:
        shutil.copyfile(source, FIGURES / name)


if __name__ == "__main__":
    events, predictions = verify_wp03()
    print(f"Verified WP03 metrics for {events} events and {predictions} predictions.", flush=True)
    work = Path(tempfile.mkdtemp(prefix="sacaqm-submission-audit-"))
    print(f"Isolated agent verification directory: {work}", flush=True)
    print("Reproduced historical, controlled and eligibility analysis files:", verify_agent_outputs(work))
    build_figures()
    print(f"Chapter 5 figures: {FIGURES}")
