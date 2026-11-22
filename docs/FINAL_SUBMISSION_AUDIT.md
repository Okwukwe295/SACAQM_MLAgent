# SACAQM final submission audit

22 November 2026 · Johannesburg

**Verdict: BLOCKED.** The frozen numerical results passed the checks below. The manuscript is still a working draft and the distribution package requires a file and data-access review.

## Execution and reproducibility

Run from the repository root using the project virtual environment. [Reproduction instructions](REPRODUCE.md) include the isolated WP01 and WP02 commands.

| Experiment | Original execution | Verification performed |
| --- | --- | --- |
| WP01 historical candidate-hour Logistic Regression | Extract `46cb986:model.ipynb` with `git show` and execute its 25 code cells in an isolated folder with `labelled_spike_candidates.csv`. The PowerShell command is in the reproduction guide. | Checked the Git archive, candidate export, stored notebook outputs and recorded manuscript table. This audit used archived results. The historical reproduction boundary starts at the derived candidate CSV. |
| WP02 event-level Logistic Regression | In a fresh directory with the five March–July monthly inputs, metadata and review cases, run `wp02_prepare.py`, `wp02_model.py` and `wp02_review.py` with the project Python interpreter. | All 19 manifest entries matched. Eight regenerated CSVs and the copied review-case CSV matched the archive byte for byte. The audit JSON also matched. The blinded review PDF regenerated successfully and has a different file hash from the archived PDF. Its visual equivalence was not assessed. |
| WP03 four-model ablation | `.\.venv\Scripts\python.exe -m scripts.wp03_compare --version local_through_september` | Recomputed support, confusion matrices, balanced accuracy, per-class precision/recall/F1, ROC AUC and average precision from all 2,376 frozen predictions. All eight rows matched the saved metrics within numerical tolerance. This check did not refit the models. |
| Historical agent linkage | `.\.venv\Scripts\python.exe -m scripts.agent_comparison` | Reproduced eight published CSV/JSON artifacts byte for byte in an isolated copy of the local archives. No application server or database access. |
| Controlled trigger audit | `.\.venv\Scripts\python.exe -m scripts.agent_controlled_comparison` | Reproduced five generated artifacts byte for byte in an isolated output folder, including the header-only replay file. |
| Trigger eligibility analysis | `.\.venv\Scripts\python.exe -m scripts.agent_eligibility_analysis` | Reproduced nine generated artifacts byte for byte in isolation, including both figures, the subgroup metrics and the 297-event join verification. |

The WP02 rerun used the recorded Python and package versions. Preserve `wp02/run_manifest.json` with the benchmark. For offline checks without rewriting the original agent or model results, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.final_submission_audit
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

All 12 SACAQM tests passed. The separate AGENT_AI integration test is outside this repository's suite and can call an external service. The audit used local files throughout.

## Verified numerical results

- **WP01.** 2,040 candidate-hour rows, with 730 strictly rule-labelled rows (431 real, 299 fake) across 677 distinct sensor events, verified against the candidate export. The chronological baseline used 183 test rows, with TN/FP/FN/TP of 74/10/47/52, real precision 0.839, recall 0.525, F1 0.646, ROC AUC 0.800 and AP 0.850. The tuned model's real F1 was 0.654. The 46-sensor LOSO evaluation pooled 730 predictions and recorded real F1 0.703. Preserve the row-level unit and the historical protocol limitations.
- **WP02 cleaning and labels.** 2,061,501 source rows from 83 sensors, 26,672 extra records at repeated sensor/timestamp keys, 12 conflicting keys, 82 located sensors and 1,830 reconstructed events. The three proxy-label counts were 372 real, 186 fake and 1,272 uncertain.
- **WP02 Logistic Regression.** The chronological evaluation used 401 training events, 16 purged events and 141 test events. Baseline and tuning both selected or used `C=1` and generated identical predictions. Proxy-real precision/recall/F1 were 0.656/0.709/0.682 in the future test and 0.723/0.694/0.708 in the pooled 558-event held-sensor evaluation.
- **WP03 coverage and labels.** The frozen source snapshot contains 2,934,580 rows through 25 September 2026, 2,683 events, and 572 proxy-real, 314 proxy-fake and 1,797 uncertain events. The local WP03 design uses 586 train, 3 purged and 297 test events. The held-out proxy classes are 200 real and 97 fake. The versioned coverage manifest is partial.
- **Historical agent linkage.** 1,691 investigations, 118 reviewed, and 2,683 reconstructed events. The zero-offset result has 21 conditional one-to-one matches, including four reviewed and one unreviewed held-out match. There are zero reviewed held-out matches. The −2 h and +2 h clock scenarios give 15 and 78 unique conditional matches. Timestamp alignment and run mode remain unresolved.
- **Controlled eligibility.** 83 conditionally eligible (55 real, 28 fake), 211 ineligible (142 real, 69 fake), and three unresolved (all proxy-real). The sample selected 30, with 15 per class. The audit produced zero replay decisions. Eligible versus ineligible median event peak PM2.5 was 81.7 versus 40.5 µg/m³, and median event mean was 74.6 versus 39.0 µg/m³. Spatial features improved eligible-subgroup balanced accuracy by 14.5–21.6 percentage points across the four models. Spatial boosting led that subgroup at 83.0%.

