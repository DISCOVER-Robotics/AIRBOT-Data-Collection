# Installation

```bash
sudo apt install ./airbot-configure_5.1.2-1_all.deb
conda create -n airbot_data python=3.10 && conda activate airbot_data
pip install airbot_py-5.1.2-py3-none-any.whl -i https://mirrors.huaweicloud.com/repository/pypi/simple
pip install airbot_data-1.2.1-py3-none-any.whl -i https://mirrors.huaweicloud.com/repository/pypi/simple
pip install av -i https://mirrors.huaweicloud.com/repository/pypi/simple
pip uninstall opencv-python-headless
git clone https://git.qiuzhi.tech/OpenGHz/airbot-data-collection.git
cd airbot-data-collection
pip install -e ."[all]" -i https://mirrors.huaweicloud.com/repository/pypi/simple
```

# Usage

Enter the package directory:
```bash
cd airbot_data_collection
```

Start AIRBOT FSMs first:

One leader arm and one follower:

```bash
airbot_fsm -i can0 -p 50050
airbot_fsm -i can1 -p 50051
```

Two leader arms and two follower arms

```bash
airbot_fsm -i can0 -p 50050
airbot_fsm -i can1 -p 50051
airbot_fsm -i can2 -p 50052
airbot_fsm -i can3 -p 50053
```

Then run the data collection program:

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

Data key structure: /{group name}/{component name}/{data type name}
