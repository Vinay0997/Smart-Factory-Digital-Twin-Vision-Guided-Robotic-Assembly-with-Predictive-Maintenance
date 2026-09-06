# OEE and KPI Definitions

Reference definitions for every metric surfaced on the Ignition HMI and Grafana dashboards, and how each maps back to a tag or database field in this project.

## Overall Equipment Effectiveness (OEE)

OEE is the standard Lean manufacturing metric combining three factors:

\[ \text{OEE} = \text{Availability} \times \text{Performance} \times \text{Quality} \]

A "world-class" OEE benchmark is generally considered 85%+. In this project, `OEE_Overall` is a generated/calculated tag/column driven by the three sub-metrics below.

| Metric | Tag / Field | Formula | Description |
|---|---|---|---|
| Availability | `OEE_Availability` (Ignition calc tag) | Run Time / Planned Production Time | Fraction of scheduled time the conveyor/robot cell was actually running, excluding planned stops |
| Performance | `OEE_Performance` (Ignition calc tag) | (Ideal Cycle Time x Total Parts) / Run Time | How close actual cycle time ran to the ideal/design cycle time |
| Quality | `OEE_Quality` (Ignition calc tag, also `v_current_run_summary.quality_pct` in Postgres) | Good Parts / Total Parts | Fraction of parts that passed vision inspection on the first pass |
| Overall OEE | `OEE_Overall` | Availability x Performance x Quality | Composite score shown on the main HMI gauge and Grafana OEE dashboard |

## Availability

- **Definition:** The percentage of scheduled production time that the line was actually available to run, after subtracting unplanned downtime (E-stops, safety faults, jams) and planned stops (breaks, changeovers).
- **Data source:** Derived from `Conveyor_Running` uptime versus scheduled shift time (`shifts` table) and gaps recorded in `downtime_events`.
- **Target:** >= 90% is considered strong for a simulated single-line cell.

## Performance

- **Definition:** How fast the line ran relative to its designed maximum speed, accounting for minor stops and reduced-speed running that don't count as full downtime.
- **Data source:** `Machine_Cycle_Time` tag compared against a defined ideal cycle time constant (set per station in `plc/opcua-tag-map.csv` scan configuration).
- **Target:** Watch `Machine_Cycle_Time` drift upward over time on the Predictive Maintenance dashboard — sustained drift indicates mechanical wear before it becomes a hard failure.

## Quality

- **Definition:** The percentage of parts that pass inspection without rework, on the first attempt.
- **Data source:** `parts.inspection_status` in PostgreSQL, aggregated in the `v_current_run_summary` view; also mirrored via `Vision_Confidence_Score` for per-part detail.
- **Target:** >= 95% for a stable simulated process; values well below this should trigger review of FMEA items FM-01/FM-02 in `docs/fmea-vision-inspection.md`.

## Downtime Metrics

| Metric | Field | Description |
|---|---|---|
| Downtime event count | `downtime_events` row count | Number of discrete stoppages in a given period |
| Downtime duration | `downtime_events.duration_seconds` (generated column) | Time lost per event, computed from `started_at`/`ended_at` |
| Fault code | `downtime_events.fault_code` | Maps to `Fault_Code` (PLC) or `SafetyFaultCode` (interlock logic): 1=E-Stop, 2=Safety zone breach, 3=Robot cell not ready, 4=Air pressure fault |
| MTBF (Mean Time Between Failures) | Derived: total run time / number of downtime events | Reliability indicator tracked over a rolling 7-day window on the Predictive Maintenance dashboard |

## Vision Inspection Metrics

| Metric | Field | Description |
|---|---|---|
| Inspection status | `Vision_Inspection_Result` / `parts.inspection_status` | One of `pass`, `fail_misaligned`, `fail_defect`, `no_part_detected` |
| Confidence score | `Vision_Confidence_Score` / `parts.confidence_score` | 0-1 score from the classical CV centroid check or YOLO detection confidence |
| Offset | `parts.offset_px` | Pixel distance between detected part center and expected center, used to flag misalignment |
| Reject rate | Derived: `fail_*` count / total parts | Tracked in the Grafana "Reject Rate by Cause" pie chart |

## Predictive Maintenance Metrics

| Metric | Field | Description |
|---|---|---|
| Alert level | `Predictive_Maintenance_Alert` / `maintenance_alerts.alert_level` | `normal`, `warning`, or `critical`, forwarded from cloud analytics via AWS IoT Core |
| Vibration RMS | InfluxDB field `vibration_rms` (simulated) | Proxy signal for conveyor motor bearing wear; thresholds set at 3.5 (warning) and 5.0 (critical) |
| Cycle time drift | `Machine_Cycle_Time` trend over time | Gradual increase suggests mechanical degradation before a hard failure occurs |

## Notes on Simulated vs. Real-World Values

Because this project runs on Factory I/O and Gazebo rather than physical hardware, metrics like vibration RMS are synthetic signals generated for demonstration purposes rather than real sensor readings. When describing this project in interviews, be explicit that the OEE/PdM methodology and dashboard design are production-representative, while the underlying signal sources are simulated.
