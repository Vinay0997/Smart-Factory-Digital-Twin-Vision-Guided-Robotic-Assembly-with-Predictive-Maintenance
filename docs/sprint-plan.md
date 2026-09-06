# Sprint Plan

Agile, 2-week sprints. Each sprint has a goal, a task checklist, and a single deliverable that should be demoable (screenshot, recording, or working command) before moving to the next sprint.

## Sprint 1 — Plant Simulation & PLC Logic

**Goal:** A simulated conveyor cell running under closed-loop PLC control.

- [ ] Install Factory I/O (30-day Ultimate trial) and build a conveyor-and-sorting station scene.
- [ ] Install TIA Portal (or CODESYS) and create a new S7-1500 (or generic IEC 61131-3) project.
- [ ] Import `plc/tia-portal/conveyor_sequencing.scl` and `plc/codesys/interlock_logic.st`.
- [ ] Expose Factory I/O tags via its built-in OPC-UA server.
- [ ] Wire PLC inputs/outputs to Factory I/O tags per `plc/opcua-tag-map.csv`.
- [ ] Run the simulation and confirm the conveyor starts, stops on E-stop, and increments the part counter.

**Deliverable:** Screen recording of the conveyor cycling under PLC control with a simulated E-stop trip and recovery.

## Sprint 2 — SCADA & HMI

**Goal:** Live operator dashboard reflecting real-time plant state.

- [ ] Install Ignition (free trial mode).
- [ ] Import `scada/ignition/opcua-connection.json` connection settings, pointed at the PLC/Factory I/O OPC-UA server.
- [ ] Import or rebuild `scada/ignition/hmi-screens/assembly-line-overview.json` as a Perspective view.
- [ ] Bind all indicators, counters, and the OEE gauge to live tags.
- [ ] Configure OEE calculation tags (availability, performance, quality).

**Deliverable:** Ignition project export plus screenshots of the HMI reacting live to conveyor state changes.

## Sprint 3 — Robot Cell Simulation

**Goal:** A UR10 arm executing a full pick-and-place cycle in Gazebo.

- [ ] Set up a ROS2 workspace (`robot-cell/ros2_ws`).
- [ ] Pull in a UR10 URDF/xacro description (`robot-cell/ros2_ws/src/ur10_description`).
- [ ] Configure MoveIt (`robot-cell/ros2_ws/src/ur10_moveit_config`).
- [ ] Load `robot-cell/gazebo_worlds/assembly_station.world`.
- [ ] Launch `factory_cell.launch.py` and confirm the robot spawns, controllers activate, and MoveIt plans successfully.
- [ ] Run `pick_place_node.py --dry-run` first, then with live MoveIt execution.

**Deliverable:** Recording of a full pick cycle: home -> pick -> place -> return home.

## Sprint 4 — Vision Inspection

**Goal:** Automated pass/fail decisions feeding back into the physical cell.

- [ ] Confirm the Gazebo camera topic is publishing via `ros_gz_bridge`.
- [ ] Run `vision/inspection_node.py --mode ros2` and verify inspection results are logged.
- [ ] Test the standalone classical-CV path (`--mode standalone --source 0`) against a webcam for quick iteration.
- [ ] Verify MQTT messages land on `factory/vision/inspection_result`.
- [ ] Confirm `pick_place_node.py` correctly routes "pass" parts to the assembly fixture and "fail" parts to the reject bin.
- [ ] Review and begin addressing FMEA items FM-01, FM-02, and FM-08 from `docs/fmea-vision-inspection.md`.

**Deliverable:** Log output and a short clip showing a rejected part correctly routed to the reject bin.

## Sprint 5 — IIoT & Cloud Integration

**Goal:** End-to-end telemetry flowing from simulation to the cloud.

- [ ] Bring up Mosquitto via `docker compose up mosquitto`.
- [ ] Create an AWS IoT Core "thing", download certificates, and set `AWS_IOT_*` variables in `.env`.
- [ ] Set `ENABLE_AWS_FORWARDING=true` and run `iot-bridge/mqtt_publisher.py`.
- [ ] Confirm messages appear in the AWS IoT Core MQTT test client.
- [ ] Confirm the same messages are written to InfluxDB (`docker compose up influxdb`).

**Deliverable:** Screenshot of the AWS IoT Core console showing live incoming messages alongside an InfluxDB query returning the same data.

## Sprint 6 — Data, Dashboards & Documentation

**Goal:** A polished, demoable, fully documented project.

- [ ] Load `data-pipeline/postgres/schema.sql` and confirm seed data (shifts, sample FMEA row) is present.
- [ ] Import `data-pipeline/grafana/dashboards/oee-dashboard.json` and `predictive-maintenance.json` into Grafana.
- [ ] Connect both InfluxDB and PostgreSQL as Grafana data sources (`influxdb-telemetry`, `postgres-factory`).
- [ ] Finish `docs/fmea-vision-inspection.md` and `docs/oee-kpi-definitions.md`.
- [ ] Record a 3–5 minute end-to-end demo video.
- [ ] Finalize the top-level `README.md` with screenshots/GIFs and push to GitHub.

**Deliverable:** Complete GitHub repository with working `docker compose up`, populated dashboards, and a demo recording linked in the README.
