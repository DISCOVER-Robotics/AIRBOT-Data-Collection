# Installation

```bash
sudo apt install ./airbot-configure_5.1.6_all.deb -y
conda create -n airbot_data python=3.10 && conda activate airbot_data
pip install airbot_py-5.1.6-py3-none-any.whl -i https://mirrors.huaweicloud.com/repository/pypi/simple
bash install.sh
# for some airbot scripts
export PYTHONPATH="$(pwd):$PYTHONPATH"
```

# Development

```bash
pip install pre-commit
pre-commit run --all-files
pre-commit install
```
