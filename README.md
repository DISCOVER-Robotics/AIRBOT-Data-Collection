# Installation

```bash
sudo apt install ./airbot-configure_5.1.2-1_all.deb -y
conda create -n airbot_data python=3.10 && conda activate airbot_data
pip install airbot_py-5.1.2-py3-none-any.whl -i https://mirrors.huaweicloud.com/repository/pypi/simple
bash install.sh
```

# Setup

```bash
python3 tools/setup.py
```

# Usage

```bash
python3 main.py --path defaults/config_setup.yaml
```
