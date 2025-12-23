# 常见配置调整说明

本文档以`airbot_ie`默认配置为例介绍了一些常见的配置调整说明，帮助用户更好地理解和使用数据采集系统。

## 任务信息

不同任务一般需要手动对配置文件中的参数进行修改，特别是`airbot_ie/configs/basis.yaml`中`task_info`中的任务名称等，这些信息将可能在后续用作区分不同类型数据，以及可能用作模型的`prompt`。

## 动作回调

支持配置在数据采集状态变化时自动执行指定动作，例如在每次开始采集前自动将机械臂臂重置到初始位姿等，可参考`airbot_ie/configs/demonstrators/test.yaml`中的`send_actions`字段进行配置（注意不要直接在`test.yaml`中修改）。

## 相机功能

### 深度数据
默认情况下深度相机不采集深度数据（体积较大），如果需要采集，可参考`airbot_ie/configs/demonstrators/realsense.yaml`中的参数，在`setup.yaml`的相机配置中添加`enable_depth`和`align_depth`字段并设置为`true`。点云数据不支持也不建议直接采集，请自行通过后处理从深度图像中生成。

### 非阻塞模式
普通USB相机（V4L2 Camera）目前支持非阻塞取图模式，可在相机配置中增加`blocking`字段并设置为`false`，这样可以避免因相机帧率不足影响整体数据采集频率，不过会导致相机数据中出现重复帧（目前暂不支持异步不等长采集）。

### RealSense可选配置
RealSense相机的分辨率和帧率等配置受USB口是否为USB3.0影响，可通过安装使用`rs-enumerate-devices`命令查看相机支持的分辨率和帧率，并在配置文件中进行相应修改。


### 相机信息覆盖

可在对应相机的配置下，增加如下参数以覆盖默认相机信息：
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

深度模组的配置类似，只是字段名称替换为`depth_module`即可。

## 自动遥操

默认情况下，需要根据机器人实际使用方式手动启动遥操作控制，对于基于`grouped demonstrator`构建的示教器，可开启自动遥操作控制。需调整`demonstrator.auto_control`下的字段：
  - `groups`字段设置为`null`（注意不是列表`[null]`）；
  - 增加`modes`字段并设置为列表`[process]`（`process`表示以子进程的方式启动控制程序）；
  - 增加`rates`字段并设置为列表`[100]`（`100`是默认的遥操控制频率，理论上数据采集的更新频率不应超过该值）。

## 采样器

- ROS-MCAP采样器：将`airbot_ie/configs/basis.yaml`中sampler类型调整为：`airbot_data_collection.common.samplers.mcap_sampler_ros.McapDataSamplerROS`。这样保存的MCAP的消息格式与ROS录制的Bag文件兼容。
- 独立保存视频文件：在airbot_ie/configs/basis.yaml中为sampler增加配置：`video_save_to: folder`，这样视频数据将不保存到mcap文件中，而是独立保存为.mp4文件到文件夹中。

## 数据合并

默认情况下各个组件的数据拥有自己独立的键名，例如`arm`和`eef`分别拥有自己的`joint_state`数据。ROS通常会将这些数据合并到同一个`joint_sates`话题下发布，因此在采集时需要将这些数据合并。这可以通过在根配置下增加`key_merge`字段，可配置自定义的函数（输入为原始字典，输出为合并后的字典）或分别指定合并方式函数`method`和合并指示函数`pred`，经由内置合并器根据该配置进行合并（适用于大多数情况）。

## 名称重映射

默认的`grouped demonstrator`示教器通过`group name`、`component name`和`data key`三层名称通过`/`连接形成最终的数据名称，其中`data key`一般遵循：`<sub component name>/<data type>/<field name[optional]>`结构。例如`/left/leader/arm/joint_state`。但ROS通常期望数据名称为：`/robot/arm_left_leader/joint_states`。为此，可通过在`sampler.instance`字段下增加`key_remap`配置，指定一个映射函数，具体可参考：`airbot_ie/configs/key_remap/example.yaml`。

## 数据种类

机器人通常可以获取多种数据，例如各种传感器实时数据，以及机器人关节名称信息等。通常，非实时的数据默认通过`info`接口获取而不被加入观测数据中，但ROS有时会要求将这些数据实时发布以保持完整性，例如`JointState`消息中包含固定的关节名称信息。为此，可通过在机器人配置文件中的观测接口中增加对应数据类型的接口，具体可参考：`airbot_ie/configs/robots/airbot_play_with_name.yaml`。
