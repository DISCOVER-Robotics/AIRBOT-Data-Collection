TOK4 & TOK2:
Metadata:
* timestamps:
  * `save_time`
  * `start_time`
* version:
  * `driver_version`
  * `recorder_version`
  * `file_version`
* task_info:
  * `task_id`
  * `task_name`
  * `station_id`
  * `operator`
  * `object`
  * `skill`
* hardware_info: # Null for now
  * `/robot_type`
  * `/host_type`
  * `/arm/lead_left/joint_names`
  * `/arm/lead_left/sku`
  * `/arm/lead_left/sn`
  * `/arm/lead_left/firmware`
  * `/arm/lead_right/joint_names`
  * `/arm/lead_right/sku`
  * `/arm/lead_right/sn`
  * `/arm/lead_right/firmware`
  * `/arm/follow_left/joint_names`
  * `/arm/follow_left/sku`
  * `/arm/follow_left/sn`
  * `/arm/follow_left/firmware`
  * `/arm/follow_right/joint_names`
  * `/arm/follow_right/sku`
  * `/arm/follow_right/sn`
  * `/arm/follow_right/firmware`
  * `/eef/lead_left/sku`
  * `/eef/lead_left/sn`
  * `/eef/lead_left/firmware`
  * `/eef/lead_right/sku`
  * `/eef/lead_right/sn`
  * `/eef/lead_right/firmware`
  * `/eef/follow_left/sku`
  * `/eef/follow_left/sn`
  * `/eef/follow_left/firmware`
  * `/eef/follow_right/sku`
  * `/eef/follow_right/sn`
  * `/eef/follow_right/firmware`
  * `/cam/follow_left/sku`
  * `/cam/follow_left/sn`
  * `/cam/follow_left/depth/frame_size`: [1920, 1080]
  * `/cam/follow_left/rgb/frame_size`: [1920, 1080]
  * `/cam/follow_left/depth/save_type`: "frame" / "h264"
  * `/cam/follow_left/rgb/save_type`: "frame" / "h264"
  * `/cam/follow_right/sku`
  * `/cam/follow_right/sn`
  * `/cam/follow_right/depth/frame_size`: [1920, 1080]
  * `/cam/follow_right/rgb/frame_size`: [1920, 1080]
  * `/cam/follow_right/depth/save_type`: "frame" / "h264"
  * `/cam/follow_right/rgb/save_type`: "frame" / "h264"
  * `/cam/env_top/sku`
  * `/cam/env_top/sn`
  * `/cam/env_top/depth/frame_size`: [1920, 1080]
  * `/cam/env_top/rgb/frame_size`: [1920, 1080]
  * `/cam/env_top/depth/save_type`: "frame" / "h264"
  * `/cam/env_top/rgb/save_type`: "frame" / "h264"
  * `/cam/env_front/sku`
  * `/cam/env_front/sn`
  * `/cam/env_front/depth/frame_size`: [1920, 1080]
  * `/cam/env_front/rgb/frame_size`: [1920, 1080]
  * `/cam/env_front/depth/save_type`: "frame" / "h264"
  * `/cam/env_front/rgb/save_type`: "frame" / "h264"
Messages ([Schema] /channel_name):
* [FloatArray] /arm/lead_left/joint_pos
* [FloatArray] /arm/lead_left/joint_vel
* [FloatArray] /arm/lead_left/joint_eff
* [FloatArray] /arm/lead_right/joint_pos
* [FloatArray] /arm/lead_right/joint_vel
* [FloatArray] /arm/lead_right/joint_eff
* [FloatArray] /arm/follow_left/joint_pos
* [FloatArray] /arm/follow_left/joint_vel
* [FloatArray] /arm/follow_left/joint_eff
* [FloatArray] /arm/follow_right/joint_pos
* [FloatArray] /arm/follow_right/joint_vel
* [FloatArray] /arm/follow_right/joint_eff
* [TF] /arm/lead_left/tf
* [TF] /arm/lead_right/tf
* [TF] /arm/follow_left/tf
* [TF] /arm/follow_right/tf
* [Pose] /arm/lead_left/end_pose
* [Pose] /arm/lead_right/end_pose
* [Pose] /arm/follow_left/end_pose
* [Pose] /arm/follow_right/end_pose
* [FloatArray] /eef/lead_left/joint_pos
* [FloatArray] /eef/lead_left/joint_vel
* [FloatArray] /eef/lead_left/joint_eff
* [FloatArray] /eef/lead_right/joint_pos
* [FloatArray] /eef/lead_right/joint_vel
* [FloatArray] /eef/lead_right/joint_eff
* [FloatArray] /eef/follow_left/joint_pos
* [FloatArray] /eef/follow_left/joint_vel
* [FloatArray] /eef/follow_left/joint_eff
* [FloatArray] /eef/follow_right/joint_pos
* [FloatArray] /eef/follow_right/joint_vel
* [FloatArray] /eef/follow_right/joint_eff
* [CompressedImage] /cam/follow_left/rgb/compressed
* [CompressedImage] /cam/follow_left/depth/compressed
* [CompressedImage] /cam/follow_right/rgb/compressed
* [CompressedImage] /cam/follow_right/depth/compressed
* [CompressedImage] /cam/env_top/rgb/compressed
* [CompressedImage] /cam/env_top/depth/compressed
* [CompressedImage] /cam/env_front/rgb/compressed
* [CompressedImage] /cam/env_front/depth/compressed
Attachments: ([media_type] name) (Serialized by libh264 or hobot_h264)
* [video/mp4;codecs="avc1.4d002a"] `/cam/follow_left/video`
* [video/mp4;codecs="avc1.4d002a"] `/cam/follow_right/video`
* [video/mp4;codecs="avc1.4d002a"] `/cam/env_top/video`
* [video/mp4;codecs="avc1.4d002a"] `/cam/env_front/video`
* [video/mp4;codecs="avc1.4d002a"] `/scene`
* [application/urdf] `/arm/lead_left/description`
* [application/urdf] `/arm/lead_right/description`
* [application/urdf] `/arm/follow_left/description`
* [application/urdf] `/arm/follow_right/description`
