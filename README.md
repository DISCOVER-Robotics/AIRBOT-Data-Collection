# Installation

```bash
sudo apt install ./airbot-configure_5.1.2-1_all.deb -y
conda create -n airbot_data python=3.10 && conda activate airbot_data
pip install airbot_py-5.1.2-py3-none-any.whl -i https://mirrors.huaweicloud.com/repository/pypi/simple
bash install.sh
```

# Configuration

To avoid confusing the leader arm with the follower arm, it's necessary to bind CAN names to each device in sequence. Take the control of two arms as an example. Complete the following steps in order:

1. Unplug all robotic arms and other CAN devices to ensure that the ip l command shows no CAN devices.
2. Connect the left leader arm, run sudo bind_airbot_device can_left_lead, and then disconnect it.
3. Connect the left follower arm, run sudo bind_airbot_device can_left, and then disconnect it.
4. Connect the right leader arm, run sudo bind_airbot_device can_right_lead, and then disconnect it.
5. Connect the right follower arm, run sudo bind_airbot_device can_right, and then disconnect it.
6. Connect all the arms.


# Usage

Enter the package directory:
```bash
cd airbot_data_collection
```

Start AIRBOT FSMs first:

One leader arm and one follower:

```bash
airbot_fsm -i can_left_lead -p 50050
airbot_fsm -i can_left -p 50051
```

Two leader arms and two follower arms

```bash
airbot_fsm -i can_left_lead -p 50050
airbot_fsm -i can_left -p 50051
airbot_fsm -i can_right_lead -p 50052
airbot_fsm -i can_right -p 50053
```

Then run the data collection script:

One leader arm, one follower arm and one usb camera case:

```bash
python3 main.py --path defaults/config.yaml \
                --components.names arm_leader arm camera \
                --components.paths airbot_play airbot_play usb_cam \
                --components.params '{}' '{"port": 50051}' '{"camera_index": 0}' \
                --components.roles l f o \
                --components.groups left left left \
                --dataset.directory example_task \
                --auto-control.rate 100 \
                --update-rate 20 \
                --sample-limit.start-round 0 \
                --sample-limit.size 1000
```

Two leader arms, two follower arms and three usb cameras case:

```bash
python3 main.py --path defaults/config.yaml \
                --components.names left_arm_leader left_arm left_camera right_arm_leader right_arm right_camera head_camera \
                --components.paths airbot_play airbot_play usb_cam airbot_play airbot_play usb_cam usb_cam \
                --components.params '{}' '{"port": 50051}' '{"camera_index": 0}' '{"port": 50052}' '{"port": 50053}' '{"camera_index": 2}' '{"camera_index": 4}' \
                --components.roles l f o l f o o \
                --components.groups left left left right right right right \
                --dataset.directory example_task \
                --auto-control.rate 100 \
                --update-rate 20 \
                --sample-limit.start-round 0 \
                --sample-limit.size 1000
```

After that, you can use the keyboard to control the data collection process. Instructions for keyboard usage can be found in the terminal printout, or you can press the `i` key to reprint them. Note that keyboard responses are global, so if you need to use the keyboard for other tasks, please close the data collection program first.

Data key structure: /{group name}/{component name}/{data type name}
