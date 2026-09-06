# Smart Factory Digital Twin: Vision-Guided Robotic Assembly with Predictive Maintenance

An end-to-end simulated Industry 4.0 platform that integrates PLC logic, SCADA, robotics, computer vision, IIoT protocols, and cloud dashboards — covering the full tool stack from PLC programming to cloud-based predictive maintenance, without requiring physical hardware.

## Overview

This project simulates a smart manufacturing cell: a conveyor feeds parts to a vision-guided robotic pick-and-place station, PLC logic handles sequencing and safety interlocks, SCADA visualizes real-time OEE, and telemetry flows to the cloud for predictive-maintenance analytics.

**Architecture flow:**

```
Factory I/O (3D plant simulation)
      |  OPC-UA
Siemens TIA Portal / CODESYS PLC logic
      |  OPC-UA
Ignition SCADA (HMI + OEE dashboards)
      |
ROS2 + Gazebo + MoveIt (UR10 robot cell)
      |
OpenCV / YOLO (vision inspection)
      |  MQTT
Mosquitto Broker
      |
AWS IoT Core (cloud ingestion)
      |
Docker Compose: InfluxDB + Grafana + PostgreSQL
      |
Grafana Dashboards (OEE, uptime, predictive maintenance alerts)
```

## Tools Covered

| Category | Tools |
|---|---|
| Robotics | ROS2, Gazebo, MoveIt, UR10 simulation model |
| PLC / SCADA | Siemens TIA Portal (S7-1500), Allen-Bradley RSLogix emulator, Ignition SCADA, Wonderware (optional) |
| Simulation | Factory I/O, MATLAB/Simulink (or Python numpy/scipy) |
| Computer Vision | OpenCV, YOLO |
| Industrial Protocols | OPC-UA, MQTT, Ethernet/IP (via Factory I/O driver) |
| Cloud / IoT | AWS IoT Core, Docker, Docker Compose |
| Data & Visualization | InfluxDB, Grafana, PostgreSQL |
| CAD | SolidWorks / AutoCAD (fixture/jig design, exported as reference) |
| Methodology | Agile sprints, Kanban board, FMEA documentation |

## Repository Structure

```
smart-factory-digital-twin/
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── architecture-diagram.png
│   ├── fmea-vision-inspection.md
│   ├── sprint-plan.md
│   └── oee-kpi-definitions.md
├── plc/
│   ├── tia-portal/
│   │   └── conveyor_sequencing.scl
│   ├── codesys/
│   │   └── interlock_logic.st
│   └── opcua-tag-map.csv
├── scada/
│   └── ignition/
│       ├── hmi-screens/
│       └── opcua-connection.json
├── robot-cell/
│   ├── ros2_ws/
│   │   ├── src/
│   │   │   ├── ur10_description/
│   │   │   ├── ur10_moveit_config/
│   │   │   └── pick_place_node/
│   │   └── launch/
│   │       └── factory_cell.launch.py
│   └── gazebo_worlds/
│       └── assembly_station.world
├── vision/
│   ├── inspection_node.py
│   ├── yolo_model/
│   │   └── defect_detector.pt
│   └── requirements.txt
├── iot-bridge/
│   ├── mqtt_publisher.py
│   ├── aws_iot_rule.json
│   └── mosquitto/
│       └── mosquitto.conf
├── data-pipeline/
│   ├── influxdb/
│   │   └── init-bucket.sh
│   ├── postgres/
│   │   └── schema.sql
│   └── grafana/
│       └── dashboards/
│           ├── oee-dashboard.json
│           └── predictive-maintenance.json
├── cad/
│   └── fixture-jig.sldprt
└── scripts/
    ├── setup.sh
    └── validate_kinematics.py
```

## docker-compose.yml

```yaml
version: "3.9"

services:
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./iot-bridge/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf
    restart: unless-stopped

  influxdb:
    image: influxdb:2.7
    container_name: influxdb
    ports:
      - "8086:8086"
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=${INFLUX_USER}
      - DOCKER_INFLUXDB_INIT_PASSWORD=${INFLUX_PASSWORD}
      - DOCKER_INFLUXDB_INIT_ORG=smart-factory
      - DOCKER_INFLUXDB_INIT_BUCKET=telemetry
    volumes:
      - influxdb-data:/var/lib/influxdb2
    restart: unless-stopped

  postgres:
    image: postgres:16
    container_name: postgres
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=production_records
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./data-pipeline/postgres/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.0.0
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_USER}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana-data:/var/lib/grafana
      - ./data-pipeline/grafana/dashboards:/etc/grafana/provisioning/dashboards
    depends_on:
      - influxdb
      - postgres
    restart: unless-stopped

  mqtt-bridge:
    build:
      context: ./iot-bridge
    container_name: mqtt-bridge
    depends_on:
      - mosquitto
      - influxdb
    environment:
      - MQTT_BROKER=mosquitto
      - INFLUX_URL=http://influxdb:8086
      - INFLUX_TOKEN=${INFLUX_TOKEN}
    restart: unless-stopped

volumes:
  influxdb-data:
  postgres-data:
  grafana-data:
```

