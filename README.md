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
pip install -e . -i https://mirrors.huaweicloud.com/repository/pypi/simple
```

# Usage

Start AIRBOT FSM fisrt:

```bash
airbot_fsm -i can0 -p 50050
airbot_fsm -i can1 -p 50051
```

Then run the datacollection program:

```bash
python3 main.py --path defaults/config.yaml \
                --components.names arm_leader arm left_camera \
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