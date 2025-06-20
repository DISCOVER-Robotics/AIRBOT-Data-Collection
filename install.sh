#!/bin/bash

# Install dependencies for Airbot Data Collection

set -e

arg=$1

sudo apt-get install -y libturbojpeg gcc python3-dev v4l-utils
pip install -e ."[all]" -i https://pypi.mirrors.ustc.edu.cn/simple

if  [ "$arg" == "realsense" ]; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]; then
        pip install pyrealsense2
    else
        pip install pyrealsense2-beta
    fi
fi
