# FMEA: Vision Inspection Subsystem

Failure Mode and Effects Analysis for the vision-guided quality inspection subsystem in the Smart Factory Digital Twin, covering the camera/Gazebo sensor, `inspection_node.py`, the MQTT bridge, and the reject-arm actuation path. Scored on the standard 1–10 Severity (S) / Occurrence (O) / Detection (D) scale, with Risk Priority Number (RPN) = S x O x D. Items with RPN above 100 are prioritized for corrective action.

## Scope

This analysis covers the path from part arrival at the pick station through the vision inspection decision to the reject-arm/robot placement action, as implemented in `vision/inspection_node.py`, `plc/tia-portal/conveyor_sequencing.scl`, and `iot-bridge/mqtt_publisher.py`.

## Failure Mode Register

| ID | Failure mode | Potential effect | S | O | D | RPN | Recommended action | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| FM-01 | Camera misdetects part alignment due to lighting variation | Good part incorrectly rejected, reducing throughput and increasing scrap-tracking noise | 6 | 4 | 5 | 120 | Add lighting normalization preprocessing (CLAHE/histogram equalization); retrain YOLO model with varied lighting dataset | Vinay Shanamoni | Open |
| FM-02 | Classical CV contour detection fails on low-contrast or transparent parts | Part passes inspection undetected, defective part reaches assembly fixture | 8 | 3 | 6 | 144 | Switch to YOLO-based detector for low-contrast SKUs; add part-presence confirmation via a second sensor (photoelectric) before trusting a "pass" | Vinay Shanamoni | Open |
| FM-03 | MQTT broker connection drops between inspection node and PLC bridge | Inspection results never reach the PLC; conveyor stalls in INSPECTING state indefinitely | 7 | 3 | 4 | 84 | Add MQTT connection watchdog with automatic reconnect and a PLC-side timeout that forces a fault state (Fault_Code) if no result received within N seconds | Vinay Shanamoni | Open |
| FM-04 | Vision node publishes malformed/non-JSON payload | PLC bridge or SCADA misinterprets result, potential unsafe reject-arm trigger | 7 | 2 | 5 | 70 | Enforce a strict JSON schema on publish; add payload validation in `mqtt_publisher.py` before writing to InfluxDB or forwarding to AWS IoT Core | Vinay Shanamoni | Open |
| FM-05 | YOLO model confidence below threshold but result still classified as "pass" | Marginal-quality part passes to assembly, downstream rework cost | 6 | 3 | 4 | 72 | Add explicit low-confidence state (`uncertain`) that routes part to manual review station instead of auto-pass/fail | Vinay Shanamoni | Open |
| FM-06 | Reject arm actuates late or fails to actuate after a "fail" result | Defective part remains on line, reaches assembly fixture | 9 | 2 | 3 | 54 | Add end-of-travel sensor on reject arm with feedback to PLC; escalate to Fault_Code if arm does not confirm actuation within timer window | Vinay Shanamoni | Open |
| FM-07 | Camera sensor topic disconnects in Gazebo/ROS2 (bridge crash) | No new inspection results published; conveyor halts waiting on vision | 5 | 2 | 3 | 30 | Add ROS2 topic heartbeat monitor; auto-restart `ros_gz_bridge` node on missed heartbeat | Vinay Shanamoni | Open |
| FM-08 | Vision inspection result timestamp lags actual part position (network/processing delay) | Wrong part rejected/accepted due to stale result applied to a different part | 8 | 3 | 6 | 144 | Include part_id correlation between conveyor sensor trigger and vision result; reject any result older than the expected cycle-time window | Vinay Shanamoni | Open |

## Priority Actions (RPN > 100)

Three failure modes exceed the RPN 100 threshold and should be addressed first:

- **FM-02** (undetected low-contrast defects, RPN 144) and **FM-08** (stale result misapplied to wrong part, RPN 144) both carry high severity (8) because they risk a defective part reaching the assembly fixture rather than just a throughput loss. Both should be resolved before any live demo of the reject path.
- **FM-01** (lighting-driven false rejects, RPN 120) is lower severity but higher occurrence, and directly affects the quality metric shown on the OEE dashboard, so it should be resolved before collecting any dashboard screenshots for a portfolio recording.

## Detection Strategy Summary

Detection scores above assume no dedicated sensor fusion is yet implemented. Adding a secondary photoelectric part-presence sensor and a part-ID correlation check (tying `Part_Present_Sensor` rising edges to the corresponding vision result) would lower the Detection score on FM-02, FM-06, and FM-08, directly reducing their RPNs. This aligns with the sensor fusion approach used in your PlebC Innovations robotic ultrasound project (force-torque sensor plus closed-loop control), applied here to the vision-inspection path.

## Revision History

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-09-06 | Initial FMEA register for vision inspection subsystem | Vinay Shanamoni |
