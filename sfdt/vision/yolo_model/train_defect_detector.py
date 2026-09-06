"""
train_defect_detector.py
--------------------------
Trains the YOLO model referenced by inspection_node.py
(vision/yolo_model/defect_detector.pt).

Prerequisites:
  1. A labeled dataset exported in YOLO format (e.g. from Roboflow) with
     a data.yaml describing train/val paths and class names.
  2. pip install ultralytics

Usage:
    python train_defect_detector.py --data dataset/data.yaml --epochs 100
"""

import argparse
from pathlib import Path

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to dataset.yaml (YOLO format)")
    parser.add_argument("--base-model", default="yolo11n.pt", help="Pretrained checkpoint to fine-tune from")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--output-name", default="defect_detector")
    args = parser.parse_args()

    model = YOLO(args.base_model)

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        name=args.output_name,
        patience=20,
        project="runs/detect",
    )

    metrics = model.val()
    print(f"mAP50-95: {metrics.box.map:.4f}, mAP50: {metrics.box.map50:.4f}")

    trained_weights = Path("runs/detect") / args.output_name / "weights" / "best.pt"
    target_path = Path("yolo_model") / "defect_detector.pt"
    target_path.parent.mkdir(exist_ok=True)

    if trained_weights.exists():
        target_path.write_bytes(trained_weights.read_bytes())
        print(f"Copied trained weights to {target_path}")
    else:
        print(f"Expected weights not found at {trained_weights}, check training run output above.")


if __name__ == "__main__":
    main()
