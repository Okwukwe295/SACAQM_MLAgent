# SACAQM research report | WP02
19 November 2026 · Researcher review draft · Submission deadline 21 November 2026

## Research question
Once an hourly detector has flagged an unusual PM2.5 rise, how closely can a target sensor's measurements reproduce a retrospective network-based judgement about that event? A local plume and a sensor fault can both produce an isolated rise. The available reference is therefore a weak label. The experiment measures agreement with that reference.

## Data and event construction
The March–July exports contain 2,061,501 rows from 83 sensors. The audit found 26,672 repeat rows beyond the first record at a given sensor and timestamp. Twelve keys contained conflicting PM2.5 readings. We discarded all measurements at those keys and collapsed agreeing keys. One metadata ID, 350457790675282, identifies two distinct sites. We excluded that ID from both target and neighbour evidence pending dated deployment metadata. Raw exports were retained.

For the remaining located sensors, we averaged nonnegative PM2.5 readings within each occupied five-minute slot and weighted occupied slots equally within the hour. A reliable hour has at least ten occupied slots. We used all eligible located sensors with enough recent observations, avoiding a quality tier determined from the sensor's entire future record. The preceding 24 clock hours supply the baseline, with at least six reliable hourly observations and a standard deviation floor of 2 for the z-score. A candidate requires z > 3 and a rise of at least 10 µg/m³ since the previous reliable, consecutive hour. Adjacent candidate hours form one event. Its duration measures consecutive sharp rises; an elevated plateau can continue beyond it.

WP01 reported 2,040 candidate hours and 1,720 events. WP02 generated 2,173 hours and 1,830 events. Matching sensor and start timestamp recovered 1,718 historical events, with 112 additional starts and two historical starts absent. Revised sensor eligibility, slot weighting and cleaning all change the input to the detector. The individual contribution of each change was not measured.

## Retrospective reference and decision time
We require assessable hours immediately before and after the target run. Within 5 km, a neighbour must be assessable throughout the target run to contribute. A real proxy requires an overlapping neighbour run with both boundaries observed and duration within one hour of the target. For a fake proxy we require a single-hour target, at least one mapped neighbour, complete neighbour coverage, no concurrent neighbour spike, a sharp rise and fall, and a next-hour return toward baseline. The sharp-change threshold is the larger of 10 µg/m³ and twice the prior standard deviation. Return means absolute next-hour z ≤ 1.5 or next-hour concentration ≤ its rolling mean plus one standard deviation. All other events receive an uncertain label.

For duration d, the neighbour boundary search extends d+2 hours either side of an overlapping hour. The conservative evidence interval starts 24 hours before the earliest such search hour and closes after the last possible search hour. A one-hour event starting at 10:00 is therefore scored retrospectively at 14:00, even if its target summary was available sooner. Timestamps follow the source clock; timezone is undocumented.

## Experimental design
The strict sample comprises 558 events from 49 sensors, including 372 proxy-real and 186 proxy-fake events. The remaining 1,272 events (69.5%) are uncertain. Each strict event has one row. The four predictors are event peak, event mean, prior mean and prior standard deviation. Logistic Regression uses balanced class weights, training-fold median imputation, standardisation and a 0.5 probability threshold. Event duration, neighbour counts, next-hour readings and rule outputs are excluded from the predictor list. Proxy dependence remains: the prior standard deviation contributes to the rules and equal peak and mean can indicate a singleton.

We preserved the notebook's strict timestamp boundary convention. The event-level 75% boundary fell at 3 July 2026 21:00. All 141 later events formed the test set. Purging training events whose evidence windows reached the earliest test information left 401 training events and removed 16. Within training, three expanding chronological splits repeated the purge. Mean validation F1 selected C=1 from 0.1, 1 and 10. In a separate existing-network assessment, we withheld each sensor's labelled events in turn. Sensors can still contribute to each other's reference labels. This spatial assessment permits overlapping dates and cannot establish transfer to an independent region.

## Results
Positive class is the real proxy. AP denotes average precision.

| Protocol | Events | TN | FP | FN | TP | Precision | Recall | F1 | ROC-AUC | AP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Future LR, fixed or tuned | 141 | 23 | 32 | 25 | 61 | .656 | .709 | .682 | .611 | .719 |
| Held-sensor LR, pooled | 558 | 87 | 99 | 114 | 258 | .723 | .694 | .708 | .622 | .758 |

Of 86 proxy-real future events, the classifier identified 61 and missed 25. Of 55 proxy-fake events, it identified 23. Calling every event real would give recall 1, precision .610 and F1 .758, while identifying zero fake events. Thus real-class F1 alone would reward an unusable artifact filter. The observed ROC-AUC of .611 indicates modest ranking ability. Held-sensor and future metrics address different populations. Their difference cannot isolate a spatial-feature benefit.

WP01's future F1 was .646 across 183 candidate hours. The unit, eligibility, predictors and evaluation windows all changed. A numerical comparison cannot establish an improvement attributable to cleaning or modelling.

## Independent review and defence
All 30 queued WP01 cases match rebuilt events. The accompanying blinded packet shows five-minute-scale raw observations, target in black and geographically nearby sensors in blue. Blank intervals convey missing data. Each reviewer should independently record real, artifact or uncertain, the visible temporal/spatial evidence, and any external corroboration before inspecting rule outputs. Sensor disagreement alone is insufficient to establish an artifact. The queue deliberately includes difficult cases and cannot estimate population accuracy. Independent adjudication is pending.

The defensible claim is that the LR recovered 61 of 86 network-rule-supported future events on this frozen corpus. This experiment cannot establish ground-truth pollution accuracy, performance on uncertain events, real-time warning capability, or performance on undetected pollution episodes. The report is complete for WP02; independent labels and later planned experiments remain outside these results.

## Reproduction and evidence
From the project root, run eda.ipynb and then model.ipynb, or run wp02_prepare.py followed by wp02_model.py in the project environment. Run wp02_review.py to recreate the blinded packet using review_cases.csv. events.csv records information windows, evidence counts and every label. inner_folds.csv records tuning scores and temporal separation. Per-protocol CSVs contain probabilities and event keys. audit.json, conflicting_keys.csv and ambiguous_sites.csv document the cleaning decisions. Historical comparison uses the downloaded WP01 audit report and the bundle's candidate table and review queue.
