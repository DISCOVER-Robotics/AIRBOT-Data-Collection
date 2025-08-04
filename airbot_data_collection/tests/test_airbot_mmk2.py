from airbot_py.airbot_mmk2 import AirbotMMK2
from mmk2_types.types import (
    RobotComponents,
    JointNames,
    ComponentTypes,
    TopicNames,
    RobotComponentsGroup,
    ImageTypes,
    ControllerTypes,
)
from mmk2_types.grpc_msgs import (
    Time,
    JointState,
    TrajectoryParams,
    MoveServoParams,
    TrackingParams,
    ForwardPositionParams,
)
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, replace, field
import time
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AIRBOTMMK2Config:
    name: str = "mmk2"
    domain_id: int = -1
    ip: str = "192.168.11.200"
    port: int = 50055
    default_action: Optional[List[float]] = field(
        default_factory=lambda: [
            -0.233,
            -0.73,
            1.088,
            1.774,
            -1.1475,
            -0.1606,  # left_arm (6 joints)
            0.0,  # left_arm_eef (1 joint)
            0.2258,
            -0.6518,
            0.9543,
            -1.777,
            1.0615,
            0.3588,  # right_arm (6 joints)
            0.0,  # right_arm_eef (1 joint)
            0.0,
            -0.5,  # head (2 joints)
            0.15,  # spine (1 joint)
        ]
    )
    # cameras: Dict[str, List[str]] = field(default_factory=lambda: {})
    cameras: Dict[str, List[str]] = field(
        default_factory=lambda: {
            RobotComponents.HEAD_CAMERA: [ImageTypes.COLOR],
            RobotComponents.LEFT_CAMERA: [ImageTypes.COLOR],
            RobotComponents.RIGHT_CAMERA: [ImageTypes.COLOR],
        }
    )
    components: List[str] = field(
        default_factory=lambda: [
            RobotComponents.LEFT_ARM.value,
            RobotComponents.LEFT_ARM_EEF.value,
            RobotComponents.RIGHT_ARM.value,
            RobotComponents.RIGHT_ARM_EEF.value,
            RobotComponents.HEAD.value,
            RobotComponents.SPINE.value,
        ]
    )
    demonstrate: bool = True


