# Controlled SACAQM pilot

## Agent source audit

The sibling `AGENT_AI` checkout was inspected as source text. In `agent.py`, the hourly monitor iterates public stations with assigned sensors, skips two blocked station IDs, and uses the first reading sorted descending by timestamp from a query with a one-hour lower bound. It ignores a missing latest PM2.5 value and wakes the agent at 60 µg/m³ or higher. The hourly bucket and day counter use UTC wall time. A station gets at most one attempted investigation per bucket, and the process allows five attempts across stations per UTC day. The 24-hour mean, rounded to two decimals, can independently send a daily-outlier email at 40 µg/m³ or higher. That branch can run before the hourly investigation and does not consume its cap.

The manual investigation endpoint queries an inclusive interval and passes the rounded PM2.5 mean and latest record without a threshold gate. The separate historical replay endpoint applies the same inclusive bounds and descending timestamp order, and requires a rounded mean of at least 60 µg/m³. Both are explicitly requested investigations and use the shared activity lock. The historical readings tool uses the supplied interval for any requested station, ignores the tool's requested hours, and returns up to 20 records. The maximum of three neighbors comes from the public station inventory, using coordinates and a radius clamped to 10–80 km. The historical weather tool requests the date and hour of the interval start from Open-Meteo. Live investigations save wall-clock UTC timestamps. Replay conclusions save the supplied window start.

In `llm.py`, the genuine decision path supplies the station ID, latest reading document, threshold, trigger value, and prior agent decisions, confidences and human feedback. Live history queries the preceding 30 days. Replay queries 90 days strictly before window start, although its prompt still says 30 days. Both format up to 30 prior cases despite the prompt saying “Last 3.” The prompt asks the model to weigh sustained readings, nearby stations, weather and station reliability, and to submit an operational decision, confidence and explanation. The backend calls Moonshot's `kimi-k2.6` with tools, up to ten iterations. The source names the transport “OpenRouter” internally but points at Moonshot's endpoint.

## Offline eligibility and selection

The manifest's raw observations and frozen hourly spike rows provide the observation basis. WP03 preparation removes conflicting sensor-timestamp keys, averages samples into five-minute bins, and takes an hourly mean from at least ten occupied bins. The monitor trigger uses a single raw point. For each held-out spike hour, the pilot uses a fixed evaluation at the right edge and searches the corresponding half-open hour on the frozen dataset clock. This matches the event's underlying measurement window and excludes observations at or after the right edge. The original live query has a lower bound only and runs on its scheduler's phase. The pilot anchors to exact hours and assumes an available investigation slot for each isolated event. Historical visibility, scheduler phase, deduplication, station iteration order, daily cap state, and the dashboard/MongoDB clock alignment cannot be recovered from these local exports. Eligibility therefore describes the monitor's point trigger under this controlled schedule, independent of the historical replay endpoint's mean trigger.

The audit requires an unambiguous sensor-to-station link, a single sensor at that station, and coordinates consistent with the model metadata within 0.0001 degrees. Multi-sensor stations can trigger from a different sensor and are treated as unresolved for this same-sensor pilot. Missing observations, conflicting or invalid latest PM2.5, and unresolved station identity are recorded as missing data unless another event hour establishes eligibility. Known blocked stations are ineligible. An eligible event is anchored to its first assessable qualifying hour. A later qualifying hour can follow an unresolved hour, which is recorded in the audit.

Selection ranks eligible events by the SHA-256 of `sacaqm-controlled-pilot-v1|event_id`. It takes up to 15 per proxy class and fills remaining slots in hash order, up to 30. Proxy labels only guide sampling and analysis. The comparison has one row per held-out event and frozen model/feature arm. Prediction 1 means proxy-real and 0 means proxy-fake.

## Replay blocker

The original app's `db.py` connects and creates an index on import. Its replay conclusion writes an event and can send email when the model returns alert with confidence of at least 70. This pilot imports no agent modules and issues no external requests. A faithful isolated replay needs an adapter for historical station and sensor payloads, archived weather, historically available agent memory including review text and review timing, and local-only conclusion capture. The static station map omits historical public visibility and city fields, and the historical agent export omits free-form notes, review timing, and run mode. The sensor exports represent the dashboard snapshot, with uncertain parity with the MongoDB document payloads and coverage of potential neighbors. A clipped event-window replay would also differ from normal live tool windows and 30-day memory. External Moonshot requests require explicit approval even after these context gaps are resolved.

`replay_results.csv` is header-only. Agent decisions, confidence, and disagreement are blank in `comparison.csv`. The pilot provides no paired decision table, agreement estimate, or paired-result figure. Operational alerting incorporates a confidence and action policy. Proxy-real and proxy-fake are reference labels for the ML experiment, and neither set of outcomes establishes externally verified accuracy.

## Held-out cohort and pilot coverage

| Audit outcome | Proxy-real | Proxy-fake | Total |
| --- | ---: | ---: | ---: |
| Conditionally eligible | 55 | 28 | 83 |
| Ineligible | 142 | 69 | 211 |
| Station identity unresolved | 3 | 0 | 3 |
| Held-out cohort | 200 | 97 | 297 |
| Selected from eligible events | 15 | 15 | 30 |
| Successfully replayed | 0 | 0 | 0 |
