-- ============================================================================
-- schema.sql
-- PostgreSQL schema for the Smart Factory Digital Twin production database.
-- Loaded automatically by the postgres container via docker-entrypoint-initdb.d
-- (see docker-compose.yml). Stores batch/production records, inspection
-- results, downtime events, and maintenance records that complement the
-- time-series telemetry stored in InfluxDB.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS factory;
SET search_path TO factory, public;

-- ----------------------------------------------------------------------------
-- Shifts: operating shift windows, used to scope OEE and production reports
-- ----------------------------------------------------------------------------
CREATE TABLE shifts (
    shift_id        SERIAL PRIMARY KEY,
    shift_name      VARCHAR(50) NOT NULL,          -- e.g. 'Day', 'Swing', 'Night'
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- ----------------------------------------------------------------------------
-- Production runs: one row per shift execution on the assembly line
-- ----------------------------------------------------------------------------
CREATE TABLE production_runs (
    run_id              SERIAL PRIMARY KEY,
    shift_id            INTEGER REFERENCES shifts(shift_id),
    line_name           VARCHAR(100) NOT NULL DEFAULT 'assembly_line_1',
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    planned_units       INTEGER NOT NULL DEFAULT 0,
    operator_name       VARCHAR(100),
    notes               TEXT
);

-- ----------------------------------------------------------------------------
-- Parts: individual part records processed through the pick/inspect/place cycle
-- ----------------------------------------------------------------------------
CREATE TABLE parts (
    part_id             BIGSERIAL PRIMARY KEY,
    run_id              INTEGER REFERENCES production_runs(run_id),
    part_label          VARCHAR(50) NOT NULL,       -- matches vision node part_id, e.g. 'part-00001'
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    inspection_status   VARCHAR(30) NOT NULL,       -- pass / fail_misaligned / fail_defect / no_part_detected
    confidence_score    NUMERIC(5,4),
    offset_px           NUMERIC(8,2),
    robot_cycle_time_s  NUMERIC(6,3),
    destination         VARCHAR(30)                 -- assembly_fixture / reject_bin
);

CREATE INDEX idx_parts_run_id ON parts(run_id);
CREATE INDEX idx_parts_status ON parts(inspection_status);
CREATE INDEX idx_parts_detected_at ON parts(detected_at);

-- ----------------------------------------------------------------------------
-- Downtime events: unplanned stoppages, tied to fault codes from the PLC layer
-- ----------------------------------------------------------------------------
CREATE TABLE downtime_events (
    event_id            BIGSERIAL PRIMARY KEY,
    run_id              INTEGER REFERENCES production_runs(run_id),
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    fault_code          INTEGER,                    -- matches Fault_Code / SafetyFaultCode from PLC logic
    fault_description    VARCHAR(200),                -- e.g. 'E-Stop active', 'Robot cell not ready'
    duration_seconds    NUMERIC(10,2) GENERATED ALWAYS AS
                          (EXTRACT(EPOCH FROM (ended_at - started_at))) STORED,
    resolved_by         VARCHAR(100)
);

CREATE INDEX idx_downtime_run_id ON downtime_events(run_id);
CREATE INDEX idx_downtime_fault_code ON downtime_events(fault_code);

-- ----------------------------------------------------------------------------
-- OEE snapshots: periodic rollups written by a scheduled job or Ignition script
-- ----------------------------------------------------------------------------
CREATE TABLE oee_snapshots (
    snapshot_id         BIGSERIAL PRIMARY KEY,
    run_id              INTEGER REFERENCES production_runs(run_id),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    availability_pct    NUMERIC(5,2) NOT NULL,
    performance_pct     NUMERIC(5,2) NOT NULL,
    quality_pct         NUMERIC(5,2) NOT NULL,
    oee_overall_pct     NUMERIC(5,2) GENERATED ALWAYS AS
                          (availability_pct * performance_pct * quality_pct / 10000) STORED
);

CREATE INDEX idx_oee_run_id ON oee_snapshots(run_id);
CREATE INDEX idx_oee_recorded_at ON oee_snapshots(recorded_at);

-- ----------------------------------------------------------------------------
-- Predictive maintenance alerts: forwarded from AWS IoT Core / cloud analytics
-- ----------------------------------------------------------------------------
CREATE TABLE maintenance_alerts (
    alert_id            BIGSERIAL PRIMARY KEY,
    asset_name          VARCHAR(100) NOT NULL,       -- e.g. 'conveyor_motor', 'ur10_joint_3', 'reject_arm_solenoid'
    alert_level         VARCHAR(20) NOT NULL,        -- normal / warning / critical
    metric_name         VARCHAR(100),                -- e.g. 'vibration_rms', 'cycle_time_drift'
    metric_value        NUMERIC(12,4),
    triggered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at     TIMESTAMPTZ,
    acknowledged_by     VARCHAR(100),
    notes               TEXT
);

CREATE INDEX idx_maintenance_asset ON maintenance_alerts(asset_name);
CREATE INDEX idx_maintenance_level ON maintenance_alerts(alert_level);
CREATE INDEX idx_maintenance_triggered_at ON maintenance_alerts(triggered_at);

-- ----------------------------------------------------------------------------
-- FMEA register: risk log for the vision-inspection subsystem (and others)
-- ----------------------------------------------------------------------------
CREATE TABLE fmea_register (
    fmea_id             SERIAL PRIMARY KEY,
    subsystem           VARCHAR(100) NOT NULL,       -- e.g. 'Vision Inspection', 'Reject Arm Actuator'
    failure_mode        VARCHAR(200) NOT NULL,
    effect              TEXT,
    severity            SMALLINT CHECK (severity BETWEEN 1 AND 10),
    occurrence          SMALLINT CHECK (occurrence BETWEEN 1 AND 10),
    detection           SMALLINT CHECK (detection BETWEEN 1 AND 10),
    rpn                 SMALLINT GENERATED ALWAYS AS (severity * occurrence * detection) STORED,
    recommended_action  TEXT,
    owner               VARCHAR(100),
    status              VARCHAR(30) DEFAULT 'open'
);

-- ----------------------------------------------------------------------------
-- Seed data: default shift schedule and a sample FMEA entry
-- ----------------------------------------------------------------------------
INSERT INTO shifts (shift_name, start_time, end_time) VALUES
    ('Day',   '06:00', '14:00'),
    ('Swing', '14:00', '22:00'),
    ('Night', '22:00', '06:00');

INSERT INTO fmea_register (subsystem, failure_mode, effect, severity, occurrence, detection, recommended_action, owner)
VALUES (
    'Vision Inspection',
    'Camera misdetects part alignment due to lighting variation',
    'Good part incorrectly rejected, reducing throughput',
    6, 4, 5,
    'Add lighting normalization preprocessing step; retrain YOLO model with varied lighting dataset',
    'Vinay Shanamoni'
);

-- ----------------------------------------------------------------------------
-- Convenience view: current shift OEE and reject rate for Grafana/Ignition
-- ----------------------------------------------------------------------------
CREATE VIEW v_current_run_summary AS
SELECT
    pr.run_id,
    pr.line_name,
    pr.started_at,
    COUNT(p.part_id) AS total_parts,
    COUNT(*) FILTER (WHERE p.inspection_status = 'pass') AS parts_passed,
    COUNT(*) FILTER (WHERE p.inspection_status LIKE 'fail%') AS parts_rejected,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE p.inspection_status = 'pass') / NULLIF(COUNT(p.part_id), 0), 2
    ) AS quality_pct,
    (SELECT oee_overall_pct FROM oee_snapshots os WHERE os.run_id = pr.run_id ORDER BY recorded_at DESC LIMIT 1) AS latest_oee_pct
FROM production_runs pr
LEFT JOIN parts p ON p.run_id = pr.run_id
WHERE pr.ended_at IS NULL
GROUP BY pr.run_id, pr.line_name, pr.started_at;
