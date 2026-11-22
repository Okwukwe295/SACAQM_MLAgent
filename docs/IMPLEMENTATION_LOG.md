# SACAQM implementation log

## 20 November 2026 — March–July WP02 benchmark

Verified all 19 SHA-256 entries in `wp02/run_manifest.json` against the working tree. The inventory covers the five monthly raw exports, station metadata, historical candidate CSV, nine WP02 CSVs and three Python scripts. All matched. The manifest records Python and package versions. Its hash inventory excludes the audit JSON, blinded PDF, Markdown report and notebooks.

The March–July benchmark stays at its existing paths. The hash comparison establishes file identity with the recorded run. Scientific evaluation and independent event verification remain separate questions. August and September coverage has yet to be audited.

Added repository ignore rules for local credentials, Python caches, derived data and LaTeX build files. Versioned aggregate results and the manuscript belong outside the ignored derived-data directory. See [reproduction instructions](REPRODUCE.md).

## 20 November 2026 | Code checkpoints 1–4

All 19 frozen WP02 manifest hashes matched. The shared preparation path in historical mode reproduced all 1,830 benchmark events and every archived event column. The notebooks call the new preparation and modelling entry points. Raw measurements, old exports and benchmark scripts remain at their original paths.

The version 1 local inventory contains 2,934,580 rows from 83 sensors through 25 September. It produces 2,683 events (572 proxy-real, 314 proxy-fake, 1,797 uncertain). The acquisition roster contains 90 known identifiers, including sensors absent from the measurements. The first API request failed at connection time; 809 subsequent partitions have no request result. November has zero observed days. Full-period training and test evaluation are blocked. The per-sensor day counts describe observed slot occupancy regardless of deployment history. They cannot distinguish inactive instruments, upstream gaps and failed downloads.

The partial-snapshot study used 586 training events, three purged events and 297 later events. The eight paired comparisons, per-sensor errors, partitions and tuning scores are saved under results/wp03. Temporal-only LR reached balanced accuracy 0.644; with IDW it reached 0.829. The spatial forest reached 0.849, with 11 proxy-real misses and 24 proxy-fake false positives. Neighbour evidence also contributes to the reference labels. This result measures proxy agreement and cannot establish physical pollution validity.

Read-only inspection of the agent source established station-level alert/no_alert, optional replay start time versus live write time, human_verdict and optional correct_decision. The agent considers neighbour confirmation, weather, history and confidence. Its application database module creates an index at import time, so the comparison script uses a separate read-only projection. The project environment lacks the MongoDB driver, package installation could not obtain it, and a separate SRV lookup could not resolve the authorised cluster. Source-clock alignment remains unverified. No matched record counts or agreement estimates have been inferred.

## 21 November 2026 | Offline agent comparison

Reworked scripts/agent_comparison.py to use the three local agent exports. Counts, review corrections, input hashes and the WP03 event-file linkage were checked. The prior live-access status describes an earlier attempt; the new export_20261120 directory is the offline result. No database connection was made. Run the module without arguments.

At zero clock offset, 21 of 2,683 events have a unique conditional investigation link, 33 receive 126 repeated investigations and 2,629 have no eligible overlap. Four of 118 reviewed investigations have unique conditional pairs; none has a held-out prediction. One unreviewed held-out event has all eight model predictions. Time shifts of minus and plus two hours yield 15 and 78 unique pairs. Source times and run modes remain unverified, so model accuracy against physical pollution cannot be inferred. See results/agent/20260301_20261119T2200Z_v1/export_20261120 for the full accounting.

## 22 November 2026 | Controlled agent pilot

Audited the sibling AGENT_AI source and ran the offline pilot on all 297 frozen WP03 test events. At fixed hour-end boundaries and with an available investigation slot, 83 meet the latest-point PM2.5 trigger. Of the remaining events, 209 are below the trigger, two are at blocked stations, and three have unresolved multi-sensor station identity. The deterministic pilot sample contains 15 proxy-real and 15 proxy-fake events. The comparison carries all 2,376 frozen prediction rows.

Zero events were replayed. The archived station and investigation exports lack complete historical tool context, and the genuine Moonshot Kimi decision loop requires external calls with prior approval. The original replay endpoint uses an interval-mean gate, writes decisions, and can send email. The offline module issues no database or external service requests. Run `.\.venv\Scripts\python.exe -m scripts.agent_controlled_comparison` from the repository root. Outputs and the source audit are in [results/agent/controlled_pilot](../results/agent/controlled_pilot).
