#!/bin/bash

# Install dependencies for AIRBOT Data Collection

set -e

arg=$1

sudo apt-get install -y pip python3-dev libturbojpeg gcc
pip install --upgrade pip wheel -i https://pypi.mirrors.ustc.edu.cn/simple
pip install --no-build-isolation -e ."[all,airbot]" -i https://pypi.mirrors.ustc.edu.cn/simple

if  [ "$arg" == "realsense" ]; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]; then
        pip install pyrealsense2 -i https://pypi.mirrors.ustc.edu.cn/simple
    else
        pip install pyrealsense2-beta -i https://pypi.mirrors.ustc.edu.cn/simple
    fi
fi

pip install "mcap-data-loader @ git+https://github.com/OpenGHz/MCAP-DataLoader.git@22ffa928a6dd40228b2f2bfb0baa09c13b708741" -U
