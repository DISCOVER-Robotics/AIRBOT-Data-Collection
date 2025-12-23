# AIRBOT Play/PTK/TOK 数据采集自动配置

## 注意事项

- 对于`拖动示教`方式暂不支持自动配置，请手动绑定设备并修改配置文件。参考配置文件位于`airbot_ie/configs/demonstrators/airbot_play.yaml`
- 如果尚未绑定机械臂，请确保按正确顺序插入设备（见[设备连接](../setup/airbot_play.md#设备连接)），然后执行下述命令后会默认自动进行绑定，请根据终端提示拔掉设备并重新连接即可
- 同时使用多个USB相机时往往会因为相机连接顺序变化而导致设备号变化，造成数据记录的语义与实际不符，例如名为`env_camera`的环境相机实际上可能错误地对应了臂载相机。为了解决这个问题，自动配置程序使用了USB端口号代替设备号进行配置

## 配置过程

运行如下程序进行自动绑定：
```bash
python3 airbot_ie/scripts/setup.py --ic <bus_id> --ii <can_id> --rcd <ref_config_dir> --rcn <ref_config_name>
```

参数说明：

- `--ic`：指定要忽略的相机的USB端口号（注意不是相机设备号/设备路径，查看方式参见[相机信息](../../README.md#cam_info)），通常用于忽略笔记本电脑内置相机，如果有其他需要忽略的相机，可以继续添加总线号（用英文逗号隔开，下同）。如果不需要忽略相机，请去掉该参数。
- `--ii`：指定要忽略的CAN名称，通常用于忽略非机械臂的其他在用的CAN设备。如果不需要忽略，请去掉该参数。
- `--rcd`：参考配置文件夹路径，默认值为`airbot_ie/configs/demonstrators`。
- `--rcn`：参考配置文件名称，默认值为`airbot_play`（后缀可省略）。


启动后，该程序会要求输入密码，这是为了获取设备的序列号便于匹配不同设备。
而后会自动检测设备所连接的所有相机并通过图形窗口实时显示图像，图像上方标题的格式为：`名称-ID-USB端口信息或序列号`，如果未曾配置过
或者相机连接端口号发生变更，则名称为`None`，此时可按`c`键进行配置（如果按键没反应，请点击任意图像窗口后再次尝试，下同），此时终端会提示要对某个端口号的相机命名，通过数字按键选择对应名称
（规范化的可选名称在`airbot_ie/scripts/station_config.yaml`中配置，通常不需修改），如果只剩一个相机和一个可选名称未被配置则会自动完成。
配置完成后建议通过图像窗口检查名称是否符合实际，然后按`s`键保存配置并退出，配置文件将保存到`airbot_ie/configs/demonstrators/setup.yaml`中。
可以根据使用情况手动修改该配置文件，例如机械臂的端口号、数据保存目录等。

## 手动调整

- 自动生成参考：配置文件的生成基于`airbot_ie/configs/demonstrators/airbot_play.yaml`，主要是覆写了`demonstrator.instance`字段下的`components`参数以及增加了`post_capture`参数（默认值位于`airbot_ie/configs/demonstrators/post_capture`，主要用于将示教器的控制范围映射到执行器的范围内），因此为防止重新生成配置后覆盖，建议不要直接修改`setup.yaml`，而是修改上述默认配置文件。
- 任务差异化：不同任务一般需要手动对配置文件中的参数进行修改，特别是`airbot_ie/configs/basis.yaml`中`task_info`中的任务名称等，这些信息将可能在后续用作区分不同类型数据，以及可能用作模型的`prompt`。
- 动作回调：支持配置在数据采集状态变化时自动执行指定动作，例如在每次开始采集前自动将机械臂臂重置到初始位姿等，可参考`airbot_ie/configs/demonstrators/test.yaml`中的`send_actions`字段进行配置（注意不要直接在`test.yaml`中修改，这是无效的）。
- 深度数据：默认情况下深度相机不采集深度数据（体积较大），如果需要采集，可参考`airbot_ie/configs/demonstrators/realsense.yaml`中的参数，在`setup.yaml`的相机配置中添加`enable_depth`和`align_depth`字段并设置为`true`。点云数据不支持也不建议直接采集，请自行通过后处理从深度图像中生成。
- 自动遥操作：默认情况下，需要手动启动机械臂的遥操作控制，见[启动遥操作](../teleop/airbot_play.md)，若要开启自动遥操作控制需调整`demonstrator.auto_control`下的字段：
    - `groups`字段设置为`null`（注意不是列表`[null]`）；
    - 增加`modes`字段并设置为列表`[process]`（`process`表示以子进程的方式启动控制程序）；
    - 增加`rates`字段并设置为列表`[100]`（`100`是默认的遥操控制频率）。
- 非阻塞取图：普通USB相机（V4L2 Camera）目前支持非阻塞取图模式，可在相机配置中增加`blocking`字段并设置为`false`，这样可以避免因相机帧率不足影响整体数据采集频率，不过会导致相机数据中出现重复帧（目前暂不支持异步不等长采集）。
- RealSense相机的分辨率和帧率等配置受USB口是否为USB3.0影响，可通过安装使用`rs-enumerate-devices`命令查看相机支持的分辨率和帧率，并在配置文件中进行相应修改。
