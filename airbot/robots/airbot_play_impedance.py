from discoverse.examples.force_control.impedance_control import ImpedanceController
from discoverse.examples.mocap_ik.mink_arm_ik import Mink_IK
from airbot_data_collection.airbot.robots.airbot_play import (
    AIRBOTPlay,
    AIRBOTPlayConfig,
    RobotMode,
    AIRBOTArm,
)
from typing import List, Union
from threading import Thread, Lock
from pydantic import BaseModel, computed_field, PositiveFloat, ConfigDict
from pathlib import Path
import mujoco
import numpy as np
import time


class ImpedanceConfig(BaseModel):
    """Configuration for ImpedanceController."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    mjcf_path: str | Path = ""
    kp: Union[List[float], np.ndarray] = [30, 100, 100, 10, 20, 20]
    kd: Union[List[float], np.ndarray] = np.array([50, 50, 50, 2.0, 2.5, 1.0]) * 0.01
    jt_coeff: Union[List[float], np.ndarray] = [0.6, 0.6, 0.6, 1.35474, 1.32355, 1.5]
    jt_max: Union[List[float], np.ndarray] = (
        np.array([10.0, 10.0, 10.0, 1.5, 1.5, 1.5]) * 0.5
    )
    control_rate: PositiveFloat = 250.0  # Hz

    def model_post_init(self, context):
        self.mjcf_path = str(self.mjcf_path)
        self.kp = np.array(self.kp)
        self.kd = np.array(self.kd)
        self.jt_coeff = np.array(self.jt_coeff)
        if not (len(self.kp) == len(self.kd) == len(self.jt_coeff)):
            raise ValueError("kp, kd, and jt_coeff must be of equal length.")


class AIRBOTPlayImpedanceConfig(AIRBOTPlayConfig):
    """Configuration for AIRBOTPlayImpedance."""

    impedance: ImpedanceConfig = ImpedanceConfig()

    @computed_field
    @property
    def mit_action(self) -> bool:
        return self.impedance.mjcf_path != ""

    @computed_field
    @property
    def pose_action(self) -> bool:
        return False


class AIRBOTPlayImpedance(AIRBOTPlay):
    config: AIRBOTPlayImpedanceConfig
    interface: AIRBOTArm

    def on_configure(self) -> bool:
        if super().on_configure():
            self._running = True
            mjcf_path = self.config.impedance.mjcf_path
            self._use_ic = mjcf_path != ""
            if self._use_ic:
                self._ic_lock = Lock()
                mj_model = mujoco.MjModel.from_xml_path(mjcf_path)
                self.impedance_controller = ImpedanceController(
                    mj_model,
                    kpl=self.config.impedance.kp * 0.0,
                    kdl=self.config.impedance.kd * 0.0,
                )
                self.ik_solver = Mink_IK(
                    mjcf_path, arm_dof=len(self.config.impedance.jt_coeff)
                )
                self._fixed_orientation = np.array([0.707, 0.0, 0.707, 0.0])  # wxyz
                self._ic_thread = Thread(
                    target=self._impedance_control_loop, daemon=True
                )
                self._ic_thread.start()
                self.impedance_controller.q_desired = None
            return True
        return False

    def send_action(self, action):
        assert len(action) == 3, "Action must be a 3D position."
        target_joints, converged = self.ik_solver.solve_ik(
            target_pos=np.array(action),
            target_ori=self._fixed_orientation,
            current_qpos=np.array(self.interface.get_joint_pos()),
        )
        if not converged:
            self.get_logger().error(f"IK did not converge for {action}!")
            return
        if self._use_ic and self.current_mode == SystemMode.SAMPLING:
            self.impedance_controller.set_target(target_joints)
        else:
            assert not self.config.pose_action, "Pose action is disabled."
            self.interface.move_to_joint_pos(
                target_joints.tolist(), self.current_mode == SystemMode.RESETTING
            )

    def on_switch_mode(self, mode):
        with self._ic_lock:
            self.impedance_controller.q_desired = None
            if mode is SystemMode.SAMPLING:
                return self.interface.switch_mode(RobotMode.MIT_INTEGRATED)
            elif mode is SystemMode.RESETTING:
                return self.interface.switch_mode(RobotMode.PLANNING_POS)
            else:
                return super().on_switch_mode(mode)

    def shutdown(self):
        if self._use_ic:
            self._running = False
            self._ic_thread.join(3.0)
        return super().shutdown()

    def _impedance_control_loop(self):
        rate = self.config.impedance.control_rate
        dt = 1.0 / rate
        while self._running:
            with self._ic_lock:
                if self.interface.get_control_mode() == RobotMode.MIT_INTEGRATED:
                    if self.impedance_controller.q_desired is not None:
                        self.impedance_controller.update_state(
                            np.array(self.interface.get_joint_pos()),
                            np.array(self.interface.get_joint_vel()),
                            np.array(self.interface.get_joint_eff()),
                        )
                        self.current_wrench = self.impedance_controller.get_ext_force()
                        torque_cmd = self.impedance_controller.compute_torque()
                        torque_cmd = np.clip(
                            torque_cmd * self.config.impedance.jt_coeff,
                            -self.config.impedance.jt_max,
                            self.config.impedance.jt_max,
                        )
                        # Send mit command
                        self.interface.mit_joint_integrated_control(
                            self.impedance_controller.q_desired.tolist(),  # target joint position
                            [0, 0, 0, 0, 0, 0],  # target joint velocity
                            torque_cmd.tolist(),  # target joint torque
                            self.config.impedance.kp.tolist(),
                            self.config.impedance.kd.tolist(),
                        )
                        # print(f"{self.impedance_controller.q_desired=}")
                        # print(f"{torque_cmd=}")
                        # self.get_logger().info
            time.sleep(dt)


if __name__ == "__main__":
    from airbot_data_collection.basis import SystemMode
    from discoverse import DISCOVERSE_ASSETS_DIR
    from airbot_data_collection.utils import init_logging

    init_logging()

    ic_play = AIRBOTPlayImpedance(
        AIRBOTPlayImpedanceConfig(
            port=50051,
            impedance=ImpedanceConfig(
                mjcf_path=Path(DISCOVERSE_ASSETS_DIR)
                / "mjcf/manipulator"
                / "robot_airbot_play_force.xml"
            ),
        )
    )
    assert ic_play.configure()

    assert ic_play.switch_mode(SystemMode.RESETTING)
    ic_play.send_action([0.259, -0.026, 0.176])
    input("Press Enter to continue...")
    assert ic_play.switch_mode(SystemMode.SAMPLING)
    assert ic_play.interface.get_control_mode() == RobotMode.MIT_INTEGRATED
    ic_play.send_action([0.259, -0.026, 0.176])
    input("Press Enter to exit...")
    print("Exiting...")
    assert ic_play.switch_mode(SystemMode.RESETTING)
    # ic_play.send_action([0.259, -0.026, 0.176])
    ic_play.shutdown()
