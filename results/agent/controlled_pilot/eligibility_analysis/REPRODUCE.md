# Reproduce the trigger eligibility analysis

Use the existing project environment with pandas, NumPy and Matplotlib. Run from the repository root in PowerShell.

```powershell
.\.venv\Scripts\python.exe -m scripts.agent_eligibility_analysis
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The analysis reads the existing eligibility audit and its summary, the frozen WP03 design, partition and predictions, and the local derived event metadata. It verifies the WP03 file hashes against the pilot summary and validates a one-to-one eligibility join on sensor, event start, event end and proxy label. Each model and feature arm has one prediction per held-out event. The verification JSON records source hashes and row counts.

Event peak is the maximum hourly PM2.5 value during a WP03 event. Event mean averages those hourly values. The distribution figure uses empirical cumulative shares on a logarithmic concentration axis. The summary CSV reports event-level quartiles and ranges in µg/m³.

Proxy-real is the positive class for precision, recall and F1. Balanced accuracy averages proxy-real and proxy-fake recall and requires both classes. Precision requires proxy-real events and at least one positive prediction, and recall and F1 require proxy-real events. Missing metrics are blank in the CSV and shown as an em dash in the report. The ineligible group includes blocked stations. Three unresolved station identities contribute to the descriptive analyses. The scored groups contain 83 and 211 unique events per configuration.

All generated files are written in this directory. The module uses local data and saved predictions throughout. See [the parent audit](../LIMITATIONS.md) for the trigger timing and station mapping assumptions.
