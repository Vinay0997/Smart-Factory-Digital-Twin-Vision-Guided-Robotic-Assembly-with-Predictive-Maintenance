"""
validate_kinematics.py
-------------------------
Offline validation of UR10 pick-and-place trajectories before running them
in Gazebo/MoveIt. Mirrors the "Built MATLAB-based simulation models to
validate kinematic trajectories...before hardware deployment" step from the
PlebC Innovations TORUS project, reimplemented in Python for this project.

Uses forward kinematics (DH parameters) to check that the named poses in
POSES (matching pick_place_node.py and ur10.srdf) are reachable and that
joint-space trajectories between them stay within velocity/acceleration
limits defined in ur10_moveit_config/config/joint_limits.yaml, without
needing MoveIt or a running simulation.

Usage:
    python validate_kinematics.py
    python validate_kinematics.py --plot   # requires matplotlib, saves PNG
"""

import argparse
import numpy as np

# UR10 DH parameters (standard convention): a, alpha, d, theta_offset (meters/radians)
UR10_DH = [
    {"a": 0.0,      "alpha": np.pi / 2, "d": 0.1273,  "theta_offset": 0.0},
    {"a": -0.612,   "alpha": 0.0,       "d": 0.0,     "theta_offset": 0.0},
    {"a": -0.5723,  "alpha": 0.0,       "d": 0.0,     "theta_offset": 0.0},
    {"a": 0.0,      "alpha": np.pi / 2, "d": 0.163941,"theta_offset": 0.0},
    {"a": 0.0,      "alpha": -np.pi / 2,"d": 0.1157,  "theta_offset": 0.0},
    {"a": 0.0,      "alpha": 0.0,       "d": 0.0922,  "theta_offset": 0.0},
]

JOINT_VELOCITY_LIMITS = {
    "shoulder_pan_joint": 2.16,
    "shoulder_lift_joint": 2.16,
    "elbow_joint": 3.15,
    "wrist_1_joint": 3.2,
    "wrist_2_joint": 3.2,
    "wrist_3_joint": 3.2,
}
JOINT_NAMES = list(JOINT_VELOCITY_LIMITS.keys())
JOINT_ACCEL_LIMIT = 5.0  # rad/s^2, matches joint_limits.yaml

# Named joint-space configurations, matching ur10.srdf group_states
JOINT_STATES = {
    "home":    [0.0, -1.5708, 1.5708, -1.5708, -1.5708, 0.0],
    "observe": [0.4, -1.2,    1.4,    -1.7,    -1.5708, 0.0],
}


def dh_transform(a, alpha, d, theta):
    ct, st = np.cos(theta), np.sin(theta)
    ca, sa = np.cos(alpha), np.sin(alpha)
    return np.array([
        [ct, -st * ca,  st * sa, a * ct],
        [st,  ct * ca, -ct * sa, a * st],
        [0.0,       sa,       ca,      d],
        [0.0,      0.0,      0.0,    1.0],
    ])


def forward_kinematics(joint_angles):
    """Returns the 4x4 end-effector pose in the base frame for a given joint config."""
    T = np.eye(4)
    for joint_angle, dh in zip(joint_angles, UR10_DH):
        T = T @ dh_transform(dh["a"], dh["alpha"], dh["d"], joint_angle + dh["theta_offset"])
    return T


def check_workspace_reachability(position, max_reach=1.3, min_reach=0.2):
    """UR10 has an approx 1.3m reach; flag poses outside a plausible working envelope."""
    distance = np.linalg.norm(position)
    return min_reach <= distance <= max_reach, distance


def validate_trajectory_dynamics(q_start, q_end, duration_s):
    """
    Checks whether a straight-line joint-space move between two configurations
    stays within per-joint velocity and acceleration limits for a given
    planned duration, using a simple trapezoidal-velocity assumption.
    """
    results = []
    for i, joint_name in enumerate(JOINT_NAMES):
        delta = q_end[i] - q_start[i]
        avg_velocity = abs(delta) / duration_s if duration_s > 0 else float("inf")
        peak_velocity = avg_velocity * 2  # trapezoidal profile peak ~2x average
        peak_accel = peak_velocity / (duration_s / 2) if duration_s > 0 else float("inf")

        vel_ok = peak_velocity <= JOINT_VELOCITY_LIMITS[joint_name]
        accel_ok = peak_accel <= JOINT_ACCEL_LIMIT

        results.append({
            "joint": joint_name,
            "delta_rad": round(delta, 4),
            "peak_velocity": round(peak_velocity, 3),
            "velocity_limit": JOINT_VELOCITY_LIMITS[joint_name],
            "velocity_ok": vel_ok,
            "peak_accel": round(peak_accel, 3),
            "accel_limit": JOINT_ACCEL_LIMIT,
            "accel_ok": accel_ok,
        })
    return results


def run_validation(plot: bool = False):
    print("=== Forward Kinematics Validation ===")
    ee_positions = {}
    for name, joints in JOINT_STATES.items():
        T = forward_kinematics(joints)
        position = T[:3, 3]
        ee_positions[name] = position
        reachable, distance = check_workspace_reachability(position)
        status = "OK" if reachable else "OUT OF RANGE"
        print(f"[{name}] EE position (base frame): {np.round(position, 4)} m, "
              f"reach={distance:.3f}m -> {status}")

    print("\n=== Trajectory Dynamics Validation (home -> observe, 2.0s planned duration) ===")
    dynamics = validate_trajectory_dynamics(JOINT_STATES["home"], JOINT_STATES["observe"], duration_s=2.0)
    all_ok = True
    for r in dynamics:
        ok = r["velocity_ok"] and r["accel_ok"]
        all_ok = all_ok and ok
        flag = "OK" if ok else "LIMIT EXCEEDED"
        print(f"  {r['joint']:22s} delta={r['delta_rad']:+.3f} rad  "
              f"v_peak={r['peak_velocity']:.2f}/{r['velocity_limit']:.2f} rad/s  "
              f"a_peak={r['peak_accel']:.2f}/{r['accel_limit']:.2f} rad/s^2  [{flag}]")

    print(f"\nOverall trajectory validation: {'PASS' if all_ok else 'FAIL - increase planned duration or use MoveIt time parameterization'}")

    if plot:
        _plot_trajectory(ee_positions)


def _plot_trajectory(ee_positions):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111, projection="3d")

    names = list(ee_positions.keys())
    coords = np.array([ee_positions[n] for n in names])
    ax.plot(coords[:, 0], coords[:, 1], coords[:, 2], "o-", color="#2874A6", linewidth=2, markersize=8)
    for n, c in zip(names, coords):
        ax.text(c[0], c[1], c[2], n, fontsize=9)

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title("UR10 End-Effector Path: Named Pose Validation")

    import os
    os.makedirs("output", exist_ok=True)
    plt.savefig("output/kinematics_validation.png", dpi=150, bbox_inches="tight")
    print("Saved plot to output/kinematics_validation.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot", action="store_true", help="Save a 3D plot of the validated end-effector path")
    args = parser.parse_args()
    run_validation(plot=args.plot)
