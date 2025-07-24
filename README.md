# Installation

```bash
sudo apt install ./airbot-configure_5.1.2-1_all.deb -y
conda create -n airbot_data python=3.10 && conda activate airbot_data
pip install airbot_py-5.1.2-py3-none-any.whl -i https://mirrors.huaweicloud.com/repository/pypi/simple
bash install.sh
```

<!-- ```bash
CUDA_ROOT=/usr/local/cuda
CUDA_TARG=$CUDA_ROOT/targets/x86_64-linux/
export CPATH=$CUDA_TARG/include:$CPATH
# export LD_LIBRARY_PATH=$CUDA_TARG/lib64:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=$CUDA_TARG/lib:$LD_LIBRARY_PATH
export PATH=$CUDA_ROOT/bin:$PATH
pip install ./PyNvVideoCodec_2.0.0.zip -i https://mirrors.aliyun.com/pypi/simple
pip install pycuda -i https://mirrors.aliyun.com/pypi/simple
pip install torch -i https://mirrors.aliyun.com/pypi/simple
``` -->

# Setup

```bash
python3 scripts/setup.py
```

# Usage

```bash
python3 main.py --path defaults/config_setup.yaml
```

# Development

```bash
pip install pre-commit
pre-commit run --all-files
pre-commit install
```