| WP03 model | Temporal-only balanced accuracy | Temporal + spatial balanced accuracy | Temporal + spatial real F1 |
| --- | ---: | ---: | ---: |
| Logistic Regression | 64.40% | 82.91% | 88.72% |
| Random forest | 57.91% | 84.88% | 91.53% |
| Histogram gradient boosting | 59.29% | 83.88% | 90.46% |
| SVM | 57.23% | 82.36% | 89.16% |

## Chapter 5 figure and table inventory

Figure files are in [results/report_figures](../results/report_figures). WP03 here means the `local_through_september` run of `20260301_20261119T2200Z_v1`. The saved tables provide source values for typesetting.

| Chapter 5 topic | Report-ready figures | Table / provenance |
| --- | --- | --- |
| Data cleaning and event detection | [WP02 cleaning and detection workflow](../results/report_figures/wp02_cleaning_and_event_detection_workflow.png), [Monthly coverage and event detections](../results/report_figures/data_coverage_and_event_detection.png) | Coverage `monthly.csv` and `manifest.json`, and `wp02/audit.json`. Report raw rows, sensors, repeated keys, conflicts, located sensors and event counts. `wp02_prepare.py` and `scripts/prepare.py` define the five-minute binning, minimum 10 occupied bins per hour, prior 24-hour baseline with at least six values, SD floor of 2, z > 3 and rise ≥ 10 µg/m³. Consecutive spike hours form events. |
| Proxy label distributions | [WP02 and WP03 source proxy classes](../results/report_figures/proxy_label_distributions_wp02_wp03.png) | `wp02/audit.json` and coverage `manifest.json` for reconstructed event counts, plus WP03 `predictions.csv` deduplicated by sensor and event start for held-out class counts. WP02 and WP03 source cohorts overlap in time. |
| WP01 historical baseline | [Confusion matrices](../results/report_figures/wp01_historical_confusion_matrices.png), [ROC and precision–recall curves](../results/report_figures/wp01_historical_roc_precision_recall.png) | Existing figures copied from `report/figures/confusion_matrices.png` and `report/figures/roc_pr_curves.png`. Original evidence is `46cb986:model.ipynb` and the manuscript's historical Logistic Regression table. |
| WP02 Logistic Regression | [Proxy-real metrics by protocol](../results/report_figures/wp02_logistic_regression_proxy_real_metrics.png) | `wp02/metrics.csv` for support, confusion counts and scores, and `wp02/inner_folds.csv` for tuning support. |
| WP03 four-model comparison | [Balanced accuracy by model and feature arm](../results/report_figures/wp03_model_feature_arm_balanced_accuracy.png) | WP03 `metrics.csv`, `design.json`, `partition.csv`, `tuning.csv` and `errors_by_sensor.csv`. The primary table uses the same 297 held-out events across all arms. |
| Historical agent matching | [Clock sensitivity of conditional matches](../results/report_figures/agent_historical_clock_sensitivity.png) | Historical export `clock_sensitivity.csv` and `summary.json`, with coverage `manifest.json` for the 2,683-event denominator. Report the reviewed and held-out match counts to show the limited comparison coverage. |
| Agent trigger eligibility | [PM2.5 distributions](../results/report_figures/agent_eligibility_pm25_distributions.png), [Frozen model comparison](../results/report_figures/agent_eligibility_frozen_model_comparison.png) | Figures copied from the eligibility analysis. Its `eligibility_summary.csv`, `eligibility_by_class.csv`, `pm25_summary.csv`, `model_performance.csv` and `eligible_spatial_deltas.csv` supply the tables. |

