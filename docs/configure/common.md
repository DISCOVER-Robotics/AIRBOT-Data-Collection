# 常见配置调整说明

本文档以`airbot_ie`默认配置为例介绍了一些常见的配置调整说明，帮助用户更好地理解和使用数据采集系统。

## 任务信息

不同任务一般需要手动对配置文件中的参数进行修改，特别是`airbot_ie/configs/basis.yaml`中`task_info`中的任务名称等，这些信息将可能在后续用作区分不同类型数据，以及可能用作模型的`prompt`。

## 动作回调

支持配置在数据采集状态变化时自动执行指定动作，例如在每次开始采集前自动将机械臂臂重置到初始位姿等，可参考`airbot_ie/configs/demonstrators/test.yaml`中的`send_actions`字段进行配置（注意不要直接在`test.yaml`中修改）。

## 相机功能

- 深度数据：默认情况下深度相机不采集深度数据（体积较大），如果需要采集，可参考`airbot_ie/configs/demonstrators/realsense.yaml`中的参数，在`setup.yaml`的相机配置中添加`enable_depth`和`align_depth`字段并设置为`true`。点云数据不支持也不建议直接采集，请自行通过后处理从深度图像中生成。
- 非阻塞取图：普通USB相机（V4L2 Camera）目前支持非阻塞取图模式，可在相机配置中增加`blocking`字段并设置为`false`，这样可以避免因相机帧率不足影响整体数据采集频率，不过会导致相机数据中出现重复帧（目前暂不支持异步不等长采集）。
- RealSense相机的分辨率和帧率等配置受USB口是否为USB3.0影响，可通过安装使用`rs-enumerate-devices`命令查看相机支持的分辨率和帧率，并在配置文件中进行相应修改。

## 自动遥操

默认情况下，需要根据机器人实际使用方式手动启动遥操作控制，对于基于`grouped demonstrator`构建的示教器，可开启自动遥操作控制。需调整`demonstrator.auto_control`下的字段：
  - `groups`字段设置为`null`（注意不是列表`[null]`）；
  - 增加`modes`字段并设置为列表`[process]`（`process`表示以子进程的方式启动控制程序）；
  - 增加`rates`字段并设置为列表`[100]`（`100`是默认的遥操控制频率，理论上数据采集的更新频率不应超过该值）。