class AIRBOTMMK2:
    def __init__(self, config: Optional[AIRBOTMMK2Config] = None, **kwargs) -> None:
        if config is None:
            config = AIRBOTMMK2Config()
        self.config = replace(config, **kwargs)
        self.robot = AirbotMMK2(
            self.config.ip,
            self.config.port,
            self.config.name,
            self.config.domain_id,
        )
        self.joint_names = {}
        self.cameras: Dict[RobotComponents, str] = {}
        self.components: Dict[RobotComponents, ComponentTypes] = {}
        all_joint_names = JointNames()
        self.joint_num = 0
        for k, types in self.config.cameras.items():
            self.cameras[RobotComponents(k)] = [ImageTypes(v) for v in types]
        for comp_str in self.config.components:
            comp = RobotComponents(comp_str)
            # TODO: get the type info from SDK
            self.components[comp] = ComponentTypes.UNKNOWN
            names = all_joint_names.__dict__[comp_str]
            self.joint_names[comp] = names
            self.joint_num += len(names)
        logger.info(f"Components: {self.components}")
        logger.info(f"Joint numbers: {self.joint_num}")

        self.robot.enable_resources(
            {
                comp: {
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                }
                for comp in self.cameras
            }
        )
        # use stream to get images
        # self.robot.enable_stream(self.robot.get_image, self.cameras)
        if self.config.demonstrate:
            comp_action_topic = {
                comp: TopicNames.tracking.format(component=comp.value)
                for comp in RobotComponentsGroup.ARMS
            }
            comp_action_topic.update(
                {
                    comp: TopicNames.controller_command.format(
                        component=comp.value,
                        controller=ControllerTypes.FORWARD_POSITION.value,
                    )
                    for comp in RobotComponentsGroup.HEAD_SPINE
                }
            )
            self.robot.listen_to(list(comp_action_topic.values()))
            self._comp_action_topic = comp_action_topic
        self.logs = {}
        self.enter_active_mode = lambda: self._set_mode("active")
        self.enter_passive_mode = lambda: self._set_mode("passive")
        self.get_state_mode = lambda: self._state_mode
        self.exit = lambda: None
        self.reset()

    def reset(self, sleep_time=0):
        if self.config.default_action is not None:
            goal = self._action_to_goal(self.config.default_action)
            logger.info(f"Reset to default action: {self.config.default_action}")
            # logger.info(f"Reset to default goal: {goal}")
            # TODO: hard code for spine&head control
            self.robot.set_goal(goal, TrajectoryParams())
        else:
            logger.warning("No default action is set.")
        time.sleep(sleep_time)
        self.enter_servo_mode()

    def send_action(self, action, wait=False):
        goal = self._action_to_goal(action)
        # logger.info(f"Send action: {action}")
        # logger.info(f"Send goal: {goal}")

        # param = MoveServoParams(header=self.robot.get_header())
        if self.traj_mode:
            self.robot.set_goal(goal, TrajectoryParams())
        else:
            param = ForwardPositionParams()

            self.robot.set_goal(goal, param)

    def get_low_dim_data(self):
        data = {}
        robot_state = self.robot.get_robot_state()
        all_joints = robot_state.joint_state
        # logger.info(f"joint_stamp: {all_joints.header.stamp}")
        for comp in self.components:
            joint_states = self.robot.get_joint_values_by_names(
                all_joints, self.joint_names[comp]
            )
            data[f"observation/{comp.value}/joint_position"] = joint_states
            if comp == RobotComponents.BASE:
                base_pose = robot_state.base_state.pose
                base_vel = robot_state.base_state.velocity
                data_pose = [
                    base_pose.x,
                    base_pose.y,
                    base_pose.theta,
                ]
                data[f"action/{comp.value}/pose"] = data_pose
                data_vel = [
                    base_vel.x,
                    base_vel.y,
                    base_vel.omega,
                ]
                data[f"action/{comp.value}/velocity"] = data_vel
                data[f"action/{comp.value}/joint_position"] = data_vel + data_pose
            if self.config.demonstrate:
                if comp in RobotComponentsGroup.ARMS:
                    arm_jn = JointNames().__dict__[comp.value]
                    comp_eef = comp.value + "_eef"
                    eef_jn = JointNames().__dict__[comp_eef]
                    js = self.robot.get_listened(self._comp_action_topic[comp])
                    jq = self.robot.get_joint_values_by_names(js, arm_jn + eef_jn)
                    data[f"action/{comp.value}/joint_position"] = jq[:-1]
                    # the eef joint is in arms
                    data[f"action/{comp_eef}/joint_position"] = jq[-1:]
                elif comp in RobotComponentsGroup.HEAD_SPINE:
                    jq = list(
                        self.robot.get_listened(self._comp_action_topic[comp]).data
                    )
                    data[f"action/{comp.value}/joint_position"] = jq
        return data

    def _capture_images(self) -> Tuple[Dict[str, bytes], Dict[str, Time]]:
        images = {}
        img_stamps: Dict[RobotComponents, Time] = {}
        before_camread_t = time.perf_counter()
        comp_images = self.robot.get_image(self.cameras)
        for comp, image in comp_images.items():
            # TODO: now only support for color image
            images[comp.value] = image.data[ImageTypes.COLOR]
            img_stamps[comp.value] = image.stamp

        print(f"async_read_camera_{time.perf_counter() - before_camread_t}_dt_s")

        return images, img_stamps

    def capture_observation(self):
        """The returned observations do not have a batch dimension."""
        # Capture images from cameras
        images, img_stamps = self._capture_images()
        low_dim_data = self.get_low_dim_data()

        obs_act_dict = {}
        for comp, stamp in img_stamps.items():
            obs_act_dict[f"/time/{comp}"] = stamp.sec + stamp.nanosec * 1e-9
        # Populate output dictionaries and format to pytorch
        obs_act_dict["low_dim"] = low_dim_data
        for name in images:
            # print(images[name].shape)
            obs_act_dict[f"observation.images.{name}"] = images[name]
        return obs_act_dict

    def low_dim_to_action(self, low_dim: dict, step: int) -> list:
        action = []
        # logger.info(low_dim.keys())
        for comp in self.components:
            # action.extend(low_dim[f"action/{comp.value}/joint_position"][step])
            # old version
            if comp in RobotComponentsGroup.ARMS_EEFS:
                pos_comp = comp.value.split("_")
                key = f"{pos_comp[1]}/{pos_comp[0]}"
            else:
                key = comp.value
            action.extend(low_dim[f"action/{key}/joint_position"][step])
        return action

    def _set_mode(self, mode):
        self._state_mode = mode

    def _action_check(self, action):
        assert len(action) == self.joint_num, (
            f"Invalid action {action} with length: {len(action)}"
        )

    def _action_to_goal(self, action) -> Dict[RobotComponents, JointState]:
        self._action_check(action)
        goal = {}
        j_cnt = 0
        for comp in self.components:
            end = j_cnt + len(self.joint_names[comp])
            goal[comp] = JointState(position=action[j_cnt:end])
            j_cnt = end
        return goal

    def enter_traj_mode(self):
        self.traj_mode = True

    def enter_servo_mode(self):
        self.traj_mode = False


def main():
    mmk = AIRBOTMMK2()
    # robot.reset()
    for i in range(100000):
        mmk.capture_observation()


if __name__ == "__main__":
    main()
