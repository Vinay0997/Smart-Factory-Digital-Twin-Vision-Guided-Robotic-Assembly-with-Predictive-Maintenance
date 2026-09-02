"""
Vision Inspection Node
-----------------------
Subscribes to a simulated camera feed (Gazebo ROS2 topic or local webcam/video
file for standalone testing), runs defect/misalignment detection with
OpenCV + a YOLO model, and publishes pass/fail results over MQTT so the
PLC/Factory I/O reject-arm actuator can react.

Two run modes:
  1. ROS2 mode  -> subscribes to /camera/image_raw (sensor_msgs/Image)
  2. Standalone -> reads from a local webcam or video file for quick testing
     without a full ROS2/Gazebo stack running.

Usage:
    python inspection_node.py --mode standalone --source 0
    python inspection_node.py --mode ros2
"""

import argparse
import json
import time
from dataclasses import dataclass

import cv2
import numpy as np
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_RESULT = "factory/vision/inspection_result"
MQTT_TOPIC_HEARTBEAT = "factory/vision/heartbeat"

CONFIDENCE_THRESHOLD = 0.5
MISALIGNMENT_PX_TOLERANCE = 15
EXPECTED_CENTER = (320, 240)


@dataclass
class InspectionResult:
    part_id: str
    status: str
    confidence: float
    offset_px: float
    timestamp: float

    def to_json(self) -> str:
        return json.dumps({
            "part_id": self.part_id,
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "offset_px": round(self.offset_px, 2),
            "timestamp": self.timestamp,
        })


class MQTTPublisher:
    def __init__(self, broker: str, port: int):
        self.client = mqtt.Client(client_id="vision-inspection-node")
        self.client.connect(broker, port, keepalive=60)
        self.client.loop_start()

    def publish_result(self, result: InspectionResult):
        self.client.publish(MQTT_TOPIC_RESULT, result.to_json(), qos=1)

    def publish_heartbeat(self):
        self.client.publish(MQTT_TOPIC_HEARTBEAT, json.dumps({"alive": True, "ts": time.time()}))

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


class DefectDetector:
    """
    Lightweight stand-in detector. Replace `_run_yolo` with a real
    ultralytics YOLO call once yolo_model/defect_detector.pt is trained.
    """

    def __init__(self, model_path: str = "yolo_model/defect_detector.pt", use_yolo: bool = False):
        self.use_yolo = use_yolo
        self.model = None
        if use_yolo:
            from ultralytics import YOLO
            self.model = YOLO(model_path)

    def inspect(self, frame: np.ndarray, part_id: str) -> InspectionResult:
        if self.use_yolo and self.model is not None:
            return self._run_yolo(frame, part_id)
        return self._run_classical_cv(frame, part_id)

    def _run_classical_cv(self, frame: np.ndarray, part_id: str) -> InspectionResult:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 60, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return InspectionResult(part_id, "no_part_detected", 0.0, 0.0, time.time())

        largest = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest)
        if M["m00"] == 0:
            return InspectionResult(part_id, "no_part_detected", 0.0, 0.0, time.time())

        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        offset = float(np.hypot(cx - EXPECTED_CENTER[0], cy - EXPECTED_CENTER[1]))

        status = "pass" if offset <= MISALIGNMENT_PX_TOLERANCE else "fail_misaligned"
        confidence = max(0.0, 1.0 - (offset / (EXPECTED_CENTER[0])))
        return InspectionResult(part_id, status, confidence, offset, time.time())

    def _run_yolo(self, frame: np.ndarray, part_id: str) -> InspectionResult:
        results = self.model.predict(frame, verbose=False)
        if not results or len(results[0].boxes) == 0:
            return InspectionResult(part_id, "no_part_detected", 0.0, 0.0, time.time())

        box = results[0].boxes[0]
        conf = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        offset = float(np.hypot(cx - EXPECTED_CENTER[0], cy - EXPECTED_CENTER[1]))

        status = "pass" if (conf >= CONFIDENCE_THRESHOLD and offset <= MISALIGNMENT_PX_TOLERANCE) else "fail_defect"
        return InspectionResult(part_id, status, conf, offset, time.time())


def run_standalone(source, detector: DefectDetector, publisher: MQTTPublisher):
    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else source)
    part_counter = 0
    last_heartbeat = time.time()

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            part_counter += 1
            part_id = f"part-{part_counter:05d}"
            result = detector.inspect(frame, part_id)
            publisher.publish_result(result)
            print(f"[{part_id}] status={result.status} confidence={result.confidence:.2f} offset={result.offset_px:.1f}px")

            if time.time() - last_heartbeat > 5:
                publisher.publish_heartbeat()
                last_heartbeat = time.time()

            cv2.imshow("Vision Inspection", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def run_ros2(detector: DefectDetector, publisher: MQTTPublisher):
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from cv_bridge import CvBridge

    class InspectionNode(Node):
        def __init__(self):
            super().__init__("vision_inspection_node")
            self.bridge = CvBridge()
            self.part_counter = 0
            self.subscription = self.create_subscription(
                Image, "/camera/image_raw", self.image_callback, 10
            )
            self.get_logger().info("Vision inspection node started, listening on /camera/image_raw")

        def image_callback(self, msg: Image):
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            self.part_counter += 1
            part_id = f"part-{self.part_counter:05d}"
            result = detector.inspect(frame, part_id)
            publisher.publish_result(result)
            self.get_logger().info(f"[{part_id}] status={result.status} confidence={result.confidence:.2f}")

    rclpy.init()
    node = InspectionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Vision inspection node for the smart factory pipeline")
    parser.add_argument("--mode", choices=["standalone", "ros2"], default="standalone")
    parser.add_argument("--source", default="0", help="Camera index or video file path (standalone mode)")
    parser.add_argument("--use-yolo", action="store_true", help="Use trained YOLO model instead of classical CV")
    parser.add_argument("--broker", default=MQTT_BROKER)
    parser.add_argument("--port", type=int, default=MQTT_PORT)
    args = parser.parse_args()

    detector = DefectDetector(use_yolo=args.use_yolo)
    publisher = MQTTPublisher(args.broker, args.port)

    try:
        if args.mode == "standalone":
            run_standalone(args.source, detector, publisher)
        else:
            run_ros2(detector, publisher)
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
