#!/bin/bash

# Install dependencies for Airbot Data Collection

set -e

sudo apt-get install -y libturbojpeg gcc python3-dev v4l-utils
pip install -e ."[all]" -i https://pypi.tuna.tsinghua.edu.cn/simple
