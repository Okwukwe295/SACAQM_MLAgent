"""Quantify trigger selection and score frozen WP03 predictions by eligibility."""

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, ScalarFormatter
import numpy as np
import pandas as pd

from scripts.agent_controlled_comparison import DATA, KEY, MODEL, OUT, ROOT, digest, load_cohort


DESTINATION = OUT / "eligibility_analysis"
GROUPS = {"eligible": "Conditionally eligible", "ineligible": "Ineligible",
          "missing_data": "Unresolved station identity"}
COLORS = {"eligible": "#006a73", "ineligible": "#9c460d", "missing_data": "#627183"}
ARMS = {"temporal": "Temporal only", "temporal_spatial": "Temporal + spatial"}
METRICS = ["balanced_accuracy", "precision", "recall", "f1"]
CONCENTRATIONS = {"peak": "Event peak", "event_mean": "Event mean"}


def join_eligibility(events, eligibility):
    columns = KEY + ["end", "label"]
    cohort = events.merge(
        eligibility.rename(columns={"proxy_label": "label"}),
        on=columns, how="outer", validate="one_to_one", indicator=True,
    )
    if (
        not cohort["_merge"].eq("both").all()
        or not cohort.eligibility.isin(GROUPS).all()
        or not cohort.event_id.is_unique
        or not cohort.event_id.eq(cohort.sensor + "|" + cohort.start.dt.strftime("%Y-%m-%dT%H:%M:%S")).all()
    ):
        raise ValueError("Eligibility does not match the frozen cohort by event key, end and proxy label")
    return cohort.drop(columns="_merge")


def score(group):
    actual = group.label.eq("real")
    predicted = group.prediction.eq(1)
    tp = int((actual & predicted).sum())
    tn = int((~actual & ~predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    recall = tp / (tp + fn) if tp + fn else np.nan
    return {
        "n_events": len(group), "proxy_real": tp + fn, "proxy_fake": tn + fp,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "balanced_accuracy": (recall + tn / (tn + fp)) / 2 if tp + fn and tn + fp else np.nan,
        "precision": tp / (tp + fp) if tp + fn and tp + fp else np.nan,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fn else np.nan,
    }


def performance(predictions, cohort):
    joined = predictions.merge(cohort[KEY + ["eligibility"]], on=KEY, validate="many_to_one")
    rows = []
    for (group, model, arm), samples in joined.groupby(["eligibility", "model", "arm"]):
        if len(samples) != cohort.eligibility.eq(group).sum() or samples.duplicated(KEY).any():
            raise ValueError(f"Prediction coverage differs in {group}/{model}/{arm}")
        if group != "missing_data":
            rows.append({"eligibility": group, "model": model, "arm": arm, **score(samples)})
    metrics = pd.DataFrame(rows)
    eligible = metrics.loc[metrics.eligibility.eq("eligible")].set_index(["arm", "model"])
    deltas = (eligible.loc["temporal_spatial", METRICS] - eligible.loc["temporal", METRICS])
    return metrics, deltas.reset_index()


def distribution_figure(cohort, path):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.9), sharey=True, layout="constrained")
    for ax, (column, title) in zip(axes, CONCENTRATIONS.items()):
        for group, label in GROUPS.items():
            values = np.sort(cohort.loc[cohort.eligibility.eq(group), column].to_numpy())
            ax.step(np.r_[values[0], values], np.arange(len(values) + 1) / len(values),
                    where="post", label=f"{label} (n={len(values)})", color=COLORS[group],
                    linestyle=":" if group == "missing_data" else "-", linewidth=2)
        ax.set(xscale="log", ylim=(0, 1.03), title=title, xlabel="PM2.5 (µg/m³, log scale)")
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Cumulative share of events")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=3, frameon=False)
    fig.savefig(path, dpi=300)
    plt.close(fig)


def performance_figure(metrics, path):
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6), sharex=True, sharey=True, layout="constrained")
    models = sorted(metrics.model.unique())
    labels = {"boosting": "Boosting", "forest": "Random forest", "logistic": "Logistic regression", "svm": "SVM"}
    colors = ["#315b86", "#a34513"]
    for ax, group in zip(axes, ("eligible", "ineligible")):
        ordered = metrics.loc[metrics.eligibility.eq(group)].pivot(
            index="model", columns="arm", values="balanced_accuracy"
        ).reindex(models)
        for row, (first, second) in enumerate(ordered[list(ARMS)].itertuples(index=False, name=None)):
            ax.plot([first, second], [row, row], color="#aab5bf", linewidth=2, zorder=1)
        for (arm, label), color, marker in zip(ARMS.items(), colors, ("o", "D")):
            ax.scatter(ordered[arm], range(len(models)), color=color, marker=marker, label=label, zorder=2)
        n = metrics.loc[metrics.eligibility.eq(group), "n_events"].iloc[0]
        ax.set(title=f"{GROUPS[group]} (n={n})", xlabel="Balanced accuracy against proxy labels",
               xlim=(0.45, 1.01))
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.axvline(0.5, color="#808080", linestyle=":", linewidth=1)
        ax.grid(axis="x", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(range(len(models)), [labels[model] for model in models])
    axes[0].invert_yaxis()
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=2, frameon=False)
    fig.savefig(path, dpi=300)
    plt.close(fig)


def markdown_table(frame):
    heading = "| " + " | ".join(frame.columns) + " |"
    rule = "| " + " | ".join(["---"] * len(frame.columns)) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join([heading, rule, *rows])


