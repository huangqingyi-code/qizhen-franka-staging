"""One path contract for the 2026-10-18 ribbon workspace layout."""

from pathlib import Path


def adapter_manual():
    """Use the release-owned manual both from source and from an installed package."""
    root = Path(__file__).resolve().parent
    if root.name == "src" and (root.parent / "adapter.json").is_file():
        root = root.parent
    return root / "docs/AGENT_OPERATIONS.md"


class Workspace:
    def __init__(self, config):
        self.root = Path(config["workspace"])
        self.pipeline = self.root / "pipeline"
        self.ros = self.root / "ros"
        self.tools = self.pipeline / "tools"
        self.examples = self.root / "libfranka/build/examples"
        self.nokov = self.root / "Nokov/recorder/build/nokov_recorder"
        self.start_pose = self.ros / "src/franka_motion_planner/config/franka_start_pose.yaml"
        self.manual = adapter_manual()
        # 2026-10-22 起任务根在 workspace 根（旧版在 pipeline/trajectories），
        # 保留旧位置回退，便于滚动升级期间两种布局都能用。
        current, legacy = self.root / "trajectories", self.pipeline / "trajectories"
        self.tasks = current if current.is_dir() or not legacy.is_dir() else legacy
        self.audit = self.pipeline / "execution_logs"

    def checks(self, config):
        return [
            Path(config["ros_setup"]),
            Path(config["python_executable"]),
            self.ros / "install/setup.bash",
            self.tools / "run_pipeline.py",
            self.tools / "ribbon_level.py",
            self.tools / "pipeline_videos.py",
            self.examples / "read_franka_state",
            self.examples / "cartesian_delta_move",
            self.nokov,
            self.start_pose,
            self.manual,
            self.root / "ati/ati_capture_adapter.py",
        ]
