from pydantic import BaseModel, PositiveInt
from airbot_data_collection.basis import System
from mmk2_types.types import (
    MMK2Components,
    ImageTypes,
    TopicNames,
    MMK2ComponentsGroup,
    ControllerTypes,
    JointNames,
)
from mmk2_types.grpc_msgs import JointState, Time
from airbot_py.airbot_mmk2 import AirbotMMK2
from pydantic import BaseModel, PositiveInt
from typing import Optional, List, Union, Dict, Tuple


class AIRBOTMMKConfig(BaseModel):
    ip: str = "192.168.11.200"
    port: PositiveInt = 50055
    name: Optional[str] = None
    domain_id: Optional[int] = None
    components: List[Union[str, MMK2Components]] = []
    cameras: Dict[Union[str, MMK2Components], Dict[str, str]] = {}
    demonstrate: bool = True

    def model_post_init(self, context):
        for i, component in enumerate(self.components):
            if isinstance(component, str):
                self.components[i] = MMK2Components[component.upper()]
        for cam in list(self.cameras.keys()):
            if isinstance(cam, str):
                self.cameras[MMK2Components[cam.upper()]] = self.cameras.pop(cam)


class AIRBOTMMK(System):
    config: AIRBOTMMKConfig

    def on_configure(self) -> bool:
        self.interface = AirbotMMK2(**self.config.model_dump())
        self._action_topics = {
            comp: TopicNames.tracking.format(component=comp.value)
            for comp in MMK2ComponentsGroup.ARMS
        }
        self._action_topics.update(
            {
                comp: TopicNames.controller_command.format(
                    component=comp.value,
                    controller=ControllerTypes.FORWARD_POSITION.value,
                )
                for comp in MMK2ComponentsGroup.HEAD_SPINE
            }
        )
        self.interface.listen_to(self._action_topics.values())
        self.interface.enable_resources(self.config.cameras)
        self._joint_names = JointNames().__dict__
        self._check_joints(self.interface.get_robot_state().joint_state.name)
        return True

    def send_action(self, action):
        pass

    def on_switch_mode(self, mode):
        return True

    def _get_low_dim(self):
        data = {}
        robot_state = self.interface.get_robot_state()
        all_joints = robot_state.joint_state
        stamp = robot_state.joint_state.header.stamp
        t = stamp.sec + stamp.nanosec * 1e-9
        for comp in self.config.components:
            comp_name = comp.value
            self._set_js_bson(data, comp, t, all_joints)
            if comp == MMK2Components.BASE:
                base_pose = robot_state.base_state.pose
                base_vel = robot_state.base_state.velocity
                data_pose = [
                    base_pose.x,
                    base_pose.y,
                    base_pose.theta,
                ]
                # data[f"action/{comp_name}/pose"] = data_pose
                data_vel = [
                    base_vel.x,
                    base_vel.y,
                    base_vel.omega,
                ]
                data[f"action/{comp_name}/joint_state"] = {
                    "t": t,
                    "data": {
                        "pos": data_pose,
                        "vel": data_vel,
                        "eff": [0.0] * len(data_pose),
                    },
                }
            if self.config.demonstrate:
                if comp in MMK2ComponentsGroup.ARMS:
                    arm_jn = self._joint_names[comp.value]
                    comp_eef = comp.value + "_eef"
                    eef_jn = self._joint_names[comp_eef]
                    js = self.interface.get_listened(self._action_topics[comp])
                    jq = self.interface.get_joint_values_by_names(js, arm_jn + eef_jn)
                    data[f"action/{comp.value}/joint_state"] = {
                        "t": t,
                        "data": {
                            "pos": jq[:-1],
                            "vel": [0.0] * len(arm_jn),
                            "eff": [0.0] * len(arm_jn),
                        },
                    }
                    data[f"action/{comp_eef}/joint_state"] = {
                        "t": t,
                        "data": {
                            "pos": [jq[-1]],
                            "vel": [0.0],
                            "eff": [0.0],
                        },
                    }
                elif comp in MMK2ComponentsGroup.HEAD_SPINE:
                    jq = list(
                        self.interface.get_listened(self._action_topics[comp]).data
                    )
                    data[f"action/{comp.value}/joint_state"] = {
                        "t": t,
                        "data": {
                            "pos": jq,
                            "vel": [0.0] * len(jq),
                            "eff": [0.0] * len(jq),
                        },
                    }
                else:
                    raise ValueError(
                        f"Component {comp} not supported for demonstration"
                    )
        return data

    def _set_js_bson(
        self, data: dict, comp: MMK2Components, t: float, js: JointState
    ) -> Dict[str,]:
        comp_data = {"t": t, "data": {}}
        for field in ["position", "velocity", "effort"]:
            value = self.interface.get_joint_values_by_names(
                js, self._joint_names[comp.value], field
            )
            comp_data["data"][field[:3]] = value
        data[f"{comp.value}/joint_state"] = comp_data

    def _capture_images(self) -> Tuple[Dict[str, bytes], Dict[str, Time]]:
        images = {}
        img_stamps: Dict[MMK2Components, Time] = {}
        comp_images = self.interface.get_image(self.config.cameras)
        for comp, image in comp_images.items():
            # TODO: now only support for color image
            images[comp.value] = image.data[ImageTypes.COLOR]
            img_stamps[comp.value] = image.stamp
        return images, img_stamps

    def capture_observation(self):
        """The returned observations do not have a batch dimension."""
        # Capture images from cameras
        obs_act_dict = self._get_low_dim()
        images, img_stamps = self._capture_images()
        for name in images:
            stamp = img_stamps[name]
            obs_act_dict[f"{name}/color_image"] = {
                "t": stamp.sec * 1e-3 + stamp.nanosec * 1e-6,
                "data": images[name],
            }
        return obs_act_dict

    def _check_joints(self, joint_names: List[str]):
        required_joints = []
        for component in MMK2ComponentsGroup.ARMS_EEFS + MMK2ComponentsGroup.HEAD_SPINE:
            required_joints.extend(self._joint_names[component.value])
        missing = [j for j in required_joints if j not in joint_names]
        if missing:
            raise KeyError(f"Missing required joints: {missing}")

    def shutdown(self) -> bool:
        self.interface.close()
        return True


if __name__ == "__main__":
    mmk = AIRBOTMMK(
        AIRBOTMMKConfig(
            ip="172.25.11.188",
            components=MMK2ComponentsGroup.ARMS_EEFS + MMK2ComponentsGroup.HEAD_SPINE,
            cameras={
                MMK2Components.LEFT_CAMERA: {
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                },
                MMK2Components.RIGHT_CAMERA: {
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                },
                MMK2Components.HEAD_CAMERA: {
                    "rgb_camera.color_profile": "640,480,30",
                    "enable_depth": "false",
                },
            },
        )
    )
    assert mmk.configure()