def write_report(summary, classes, metrics, deltas):
    rates = lambda value: f"{value:.1%}" if pd.notna(value) else "—"
    percentage_points = lambda value: f"{100 * value:+.1f}" if pd.notna(value) else "—"
    summary = summary.assign(cohort_share=summary.cohort_share.map(rates))
    classes = classes.assign(eligible_share=classes.eligible_share.map(rates))
    display = metrics[["eligibility", "model", "arm", "n_events", *METRICS]].copy()
    display.eligibility = display.eligibility.map(GROUPS)
    display.arm = display.arm.map(ARMS)
    display[METRICS] = display[METRICS].apply(lambda column: column.map(rates))
    changes = deltas.copy()
    changes[METRICS] = changes[METRICS].apply(lambda column: column.map(percentage_points))
    sections = [
        "# Trigger eligibility in the frozen WP03 cohort",
        "## Eligibility summary\n\n" + markdown_table(summary.rename(columns={
            "status": "Trigger eligibility", "n_events": "Events", "cohort_share": "Share of cohort"
        })),
        "## Eligibility by proxy class\n\n" + markdown_table(classes.rename(columns={
            "label": "Proxy class", "eligible": "Conditionally eligible", "ineligible": "Ineligible",
            "missing_data": "Unresolved", "total": "Total", "eligible_share": "Eligible share of class"
        })),
        "![Distribution of event peak and mean PM2.5](pm25_distributions.png)\n\n"
        "Concentrations are computed from frozen WP03 hourly event summaries. The trigger uses a latest raw point.",
        "## Frozen model performance by trigger eligibility\n\n" + markdown_table(display.rename(columns={
            "eligibility": "Trigger eligibility", "model": "Model", "arm": "Features", "n_events": "Events",
            "balanced_accuracy": "Balanced accuracy", "precision": "Precision", "recall": "Recall", "f1": "F1"
        })),
        "![Frozen model balanced accuracy by trigger eligibility](model_comparison.png)",
        "## Spatial feature change within eligible events\n\n"
        "Temporal + spatial minus temporal only, in percentage points. Both arms use the same 83 events.\n\n"
        + markdown_table(changes.rename(columns={"model": "Model", "balanced_accuracy": "Balanced accuracy",
                                                  "precision": "Precision", "recall": "Recall", "f1": "F1"})),
        "Proxy-real is the positive class. The three unresolved cases remain in the descriptive cohort. "
        "Trigger eligibility describes entry into a conditional investigation. These model scores measure "
        "agreement with proxy labels, and spatial evidence also contributes to those labels. "
        "The subgroup comparisons are descriptive and include no agent decisions.",
    ]
    (DESTINATION / "REPORT.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def run():
    design_path = MODEL / "design.json"
    eligibility_path = OUT / "eligibility.csv"
    pilot_summary = OUT / "summary.json"
    inputs = [design_path, MODEL / "partition.csv", MODEL / "predictions.csv",
              DATA / "events.csv", eligibility_path, pilot_summary]
    hashes = {path.relative_to(ROOT).as_posix(): digest(path) for path in inputs}
    pilot = json.loads(pilot_summary.read_text())
    for path in inputs[:4]:
        name = path.relative_to(ROOT).as_posix()
        if hashes[name] != pilot["input_sha256"][name]:
            raise ValueError(f"Frozen WP03 input differs from the pilot: {name}")
    design = json.loads(design_path.read_text())
    events, predictions = load_cohort(design)
    audit = pd.read_csv(eligibility_path, parse_dates=["start", "end"])
    cohort = join_eligibility(events, audit)
    if cohort.eligibility.value_counts().to_dict() != pilot["eligibility_counts"]:
        raise ValueError("Eligibility status counts differ from the pilot summary")
    classes = pd.crosstab(cohort.label, cohort.eligibility).reindex(index=["real", "fake"], columns=GROUPS, fill_value=0)
    counts = classes.sum()
    summary = pd.DataFrame({"status": [*GROUPS.values(), "All held-out events"],
                            "n_events": [*counts, len(cohort)]})
    summary["cohort_share"] = summary.n_events / len(cohort)
    classes["total"] = classes.sum(axis=1)
    classes["eligible_share"] = classes.eligible / classes.total
    concentration_rows = []
    for group in GROUPS:
        for column in CONCENTRATIONS:
            values = cohort.loc[cohort.eligibility.eq(group), column]
            if values.empty or not (np.isfinite(values) & values.gt(0)).all():
                raise ValueError(f"Expected positive frozen PM2.5 values for {group}/{column}")
            low, q1, med, q3, high = values.quantile([0, .25, .5, .75, 1])
            concentration_rows.append(dict(eligibility=group, measure=column, n_events=len(values),
                                           minimum=low, q1=q1, median=med, q3=q3, maximum=high))
    metrics, deltas = performance(predictions, cohort)
    if any(digest(ROOT / name) != before for name, before in hashes.items()):
        raise ValueError("Input file changed while the analysis was running")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    tables = {"eligibility_summary": summary, "eligibility_by_class": classes.reset_index(),
              "pm25_summary": pd.DataFrame(concentration_rows), "model_performance": metrics,
              "eligible_spatial_deltas": deltas}
    for name, table in tables.items():
        table.to_csv(DESTINATION / f"{name}.csv", index=False)
    distribution_figure(cohort, DESTINATION / "pm25_distributions.png")
    performance_figure(metrics, DESTINATION / "model_comparison.png")
    write_report(summary, classes.reset_index(), metrics, deltas)
    verification = {"unique_events": len(cohort), "prediction_rows": len(predictions),
                    "unique_events_by_status": counts.to_dict(), "scored_model_subgroups": len(metrics),
                    "input_sha256": hashes}
    (DESTINATION / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    return verification


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
