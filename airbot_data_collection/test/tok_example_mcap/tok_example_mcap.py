import flatbuffers
from time import time_ns
from mcap.writer import Writer
from mcap.well_known import SchemaEncoding, MessageEncoding
import json
from foxglove_schemas_flatbuffer import get_schema
import foxglove_schemas_flatbuffer.Vector3 as Vec3
import foxglove_schemas_flatbuffer.Quaternion as Quat
import foxglove_schemas_flatbuffer.Pose as PoseFB
import airbot_type.FloatArray as FloatArray
import time
from random import uniform
# Create the builder
builder = flatbuffers.Builder(0)
with open("tok_example.mcap", "wb") as f:
    # Create the writer
    writer = Writer(f)
    writer.start()

    # metadata
    writer.add_metadata(
        name="version",
        data={
            "driver_version": "5.1.3",
            "recorder_version": "1",
            "file_version": "1",
        }
    )
    writer.add_metadata(
        name="task_info",
        data={
            "task_id": "1",
            "task_name": "coding",
            "station_id": "WX01",
            "operator": "Lue",
            "object": "keyboard",
            "skill": "click",
        }
    )
    writer.add_metadata(
        name="hardware_info",
        data={
            "robot_type": "TOK2",
            "host_type": "X5_RDK",
            "arm/lead_left/joint_names":
                json.dumps(
                    ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "eef_joint"]
                ),
            "arm/lead_left/sku": "AIRBOT-Replay",
            "arm/lead_left/sn": "PB34123412340001",
            "arm/lead_left/firmware":
                json.dumps(
                    ["0300", "0304", "0304", "0304", "0304", "0304", "0304", "0304"]
                ),
            "arm/lead_right/joint_names":
                json.dumps(
                    ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "eef_joint"]
                ),
            "arm/lead_right/sku": "AIRBOT-Replay",
            "arm/lead_right/sn": "PB34123412340002",
            "arm/lead_right/firmware":
                json.dumps(
                    ["0300", "0304", "0304", "0304", "0304", "0304", "0304", "0304"]
                ),
            "arm/follow_left/joint_names":
                json.dumps(
                    ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "eef_joint"]
                ),
            "arm/follow_left/sku": "AIRBOT-Play",
            "arm/follow_left/sn": "PZ34123412340001",
            "arm/follow_left/firmware":
                json.dumps(
                    ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
                ),
            "arm/follow_right/joint_names":
                json.dumps(
                    ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "eef_joint"]
                ),
            "arm/follow_right/sku": "AIRBOT-Play",
            "arm/follow_right/sn": "PZ34123412340002",
            "arm/follow_right/firmware":
                json.dumps(
                    ["0513", "0419", "0419", "0419", "5015", "5015", "5015", "5015", "0502"]
                ),
            "eef/lead_left/sku": "AIRBOT-FE2",
            "eef/lead_left/sn": "BE34123412340001",
            "eef/lead_left/firmware": "0304",
            "eef/lead_right/sku": "AIRBOT-FE2",
            "eef/lead_right/sn": "BE34123412340002",
            "eef/lead_right/firmware": "0304",
            "eef/follow_left/sku": "AIRBOT-G2",
            "eef/follow_left/sn": "PC34123412340001",
            "eef/follow_left/firmware": "5015",
            "eef/follow_right/sku": "AIRBOT-G2",
            "eef/follow_right/sn": "PC34123412340002",
            "eef/follow_right/firmware": "5015",
            "cam/follow_left/sku": "RealSense-D435i",
            "cam/follow_left/sn": "1234567890",
            "cam/follow_left/depth/frame_size": "640x480",
            "cam/follow_left/rgb/frame_size": "640x480",
            "cam/follow_left/depth/save_type": "H264",
            "cam/follow_left/rgb/save_type": "H264",
            "cam/follow_right/sku": "RealSense-D435i",
            "cam/follow_right/sn": "0987654321",
            "cam/follow_right/depth/frame_size": "640x480",
            "cam/follow_right/rgb/frame_size": "640x480",
            "cam/follow_right/depth/save_type": "H264",
            "cam/follow_right/rgb/save_type": "H264",
            "cam/env_top/sku": "RealSense-D435i",
            "cam/env_top/sn": "1122334455",
            "cam/env_top/depth/frame_size": "640x480",
            "cam/env_top/rgb/frame_size": "640x480",
            "cam/env_top/depth/save_type": "H264",
            "cam/env_top/rgb/save_type": "H264",
            "cam/env_front/sku": "RealSense-D435i",
            "cam/env_front/sn": "5566778899",
            "cam/env_front/depth/frame_size": "640x480",
            "cam/env_front/rgb/frame_size": "640x480",
            "cam/env_front/depth/save_type": "H264",
            "cam/env_front/rgb/save_type": "H264",
        }
    )

    # schemas
    pose_schema_id = writer.register_schema(
        name="foxglove.Pose",
        encoding=SchemaEncoding.Flatbuffer,
        data=get_schema("Pose"),
    )
    float_array_schema_id = writer.register_schema(
        name="airbot_type.FloatArray",
        encoding=SchemaEncoding.Flatbuffer,
        data=open("float_array.bfbs", "rb").read(),
    )
    # channels
    pose_channels = {}
    for arm in ["lead_left", "lead_right", "follow_left", "follow_right"]:
        pose_channels[arm] = writer.register_channel(
            schema_id=pose_schema_id,
            topic=f"arm/{arm}/end_pose",
            message_encoding=MessageEncoding.Flatbuffer,
        )
    float_array_channels = {}
    for typ in ["arm", "eef"]:
        float_array_channels[typ] = {}
        for arm in ["lead_left", "lead_right", "follow_left", "follow_right"]:
            float_array_channels[typ][arm] = {}
            for data_type in ["joint_pos", "joint_vel", "joint_eff"]:
                float_array_channels[typ][arm][data_type] = writer.register_channel(
                    schema_id=float_array_schema_id,
                    topic=f"{typ}/{arm}/{data_type}",
                    message_encoding=MessageEncoding.Flatbuffer,
                )

    start_time = time.time()
    init_pose = {
        "lead_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        "lead_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        "follow_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        "follow_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    }
    init_pos = {
        "arm": {
            "lead_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "lead_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "follow_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "follow_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        },
        "eef": {
            "lead_left": [0.0],
            "lead_right": [0.0],
            "follow_left": [0.0],
            "follow_right": [0.0],
        },
    }
    init_vel = {
        "arm": {
            "lead_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "lead_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "follow_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "follow_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        },
        "eef": {
            "lead_left": [0.0],
            "lead_right": [0.0],
            "follow_left": [0.0],
            "follow_right": [0.0],
        },
    }
    init_eff = {
        "arm": {
            "lead_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "lead_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "follow_left": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "follow_right": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        },
        "eef": {
            "lead_left": [0.0],
            "lead_right": [0.0],
            "follow_left": [0.0],
            "follow_right": [0.0],
        },
    }
    last_poses = init_pose.copy()
    last_pos = init_pos.copy()
    last_vel = init_vel.copy()
    last_eff = init_eff.copy()
    while time.time() - start_time < 10:
        builder = flatbuffers.Builder(256)

        # use rand values for simulation poses
        poses = {
            "lead_left": [
                init_pose["lead_left"][0] + uniform(-0.1, 0.1),
                init_pose["lead_left"][1] + uniform(-0.1, 0.1),
                init_pose["lead_left"][2] + uniform(-0.1, 0.1),
                init_pose["lead_left"][3] + uniform(-0.1, 0.1),
                init_pose["lead_left"][4] + uniform(-0.1, 0.1),
                init_pose["lead_left"][5] + uniform(-0.1, 0.1),
                init_pose["lead_left"][6],
            ],
            "lead_right": [
                init_pose["lead_right"][0] + uniform(-0.1, 0.1),
                init_pose["lead_right"][1] + uniform(-0.1, 0.1),
                init_pose["lead_right"][2] + uniform(-0.1, 0.1),
                init_pose["lead_right"][3] + uniform(-0.1, 0.1),
                init_pose["lead_right"][4] + uniform(-0.1, 0.1),
                init_pose["lead_right"][5] + uniform(-0.1, 0.1),
                init_pose["lead_right"][6],
            ],
            "follow_left": last_poses["lead_left"][:],
            "follow_right": last_poses["lead_right"][:],
        }
        last_poses = poses.copy()

        joint_pos = {
            "arm": {
                "lead_left": [uniform(-1.0, 1.0) for _ in range(6)],
                "lead_right": [uniform(-1.0, 1.0) for _ in range(6)],
                "follow_left": last_pos["arm"]["lead_left"][:],
                "follow_right": last_pos["arm"]["lead_right"][:],
            },
            "eef": {
                "lead_left": [uniform(0, 1.0)],
                "lead_right": [uniform(0, 1.0)],
                "follow_left": last_pos["eef"]["lead_left"][:],
                "follow_right": last_pos["eef"]["lead_right"][:],
            },
        }
        last_pos = joint_pos.copy()

        joint_vel = {
            "arm": {
                "lead_left": [uniform(-0.1, 0.1) for _ in range(6)],
                "lead_right": [uniform(-0.1, 0.1) for _ in range(6)],
                "follow_left": last_vel["arm"]["lead_left"][:],
                "follow_right": last_vel["arm"]["lead_right"][:],
            },
            "eef": {
                "lead_left": [uniform(-0.1, 0.1)],
                "lead_right": [uniform(-0.1, 0.1)],
                "follow_left": last_vel["eef"]["lead_left"][:],
                "follow_right": last_vel["eef"]["lead_right"][:],
            },
        }
        last_vel = joint_vel.copy()

        joint_eff = {
            "arm": {
                "lead_left": [uniform(-1.0, 1.0) for _ in range(6)],
                "lead_right": [uniform(-1.0, 1.0) for _ in range(6)],
                "follow_left": last_eff["arm"]["lead_left"][:],
                "follow_right": last_eff["arm"]["lead_right"][:],
            },
            "eef": {
                "lead_left": [uniform(-1.0, 1.0)],
                "lead_right": [uniform(-1.0, 1.0)],
                "follow_left": last_eff["eef"]["lead_left"][:],
                "follow_right": last_eff["eef"]["lead_right"][:],
            },
        }
        last_eff = joint_eff.copy()

        for arm, pose in poses.items():
            # Create the pose message
            x, y, z, qx, qy, qz, qw = pose
            Vec3.Start(builder)
            Vec3.AddX(builder, x)
            Vec3.AddY(builder, y)
            Vec3.AddZ(builder, z)
            pos = Vec3.End(builder)
            Quat.Start(builder)
            Quat.AddX(builder, qx)
            Quat.AddY(builder, qy)
            Quat.AddZ(builder, qz)
            Quat.AddW(builder, qw)
            quat = Quat.End(builder)
            PoseFB.Start(builder)
            PoseFB.AddPosition(builder, pos)
            PoseFB.AddOrientation(builder, quat)
            pose_msg = PoseFB.End(builder)
            builder.Finish(pose_msg)
            pose_bytes = builder.Output()
            # Write the message to the channel
            writer.add_message(
                channel_id=pose_channels[arm],
                log_time=time.time_ns(),
                publish_time=time.time_ns(),
                data=bytes(pose_bytes)
            )

        for typ, arms in joint_pos.items():
            for arm, pos in arms.items():
                # Create the float array message
                FloatArray.StartValuesVector(builder, len(pos))
                for value in pos:
                    builder.PrependFloat32(value)
                values = builder.EndVector()
                FloatArray.Start(builder)
                FloatArray.AddValues(builder, values)
                float_array_msg = FloatArray.End(builder)
                builder.Finish(float_array_msg)
                float_array_bytes = builder.Output()
                # Write the message to the channel
                writer.add_message(
                    channel_id=float_array_channels[typ][arm]["joint_pos"],
                    log_time=time.time_ns(),
                    publish_time=time.time_ns(),
                    data=bytes(float_array_bytes)
                )
        for typ, arms in joint_vel.items():
            for arm, vel in arms.items():
                # Create the float array message
                FloatArray.StartValuesVector(builder, len(vel))
                for value in vel:
                    builder.PrependFloat32(value)
                values = builder.EndVector()
                FloatArray.Start(builder)
                FloatArray.AddValues(builder, values)
                float_array_msg = FloatArray.End(builder)
                builder.Finish(float_array_msg)
                float_array_bytes = builder.Output()
                # Write the message to the channel
                writer.add_message(
                    channel_id=float_array_channels[typ][arm]["joint_vel"],
                    log_time=time.time_ns(),
                    publish_time=time.time_ns(),
                    data=bytes(float_array_bytes)
                )
        for typ, arms in joint_eff.items():
            for arm, eff in arms.items():
                # Create the float array message
                FloatArray.StartValuesVector(builder, len(eff))
                for value in eff:
                    builder.PrependFloat32(value)
                values = builder.EndVector()
                FloatArray.Start(builder)
                FloatArray.AddValues(builder, values)
                float_array_msg = FloatArray.End(builder)
                builder.Finish(float_array_msg)
                float_array_bytes = builder.Output()
                # Write the message to the channel
                writer.add_message(
                    channel_id=float_array_channels[typ][arm]["joint_eff"],
                    log_time=time.time_ns(),
                    publish_time=time.time_ns(),
                    data=bytes(float_array_bytes)
                )
        time.sleep(0.004)
    # Finish writing the file
    writer.finish()
