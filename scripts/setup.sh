#!/usr/bin/env bash
# ============================================================================
# setup.sh
# One-shot local environment bootstrap for the Smart Factory Digital Twin.
# Checks prerequisites, creates .env from the template, brings up the
# Docker Compose data stack, and initializes InfluxDB + PostgreSQL.
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
# ============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=== Smart Factory Digital Twin - Setup ==="
echo "Project root: ${PROJECT_ROOT}"

# ----------------------------------------------------------------------------
# 1. Check prerequisites
# ----------------------------------------------------------------------------
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "ERROR: '$1' is not installed or not on PATH. Please install it before continuing."
        exit 1
    fi
    echo "Found: $1"
}

echo ""
echo "--- Checking prerequisites ---"
check_command docker
check_command python3

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "ERROR: Neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi
echo "Using compose command: ${COMPOSE_CMD}"

# ----------------------------------------------------------------------------
# 2. Create .env from template if missing
# ----------------------------------------------------------------------------
echo ""
echo "--- Configuring environment ---"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Created .env from .env.example. Edit it with real credentials before continuing."
    else
        echo "WARNING: .env.example not found, you will need to create .env manually."
    fi
else
    echo ".env already exists, leaving it unchanged."
fi

# ----------------------------------------------------------------------------
# 3. Bring up the core data stack
# ----------------------------------------------------------------------------
echo ""
echo "--- Starting Docker Compose data stack ---"
${COMPOSE_CMD} up -d mosquitto influxdb postgres grafana

echo "Waiting for services to become healthy..."
sleep 10

# ----------------------------------------------------------------------------
# 4. Initialize InfluxDB buckets (requires INFLUX_TOKEN to already be set)
# ----------------------------------------------------------------------------
echo ""
echo "--- Initializing InfluxDB buckets ---"
if [ -f "data-pipeline/influxdb/init-bucket.sh" ]; then
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    if [ -n "${INFLUX_TOKEN:-}" ]; then
        chmod +x data-pipeline/influxdb/init-bucket.sh
        ./data-pipeline/influxdb/init-bucket.sh || echo "InfluxDB init script reported an issue, check manually."
    else
        echo "INFLUX_TOKEN not set in .env, skipping bucket initialization. Run data-pipeline/influxdb/init-bucket.sh manually once set."
    fi
else
    echo "data-pipeline/influxdb/init-bucket.sh not found, skipping."
fi

# ----------------------------------------------------------------------------
# 5. Verify PostgreSQL schema loaded correctly
# ----------------------------------------------------------------------------
echo ""
echo "--- Verifying PostgreSQL schema ---"
${COMPOSE_CMD} exec -T postgres psql -U "${POSTGRES_USER:-factory_admin}" -d production_records -c "\dt factory.*" \
    || echo "Could not verify schema automatically. Check with: docker compose exec postgres psql -U <user> -d production_records -c '\\dt factory.*'"

# ----------------------------------------------------------------------------
# 6. Install Python dependencies for vision + IoT bridge scripts
# ----------------------------------------------------------------------------
echo ""
echo "--- Installing Python dependencies ---"
if [ -f "vision/requirements.txt" ]; then
    python3 -m pip install -r vision/requirements.txt --quiet
    echo "Installed vision/requirements.txt"
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Open Grafana at http://localhost:3000 and log in with GRAFANA_USER/GRAFANA_PASSWORD from .env"
echo "  2. Import data-pipeline/grafana/dashboards/*.json"
echo "  3. Start Factory I/O and Ignition manually, then connect via scada/ignition/opcua-connection.json"
echo "  4. Launch the robot cell with: ros2 launch robot-cell/ros2_ws/launch/factory_cell.launch.py"
echo "  5. Run the vision node with: python vision/inspection_node.py --mode standalone --source 0"
