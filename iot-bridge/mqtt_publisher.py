"""
IoT Bridge: MQTT -> AWS IoT Core -> InfluxDB
----------------------------------------------
Subscribes to local factory MQTT topics (PLC telemetry + vision inspection
results published by inspection_node.py), forwards them to AWS IoT Core,
and writes every message into InfluxDB for Grafana dashboards.

Designed to run as the `mqtt-bridge` service in docker-compose.yml.

Environment variables (see .env.example):
    MQTT_BROKER, MQTT_PORT
    INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET
    AWS_IOT_ENDPOINT, AWS_IOT_CERT_PATH, AWS_IOT_KEY_PATH, AWS_IOT_CA_PATH
    ENABLE_AWS_FORWARDING (true/false)  -- set false for local-only testing
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mqtt-bridge")

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

TOPICS = [
    ("factory/vision/inspection_result", 1),
    ("factory/vision/heartbeat", 0),
    ("factory/plc/conveyor_status", 1),
    ("factory/plc/oee_metrics", 1),
]

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "smart-factory")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "telemetry")

ENABLE_AWS_FORWARDING = os.getenv("ENABLE_AWS_FORWARDING", "false").lower() == "true"
AWS_IOT_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT", "")
AWS_IOT_CERT_PATH = os.getenv("AWS_IOT_CERT_PATH", "certs/device.pem.crt")
AWS_IOT_KEY_PATH = os.getenv("AWS_IOT_KEY_PATH", "certs/private.pem.key")
AWS_IOT_CA_PATH = os.getenv("AWS_IOT_CA_PATH", "certs/AmazonRootCA1.pem")


class InfluxWriter:
    def __init__(self, url, token, org, bucket):
        self.bucket = bucket
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def write_message(self, topic: str, payload: dict):
        measurement = topic.replace("/", "_")
        point = Point(measurement).time(datetime.now(timezone.utc), WritePrecision.NS)

        for key, value in payload.items():
            if isinstance(value, (int, float)):
                point = point.field(key, value)
            else:
                point = point.tag(key, str(value))

        try:
            self.write_api.write(bucket=self.bucket, record=point)
        except Exception as exc:
            logger.error(f"InfluxDB write failed for topic {topic}: {exc}")

    def close(self):
        self.client.close()


class AWSIoTForwarder:
    """
    Thin wrapper around AWS IoT Device SDK v2. Only initialized when
    ENABLE_AWS_FORWARDING=true and valid certs are present.
    """

    def __init__(self, endpoint, cert_path, key_path, ca_path):
        from awscrt import mqtt as aws_mqtt
        from awsiot import mqtt_connection_builder

        self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=endpoint,
            cert_filepath=cert_path,
            pri_key_filepath=key_path,
            ca_filepath=ca_path,
            client_id="smart-factory-bridge",
            clean_session=False,
            keep_alive_secs=30,
        )
        connect_future = self.mqtt_connection.connect()
        connect_future.result()
        logger.info(f"Connected to AWS IoT Core at {endpoint}")

    def forward(self, topic: str, payload: dict):
        aws_topic = f"smart-factory/{topic}"
        self.mqtt_connection.publish(
            topic=aws_topic,
            payload=json.dumps(payload),
            qos=1,
        )

    def close(self):
        disconnect_future = self.mqtt_connection.disconnect()
        disconnect_future.result()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to local MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        for topic, qos in TOPICS:
            client.subscribe(topic, qos=qos)
            logger.info(f"Subscribed to {topic} (qos={qos})")
    else:
        logger.error(f"Failed to connect to MQTT broker, return code {rc}")


def make_on_message(influx_writer: InfluxWriter, aws_forwarder):
    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON payload on {msg.topic}, wrapping as raw value")
            payload = {"raw": msg.payload.decode("utf-8", errors="ignore")}

        logger.info(f"Received {msg.topic}: {payload}")

        influx_writer.write_message(msg.topic, payload)

        if aws_forwarder is not None:
            try:
                aws_forwarder.forward(msg.topic, payload)
            except Exception as exc:
                logger.error(f"AWS IoT forward failed for topic {msg.topic}: {exc}")

    return on_message


def main():
    influx_writer = InfluxWriter(INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET)

    aws_forwarder = None
    if ENABLE_AWS_FORWARDING:
        try:
            aws_forwarder = AWSIoTForwarder(
                AWS_IOT_ENDPOINT, AWS_IOT_CERT_PATH, AWS_IOT_KEY_PATH, AWS_IOT_CA_PATH
            )
        except Exception as exc:
            logger.warning(f"AWS IoT forwarding disabled, connection failed: {exc}")

    client = mqtt.Client(client_id="smart-factory-mqtt-bridge")
    client.on_connect = on_connect
    client.on_message = make_on_message(influx_writer, aws_forwarder)

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as exc:
            logger.warning(f"MQTT broker not ready ({exc}), retrying in 3s...")
            time.sleep(3)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down bridge...")
    finally:
        influx_writer.close()
        if aws_forwarder is not None:
            aws_forwarder.close()


if __name__ == "__main__":
    main()
