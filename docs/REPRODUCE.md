# Reproducing the SACAQM research archive

## WP01 historical candidate-hour model

The tracked notebook at commit `46cb986` contains the 25 original modelling code cells and their outputs. The frozen input is `labelled_spike_candidates.csv`. Run the original cells in a new temporary directory from the repository root if a historical model rerun is required. This starts at the candidate export. The current working notebook opens with an active WP03 cell, so use the archived version for WP01.

```powershell
@'
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

os.environ["MPLBACKEND"] = "Agg"
notebook = json.loads(subprocess.check_output(["git", "show", "46cb986:model.ipynb"]))
run = Path(tempfile.mkdtemp(prefix="sacaqm-wp01-"))
shutil.copyfile("labelled_spike_candidates.csv", run / "labelled_spike_candidates.csv")
os.chdir(run)
scope = {"__name__": "__main__", "display": print}
for number, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] == "code":
        exec(compile("".join(cell["source"]), f"WP01 cell {number}", "exec"), scope)
print(run)
'@ | .\.venv\Scripts\python.exe -
```

## March–July WP02

Run the following from the repository root in PowerShell to check the archived inputs, scripts and CSV outputs. A missing or changed file stops the check.

```powershell
$manifest = Get-Content wp02/run_manifest.json -Raw | ConvertFrom-Json
foreach ($entry in $manifest.sha256.psobject.Properties) {
    $actual = Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256 -ErrorAction Stop
    if ($actual.Hash -ne $entry.Value) { throw "Hash mismatch for $($entry.Name)" }
}
```

The recorded environment uses Python 3.10.11, pandas 2.3.3, NumPy 2.2.6, scikit-learn 1.7.2 and Matplotlib 3.10.9.

### Isolated WP02 rerun

The scripts resolve inputs and outputs relative to the current working directory. From the verified repository root, use a fresh temporary directory to protect the benchmark. The review script takes the archived case selection as an input.

```powershell
$repo = (Get-Location).Path
$python = Join-Path $repo '.venv/Scripts/python.exe'
$run = Join-Path $env:TEMP ("sacaqm-wp02-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path "$run/raw_data", "$run/wp02" -Force | Out-Null
foreach ($month in 'march','april','may','june','july') {
    Copy-Item "raw_data/${month}_data.csv" "$run/raw_data/"
}
Copy-Item sacaqm_dashboard_sensor_metadata.csv $run
Copy-Item wp02/review_cases.csv "$run/wp02/"
Push-Location $run
try {
    foreach ($script in 'wp02_prepare.py','wp02_model.py','wp02_review.py') {
        & $python (Join-Path $repo $script)
        if ($LASTEXITCODE -ne 0) { throw "Failed running $script" }
    }
} finally {
    Pop-Location
}
Write-Output "Rerun outputs: $run/wp02"
```

Compare the eight regenerated CSVs with the corresponding archived entries in the manifest. Verify the copied `review_cases.csv` separately. The audit JSON and review PDF are outside the hash manifest. The benchmark covers March–July.

## Frozen submission audit

Use local archives only. The audit checks WP03 metrics against its saved predictions, stages the historical agent comparison in a temporary directory, reproduces the controlled eligibility outputs in isolation, and builds the Chapter 5 figures. Its temporary directory contains restricted exports and is printed for local inspection. Run from the repository root.

```powershell
.\.venv\Scripts\python.exe -m scripts.final_submission_audit
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

See [the submission audit](FINAL_SUBMISSION_AUDIT.md) for the figure inventory and audit findings. The snapshot commands below describe the original pipeline. The training and acquisition commands are outside the frozen submission audit.

## Versioned snapshots and the later-period benchmark

Use the project environment from the repository root. The snapshot requests observations from 1 March 00:00 to 19 November 22:00 exclusive on the API request clock (UTC). The source CSV clock lacks an explicit timezone. Preserve its displayed hour for local analysis and confirm alignment before joining external timestamps. The 90-ID request roster is an acquisition inventory. It never determines historical eligibility. Spatial eligibility requires a valid unambiguous site and a reading observed by the close of the target start hour. Undated coordinates assume a stable location. Older deployments or relocations without metadata remain a limitation.

1. Run `.venv\Scripts\python -m scripts.ingest --fetch` to reconcile partitions. Repeating the command retries failures and reuses successful responses, including recorded empty responses. The request ledger distinguishes unresolved requests from successful empties. A network connection failure suspends further calls for that invocation. The older monthly exports remain untouched. The collector checks sensor and date bounds and rejects a replacement missing archived values. A successful server response alone cannot establish continuous measurement or disprove a server-side row limit.
2. Run `.venv\Scripts\python -m scripts.prepare` (also available through eda.ipynb) for derived hourly observations, one row per event, daily sensor-slot coverage, monthly counts and hashes. For a newly reconciled input inventory, set `$env:SACAQM_REVISION='v2'` before running either command. The original source files and first revision remain available. Counts by month use event onset; evidence can cross month boundaries. Zero observed rows in an unresolved month means missing local evidence.
3. Run `.venv\Scripts\python -m scripts.wp03_compare --version local_through_september` for the partial snapshot. The full experiment uses `--version expanded` and requires reconciliation. Boundaries are 1 August and 1 October respectively. The same event keys go into both feature arms. Inverse squared great-circle distance weights the mean reliable PM2.5 of assessable neighbours within 5 km over the event. Colocated neighbours are averaged separately. All three tuning folds use purged, expanding time partitions. The continuous SVM score is a decision margin.
4. Run `.venv\Scripts\python -m unittest discover -s tests -v`. Reconcile the historical benchmark by calling scripts.prepare.benchmark_check on the five original monthly inputs; it compares every historical event column against the frozen CSV.
5. Run `.venv\Scripts\python -m scripts.agent_comparison` to validate the three local agent exports and rebuild the offline comparison. Results are under `results/agent/<version>/export_20261120/`. The primary comparison assumes matching displayed clocks; the sensitivity table tests minus and plus two hours. See LIMITATIONS.md in the result directory.
