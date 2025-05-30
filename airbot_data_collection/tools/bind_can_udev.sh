#!/bin/bash

CAN_RULE_PATH=/etc/udev/rules.d/91-usb-can-airbot.rules
SLCAN_RULE_PATH=/etc/udev/rules.d/91-usb-slcan-airbot.rules

# 初始化参数变量
RAW_DEVICES=()
TARGET_NAMES=()

# 解析命令行参数
while [[ "$#" -gt 0 ]]; do
    case $1 in
        rm)
            if [ -z "$2" ] || [ "$2" = "slcan" ]; then
                rm -f "$SLCAN_RULE_PATH"
                echo "Removed $SLCAN_RULE_PATH"
            fi
            if [ -z "$2" ] || [ "$2" = "can" ]; then
                rm -f "$CAN_RULE_PATH"
                echo "Removed $CAN_RULE_PATH"
            fi
            exit 0
            ;;
        --raw)
            shift
            while [[ "$#" -gt 0 && ! "$1" =~ ^-- ]]; do
                RAW_DEVICES+=("$1")
                shift
            done
            continue
            ;;
        --target)
            shift
            while [[ "$#" -gt 0 && ! "$1" =~ ^-- ]]; do
                TARGET_NAMES+=("$1")
                shift
            done
            continue
            ;;
        *)
            BIND_NAME="$1"
            shift
            ;;
    esac
done

# 检查原始设备和目标名称数量是否一致
if [ ${#RAW_DEVICES[@]} -gt 0 ] && [ ${#TARGET_NAMES[@]} -gt 0 ]; then
    if [ ${#RAW_DEVICES[@]} -ne ${#TARGET_NAMES[@]} ]; then
        echo "Error: Number of raw devices (${#RAW_DEVICES[@]}) does not match number of target names (${#TARGET_NAMES[@]})"
        exit 1
    fi
fi

# Check for root permissions
if [ $EUID -ne 0 ]; then
    echo "This script must be run as root. Use sudo to run the script."
    exit 1
fi

# Detect connected USB2CAN devices by idVendor and idProduct
echo "Detecting connected USB2CAN devices..."
DEVICES=($(lsusb | awk '/ID (0483:0000|1d50:606f)/ {print $2 "/" $4}' | sed 's/://'))
NUM_DEVICES=${#DEVICES[@]}

if [ $NUM_DEVICES -eq 0 ]; then
    echo "No USB2CAN devices detected. Please connect a device and try again."
    exit 1
fi

# Display detected devices and extract serial numbers
echo "Detected USB2CAN devices:"
for ((i = 0; i < NUM_DEVICES; i++)); do
    DEVICE_PATH="/dev/bus/usb/${DEVICES[i]}"
    SERIAL=$(udevadm info --query=property --path=$(udevadm info --query=path --name=$DEVICE_PATH) | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)

    if [ -z "$SERIAL" ]; then
        SERIAL="Unknown"
    fi

    echo "$((i + 1)). ${DEVICES[i]}"
    echo "Serial number: $SERIAL"
done

# Loop to gather CAN interface names and automatically use serial numbers
for ((i = 0; i < NUM_DEVICES; i++)); do
    DEVICE_PATH="/dev/bus/usb/${DEVICES[i]}"
    SERIAL=$(udevadm info --query=property --path=$(udevadm info --query=path --name=$DEVICE_PATH) | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)

    if [ -z "$SERIAL" ]; then
        echo "Error: Unable to detect serial number for device ${DEVICES[i]}"
        continue
    fi

    # 决定使用哪个CAN名称
    if [ ${#TARGET_NAMES[@]} -gt 0 ] && [ $i -lt ${#TARGET_NAMES[@]} ]; then
        # 使用--target中指定的名称
        CAN_NAME=${TARGET_NAMES[$i]}
    elif [ -n "$BIND_NAME" ]; then
        # 如果提供了单个BIND_NAME，则使用它
        CAN_NAME=${BIND_NAME}
    else
        # 如果没有指定--target和BIND_NAME，则提示用户输入
        read -p "Enter desired CAN interface name for device with serial number $SERIAL (e.g., can_left) or press Enter to skip this device: " CAN_NAME
    fi

    if [ -z "$CAN_NAME" ]; then
        echo "Please enter a non-empty name"
        continue
    fi

    if [ ${#CAN_NAME} -gt 15 ]; then
        echo "The name is too long! Please enter a name with 15 characters or less"
        continue
    fi

    VENDOR_ID=$(udevadm info --query=property --path=$(udevadm info --query=path --name=$DEVICE_PATH) | grep 'ID_VENDOR_ID=' | cut -d'=' -f2)
    PRODUCT_ID=$(udevadm info --query=property --path=$(udevadm info --query=path --name=$DEVICE_PATH) | grep 'ID_MODEL_ID=' | cut -d'=' -f2)
    if [[ "$VENDOR_ID" == "0483" && "$PRODUCT_ID" == "0000" ]]; then

        # generate udev rule
        cat >>"${SLCAN_RULE_PATH}" <<EOL
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="0000", ATTRS{serial}=="$SERIAL", SYMLINK+="$CAN_NAME", GROUP="dialout", MODE="0777", TAG+="systemd", ENV{SYSTEMD_WANTS}="slcan_$CAN_NAME@.service"
EOL
        chmod +x "${SLCAN_RULE_PATH}"

        # generate service file
        cat >/etc/systemd/system/slcan_$CAN_NAME@.service <<EOL
[Unit]
Description=SocketCAN device $CAN_NAME
After=dev-$CAN_NAME.device
BindsTo=dev-$CAN_NAME.device

[Service]
ExecStart=/usr/local/bin/slcan_add_$CAN_NAME.sh
Type=forking
EOL
        chmod +x /etc/systemd/system/slcan_$CAN_NAME@.service

        # generate script file
        cat >/usr/local/bin/slcan_add_$CAN_NAME.sh <<EOL
#!/bin/bash
/usr/bin/slcand -o -c -f -s8 -S 3000000 /dev/$CAN_NAME $CAN_NAME
sleep 1
/usr/sbin/ip link set up $CAN_NAME
/usr/sbin/ip link set $CAN_NAME txqueuelen 1000
EOL

        chmod +x /usr/local/bin/slcan_add_$CAN_NAME.sh
        echo "udev for $CAN_NAME created in $SLCAN_RULE_PATH"
    else
        # generate udev rule
        cat >>${CAN_RULE_PATH} <<EOL
ACTION=="add", SUBSYSTEM=="net", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="606f", ATTRS{serial}=="$SERIAL", NAME="$CAN_NAME", RUN+="/sbin/ip link set $CAN_NAME up type can bitrate 1000000", RUN+="/sbin/ip link set $CAN_NAME txqueuelen 1000"
EOL
        chmod +x ${CAN_RULE_PATH}
        echo "udev for $CAN_NAME created in $CAN_RULE_PATH"
    fi
done

# Reload udev rules
udevadm control --reload-rules
udevadm trigger
echo "Udev rules reloaded successfully. Reconnect your USB2CAN devices."