## .env.example

```
INFLUX_USER=admin
INFLUX_PASSWORD=changeme123
INFLUX_TOKEN=replace-with-generated-token
POSTGRES_USER=factory_admin
POSTGRES_PASSWORD=changeme123
GRAFANA_USER=admin
GRAFANA_PASSWORD=changeme123
AWS_IOT_ENDPOINT=your-endpoint.iot.us-east-1.amazonaws.com
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
```

## Sprint Plan (Agile, 2-Week Sprints)

### Sprint 1 — Plant Simulation & PLC Logic
- Build a conveyor-and-sorting station scene in Factory I/O.
- Program Siemens TIA Portal (or CODESYS) logic: conveyor sequencing, part detection, E-stop interlocks.
- Expose Factory I/O tags via OPC-UA server; verify tag read/write with a UA client.
- Deliverable: working PLC logic driving the simulated conveyor, documented tag map (`plc/opcua-tag-map.csv`).

### Sprint 2 — SCADA & HMI
- Install Ignition; connect its OPC-UA client to the Factory I/O/PLC OPC-UA server.
- Build HMI screens: conveyor status, part counters, alarm banners.
- Configure OEE calculation tags (availability, performance, quality).
- Deliverable: Ignition project export with live dashboard screenshots.

### Sprint 3 — Robot Cell Simulation
- Set up ROS2 workspace with a UR10 URDF/description package.
- Launch Gazebo with the assembly-station world; configure MoveIt for pick-and-place motion planning.
- Validate trajectories in Python/MATLAB before executing in Gazebo.
- Deliverable: ROS2 launch file that runs a full pick-and-place cycle in simulation.

### Sprint 4 — Vision Inspection
- Attach a simulated camera topic in Gazebo.
- Build an OpenCV/YOLO inspection node that flags misaligned or defective parts.
- Publish pass/fail results over MQTT to trigger a reject-arm actuator in Factory I/O.
- Deliverable: `vision/inspection_node.py` with sample defect-detection output logged.

### Sprint 5 — IIoT & Cloud Integration
- Stand up Mosquitto broker; bridge PLC/vision MQTT topics to AWS IoT Core using an IoT rule.
- Route AWS IoT Core messages into a Dockerized InfluxDB bucket via a Lambda-style forwarder (or local `mqtt-bridge` service).
- Deliverable: telemetry flowing end-to-end from simulation to cloud to InfluxDB.

### Sprint 6 — Data, Dashboards & Documentation
- Store batch/production records in PostgreSQL (`data-pipeline/postgres/schema.sql`).
- Build Grafana dashboards: OEE trend, cycle time, downtime Pareto, predictive-maintenance alert panel.
- Write FMEA for the vision-inspection subsystem (`docs/fmea-vision-inspection.md`).
- Package everything with `docker-compose.yml` so a reviewer can run `docker compose up` and see live dashboards.
- Deliverable: final GitHub README, architecture diagram, and a 3–5 minute demo recording.

## Quick Start

```bash
git clone <your-repo-url>
cd smart-factory-digital-twin
cp .env.example .env
docker compose up -d
```

Then:
1. Open Factory I/O and load `robot-cell/gazebo_worlds/assembly_station.world` (or the Factory I/O scene file).
2. Launch the PLC logic in TIA Portal/CODESYS simulation mode.
3. Open Ignition and confirm the OPC-UA connection is live.
4. Run the ROS2 launch file: `ros2 launch robot-cell/ros2_ws/launch/factory_cell.launch.py`.
5. Start the vision node: `python vision/inspection_node.py`.
6. View live dashboards at `http://localhost:3000` (Grafana) and your Ignition Gateway URL.

## Standards Referenced

- ISO 10218 (industrial robot safety)
- IEC 62061 (functional safety of control systems)
- Lean/Six Sigma OEE methodology

## Notes

- All industrial software (TIA Portal, Ignition, Factory I/O) can be run in free trial or educational modes for portfolio purposes.
- Replace placeholder credentials in `.env` before running in any shared environment.
- This project is designed as a personal learning/portfolio build, not a production deployment.
