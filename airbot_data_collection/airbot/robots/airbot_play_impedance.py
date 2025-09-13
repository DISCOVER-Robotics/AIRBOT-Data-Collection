from discoverse.examples.force_control.impedance_control import ImpedanceController
from discoverse.examples.mocap_ik.mink_arm_ik import Mink_IK
from airbot_data_collection.airbot.robots.airbot_play import (
    AIRBOTPlay,
    AIRBOTPlayConfig,
)
from typing import List, Union
from threading import Thread
from pydantic import BaseModel, computed_field
import mujoco
import numpy as np
import time


class ImpedanceConfig(BaseModel):
    mjcf_path: str = ""
    kp: Union[List[float], np.ndarray] = [30, 100, 100, 10, 20, 20]
    kd: Union[List[float], np.ndarray] = [50, 50, 50, 2.0, 2.5, 1.0]
    jt_coeff: Union[List[float], np.ndarray] = [0.6, 0.6, 0.6, 1.35474, 1.32355, 1.5]
    control_rate: float = 100.0  # Hz


class AIRBOTPlayImpedanceConfig(AIRBOTPlayConfig):
    """Configuration for AIRBOTPlayImpedance."""

    impedance: ImpedanceConfig

    @computed_field
    @property
    def mit_action(self) -> bool:
        return self.impedance.mjcf_path != ""

    def model_post_init(self, context):
        self.impedance.kp = np.array(self.impedance.kp)
        self.impedance.kd = np.array(self.impedance.kd)
        self.impedance.jt_coeff = np.array(self.impedance.jt_coeff)
        if not (
            len(self.impedance.kp)
            == len(self.impedance.kd)
            == len(self.impedance.jt_coeff)
        ):
            raise ValueError("kp, kd, and jt_coeff must be of equal length.")
        super().model_post_init(context)


class AIRBOTPlayImpedance(AIRBOTPlay):
    config: AIRBOTPlayImpedanceConfig

    def on_configure(self) -> bool:
        self._running = True
        mjcf_path = self.config.impedance.mjcf_path
        self._use_ic = mjcf_path != ""
        if self._use_ic:
            mj_model = mujoco.MjModel.from_xml_path(mjcf_path)
            self.impedance_controller = ImpedanceController(
                mj_model,
                kpl=self.config.impedance.kp * 0.0,
                kdl=self.config.impedance.kd * 0.0,
            )
            self.ik_solver = Mink_IK(
                mjcf_path, arm_dof=len(self.config.impedance.jt_coeff)
            )
            self.fixed_orientation = np.array([0.707, 0.0, 0.707, 0.0])
            self._ic_thread = Thread(target=self._impedance_control_loop, daemon=True)
            self._ic_thread.start()
        return super().on_configure()

    def send_action(self, action):
        if self._use_ic:
            assert len(action) == 3, "Action must be a 3D position."
            # Solve inverse kinematics
            self.target_joints, converged = self.ik_solver.solve_ik(
                target_pos=np.array(action),
                target_ori=self.fixed_orientation,
                current_qpos=np.array(self.interface.get_joint_pos()),
            )
            if converged:
                self.impedance_controller.set_target(self.target_joints)
            else:
                self.get_logger().error("IK did not converge, skipping this command.")
        else:
            return super().send_action(action)

    def _impedance_control_loop(self):
        rate = self.config.impedance.control_rate
        dt = 1.0 / rate
        while self._running:
            self.impedance_controller.update_state(
                np.array(self.interface.get_joint_pos()),
                np.array(self.interface.get_joint_vel()),
                np.array(self.interface.get_joint_eff()),
            )
            self.current_wrench = self.impedance_controller.get_ext_force()
            torque_cmd = self.impedance_controller.compute_torque()
            self.interface.mit_joint_integrated_control(
                self.target_joints.tolist(),  # target joint position
                [0, 0, 0, 0, 0, 0],  # target joint velocity
                list(torque_cmd),  # target joint torque
                list(self.config.impedance.kp),
                list(self.config.impedance.kd),
            )
            time.sleep(dt)