## Code and repository review

- The pre-audit working tree had four modified tracked files (`.gitignore`, `eda.ipynb`, `model.ipynb`, `notes.md`), 68 untracked entries and no staged changes. The untracked material includes the nested AGENT_AI checkout, manuscript, current research scripts, tests, and WP02/WP03/agent outputs. Preserve the pre-existing work and assemble the final package from a reviewed file list. The Git index currently tracks nine files.
- The 25 legacy modelling cells are marked `%%historical` in `model.ipynb` and disabled by default. Their stored outputs match the Git archive. One legacy code cell was edited before this audit, so use the archived Git version for historical reproduction. The WP02 cell is disabled and directs readers to the isolated rerun. The notebook's first active section runs WP03 and can overwrite frozen WP03 outputs during Run All. The audit used the saved predictions and left both notebooks as found.
- `wp02_prepare.py` and `scripts/prepare.py` overlap on event reconstruction. The legacy mode of the latter exists for equivalence checking. The original scripts are hash-pinned, so retain them for benchmark reproduction. The historical notebook modelling and later WP02/WP03 code also overlap in estimators but differ in unit and protocol. The prior `results/agent/<version>/access.json` is an obsolete access-attempt diagnostic for the current offline comparison. Keep it as historical provenance and cite the local export analysis for findings.
- Local `raw_data/`, `data/derived/`, virtual environments, caches and `.env` files are covered by ignore rules. The Git index already tracks the historical candidate tables, the large combined sensor export `sacaqm_80_sensors_full.csv`, and the dashboard metadata. These are pre-existing archival files with detailed measurement or location data. Confirm the scope approved for examiner or public release. The untracked station mapping audit, event-level predictions and selection files, review case sheet and nested AGENT_AI checkout also require an explicit inclusion decision. Raw measurements and local agent exports are required for full reconstruction and should be supplied only through an authorised archive.
- A pattern-based check of current tracked and untracked research text files, notebook source and text outputs, and the agent Python source found no credential-bearing MongoDB URI, recognised token shape, private-key header or literal credential assignment. No local `.env` or key file was present at the three project roots checked. This check covers common plaintext forms in the current tree. The repository's Git history and the contents of external archives were outside its scope.

## Limits and remaining blockers

1. **Manuscript finalisation.** `report/main.tex` still labels itself a working draft and contains placeholder author, supervisor and AI declaration front matter. The abstract, discussion and conclusion refer to completed work as pending, and the corrected results section still contains TODOs. Integrate the verified WP02, WP03 and agent results using the inventory above, resolve chapter numbering (the draft currently places Methodology in Chapter 5), complete the author-owned declarations, then compile and inspect the final PDF. The local environment did not expose a LaTeX compiler on PATH.
2. **Distribution package.** Confirm permitted sharing of the tracked detailed sensor/metadata CSVs and the untracked detailed agent artifacts. Select the required code, aggregate outputs and approved inputs explicitly. Full archive reproduction needs local data intentionally excluded from Git, so document the approved hand-off path for examiners. The nested AGENT_AI checkout and its local environment are outside the submission bundle unless specifically approved.

The research itself is limited to historical and retrospective proxy-label evaluation. The timing of available evidence excludes onset-time claims, neighbour evidence contributes to the proxy labels, and the uncertain events are excluded from binary scoring. Later coverage and independent pollution truth remain unavailable. The historical match rates depend on clock assumptions and station mapping. Trigger eligibility is a conditional entry criterion. Neither historical linkage nor the controlled audit supports a verified comparative alert-accuracy estimate. The absence of genuine replay is a documented scope limit for this frozen submission.

## Files changed during the audit

- Added `docs/FINAL_SUBMISSION_AUDIT.md` and `scripts/final_submission_audit.py`.
- Updated `docs/REPRODUCE.md` with the historical command, corrected WP02 artifact accounting and a frozen-audit workflow. Corrected the manifest counts in `docs/IMPLEMENTATION_LOG.md`.
- Added the ten PNGs named in the Chapter 5 inventory under `results/report_figures/`. WP02 and agent verification also created isolated local temporary outputs.

**Final verdict: BLOCKED by manuscript finalisation and the release-package review.**
