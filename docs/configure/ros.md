# ROS配置修改说明

示例配置文件路径: `airbot_ie/configs/demonstrators/ros.yaml`。

## 采样器配置

- 使用ROS2格式的mcap数据保存：将airbot_ie/configs/basis.yaml中sampler包调整为：`airbot_data_collection.common.samplers.mcap_sampler_ros.McapDataSamplerROS`
- 视频不保存到mcap文件中，而是独立保存.mp4文件到文件夹中：在airbot_ie/configs/basis.yaml中为sampler增加配置：`video_save_to: folder`

## 设备信息配置

- 相机信息覆盖：可在示教配置文件（例如airbot_ie/configs/demonstrators/setup.yaml）中对应相机的配置下，增加如下参数以覆盖默认相机信息：
```yaml
rgb_camera:
    intrinsics:
        distortion_model: plumb_bob
        d: [0.0, 0.0, 0.0, 0.0, 0.0]
        k: [615.0, 0.0, 320.0, 0.0, 615.0, 240.0, 0.0, 0.0, 1.0]
        binning_x: 0
        binning_y: 0
    calibration:
        r: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        p: [615.0, 0.0, 320.0, 0.0, 0.0, 615.0, 240.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        roi:
        x_offset: 0
        y_offset: 0
        height: 0
        width: 0
        do_rectify: false
```

## 数据合并

默认情况下各个组件的数据拥有自己独立的键名，例如`arm`和`eef`分别拥有自己的`joint_state`数据。ROS通常会将这些数据合并到同一个`joint_sates`话题下发布，因此在采集时需要将这些数据合并。这可以通过在根配置下增加`key_merge`字段，可配置自定义的函数（输入为原始字典，输出为合并后的字典）或分别指定合并方式函数`method`和合并指示函数`pred`，经由内置合并器根据该配置进行合并（适用于大多数情况）。

## 名称重映射

默认的`grouped demonstrator`示教器通过`group name`、`component name`和`data key`三层名称通过`/`连接形成最终的数据名称，其中`data key`一般遵循：`<sub component name>/<data type>/<field name[optional]>`结构。例如`/left/leader/arm/joint_state`。但ROS通常期望数据名称为：`/robot/arm_left_leader/joint_states`。为此，可通过在`sampler.instance`字段下增加`key_remap`配置，指定一个映射函数，具体可参考：`airbot_ie/configs/key_remap/example.yaml`。

## 数据种类

机器人通常可以获取多种数据，例如各种传感器实时数据，以及机器人关节名称信息等。通常，非实时的数据默认通过`info`接口获取而不被加入观测数据中，但ROS有时会要求将这些数据实时发布以保持完整性，例如`JointState`消息中包含固定的关节名称信息。为此，可通过在机器人配置文件中的观测接口中增加对应数据类型的接口，具体可参考：`airbot_ie/configs/robots/airbot_play_with_name.yaml`。
