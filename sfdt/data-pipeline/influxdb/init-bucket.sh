#!/usr/bin/env bash
# ============================================================================
# init-bucket.sh
# Initializes InfluxDB buckets, an API token, and retention policies for the
# Smart Factory Digital Twin telemetry pipeline.
#
# The main "telemetry" bucket/org/user are already created automatically by
# the influxdb container's DOCKER_INFLUXDB_INIT_* environment variables in
# docker-compose.yml. This script is for anything beyond that first-run setup:
# additional buckets, a scoped read-only token for Grafana, and retention
# policy tuning.
#
# Usage:
#   docker compose up -d influxdb
#   ./data-pipeline/influxdb/init-bucket.sh
#
# Requires the InfluxDB CLI (`influx`) installed locally, or run this inside
# the container with: docker compose exec influxdb bash
# ============================================================================

set -euo pipefail

INFLUX_URL="${INFLUX_URL:-http://localhost:8086}"
INFLUX_ORG="${INFLUX_ORG:-smart-factory}"
INFLUX_TOKEN="${INFLUX_TOKEN:?Set INFLUX_TOKEN before running this script (see .env)}"

echo "Waiting for InfluxDB to become ready at ${INFLUX_URL}..."
until curl -sf "${INFLUX_URL}/health" > /dev/null; do
    sleep 2
done
echo "InfluxDB is ready."

# ----------------------------------------------------------------------------
# Primary telemetry bucket (created by DOCKER_INFLUXDB_INIT_BUCKET already,
# this call is idempotent-safe and will just report "already exists" if so).
# ----------------------------------------------------------------------------
influx bucket create \
    --name telemetry \
    --org "${INFLUX_ORG}" \
    --token "${INFLUX_TOKEN}" \
    --host "${INFLUX_URL}" \
    --retention 30d \
    || echo "Bucket 'telemetry' already exists, skipping."

# ----------------------------------------------------------------------------
# Long-term rollup bucket for downsampled OEE/PdM history (used by tasks
# below to keep raw high-frequency data from growing unbounded).
# ----------------------------------------------------------------------------
influx bucket create \
    --name telemetry_rollup_1y \
    --org "${INFLUX_ORG}" \
    --token "${INFLUX_TOKEN}" \
    --host "${INFLUX_URL}" \
    --retention 365d \
    || echo "Bucket 'telemetry_rollup_1y' already exists, skipping."

# ----------------------------------------------------------------------------
# Scoped read-only token for Grafana, so the dashboard connection doesn't
# use the all-access admin token.
# ----------------------------------------------------------------------------
echo "Creating a read-only Grafana token for bucket 'telemetry'..."
influx auth create \
    --org "${INFLUX_ORG}" \
    --token "${INFLUX_TOKEN}" \
    --host "${INFLUX_URL}" \
    --read-bucket "$(influx bucket list --org "${INFLUX_ORG}" --token "${INFLUX_TOKEN}" --host "${INFLUX_URL}" --name telemetry --hide-headers | awk '{print $1}')" \
    --description "grafana-readonly-telemetry" \
    || echo "Grafana read-only token may already exist, check 'influx auth list' if needed."

# ----------------------------------------------------------------------------
# Downsampling task: rolls up raw telemetry into hourly averages in the
# long-term bucket, keeping Grafana queries fast over multi-month ranges.
# ----------------------------------------------------------------------------
echo "Creating downsampling task for OEE and vibration metrics..."
cat <<'EOF' > /tmp/downsample_task.flux
option task = {name: "downsample_oee_hourly", every: 1h}

from(bucket: "telemetry")
  |> range(start: -task.every)
  |> filter(fn: (r) => r._measurement == "factory_plc_oee_metrics" or r._measurement == "factory_plc_conveyor_status")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> to(bucket: "telemetry_rollup_1y", org: "smart-factory")
EOF

influx task create \
    --org "${INFLUX_ORG}" \
    --token "${INFLUX_TOKEN}" \
    --host "${INFLUX_URL}" \
    --file /tmp/downsample_task.flux \
    || echo "Downsampling task may already exist, check 'influx task list' if needed."

rm -f /tmp/downsample_task.flux

echo "InfluxDB bucket initialization complete."
echo "Buckets: telemetry (30d retention), telemetry_rollup_1y (365d retention)"
echo "Remember to copy the Grafana read-only token above into your Grafana InfluxDB data source config."
