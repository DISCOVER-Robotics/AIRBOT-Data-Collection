#!/bin/bash

BIND_NAME=$1

CAN_RULE_PATH=/etc/udev/rules.d/91-usb-can-airbot.rules
SLCAN_RULE_PATH=/etc/udev/rules.d/91-usb-slcan-airbot.rules

# 添加映射模式处理
if [ "$BIND_NAME" = "--raw" ]; then
    # 检查是否包含 --new
    NEW_IDX=0
    for idx in $(seq 1 $#); do
        arg="${!idx}"
        if [ "$arg" = "--new" ]; then
            NEW_IDX=$idx
            break
        fi
    done
    if [ "$NEW_IDX" -eq 0 ] || [ "$NEW_IDX" -le 2 ] || [ "$NEW_IDX" -ge "$#" ]; then
        echo "Usage: $0 --raw <current_can1> <current_can2> --new <new_can1> <new_can2>"
        echo "Example: $0 --raw can0 can1 --new can_left_lead can_left"
        exit 1
    fi

    # 解析当前CAN名
    CURRENT_CANS=()
    for idx in $(seq 2 $((NEW_IDX-1))); do
        CURRENT_CANS+=("${!idx}")
    done

    # 解析目标CAN名
    TARGET_CANS=()
    for idx in $(seq $((NEW_IDX+1)) $#); do
        TARGET_CANS+=("${!idx}")
    done
    # 检查当前CAN和目标CAN数量是否匹配
    if [ "${#CURRENT_CANS[@]}" -ne "${#TARGET_CANS[@]}" ]; then
        echo "Error: Number of current CAN devices does not match number of target names"
        exit 1
    fi

    # 创建映射
    for ((i=0; i<${#CURRENT_CANS[@]}; i++)); do
        CAN_MAPPINGS[${CURRENT_CANS[i]}]=${TARGET_CANS[i]}
    done

    # 检查每个当前CAN设备是否存在
    for CAN in "${CURRENT_CANS[@]}"; do
        if ! ip link show "$CAN" &>/dev/null; then
            echo "Error: CAN device $CAN does not exist"
            exit 1
        fi
    done

    echo "Detecting device properties for CAN devices..."

    # 处理每个CAN映射
    for CURR_CAN in "${!CAN_MAPPINGS[@]}"; do
        TARGET_NAME="${CAN_MAPPINGS[$CURR_CAN]}"
        echo "Processing: $CURR_CAN -> $TARGET_NAME"

        # 找到设备的syspath
        SYSPATH=$(readlink -f /sys/class/net/$CURR_CAN/device)
        if [ -z "$SYSPATH" ]; then
            echo "Error: Cannot find device path for $CURR_CAN"
            continue
        fi

        # 从syspath获取USB设备信息
        USB_PATH=$(echo "$SYSPATH" | grep -o '/[0-9]-[0-9]\+\(.[0-9]\+\)*')
        if [ -z "$USB_PATH" ]; then
            echo "Error: Cannot determine USB path for $CURR_CAN"
            continue
        fi

        # 获取设备属性
        VENDOR_ID=$(cat "/sys$USB_PATH/idVendor" 2>/dev/null)
        PRODUCT_ID=$(cat "/sys$USB_PATH/idProduct" 2>/dev/null)
        SERIAL=$(cat "/sys$USB_PATH/serial" 2>/dev/null)

        if [ -z "$VENDOR_ID" ] || [ -z "$PRODUCT_ID" ] || [ -z "$SERIAL" ]; then
            echo "Error: Cannot determine device properties for $CURR_CAN"
            continue
        fi

        echo "Found device: VID=$VENDOR_ID, PID=$PRODUCT_ID, Serial=$SERIAL"

        # 根据设备类型创建udev规则
        if [[ "$VENDOR_ID" == "0483" && "$PRODUCT_ID" == "0000" ]]; then
            # SLCAN设备
            cat >>"${SLCAN_RULE_PATH}" <<EOL
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="$VENDOR_ID", ATTRS{idProduct}=="$PRODUCT_ID", ATTRS{serial}=="$SERIAL", SYMLINK+="$TARGET_NAME", GROUP="dialout", MODE="0777", TAG+="systemd", ENV{SYSTEMD_WANTS}="slcan_$TARGET_NAME@.service"
EOL
            chmod +x "${SLCAN_RULE_PATH}"

            # 生成服务文件
            cat >/etc/systemd/system/slcan_$TARGET_NAME@.service <<EOL
[Unit]
Description=SocketCAN device $TARGET_NAME
After=dev-$TARGET_NAME.device
BindsTo=dev-$TARGET_NAME.device

[Service]
ExecStart=/usr/local/bin/slcan_add_$TARGET_NAME.sh
Type=forking
EOL
            chmod +x /etc/systemd/system/slcan_$TARGET_NAME@.service

            # 生成脚本文件
            cat >/usr/local/bin/slcan_add_$TARGET_NAME.sh <<EOL
#!/bin/bash
/usr/bin/slcand -o -c -f -s8 -S 3000000 /dev/$TARGET_NAME $TARGET_NAME
sleep 1
/usr/sbin/ip link set up $TARGET_NAME
/usr/sbin/ip link set $TARGET_NAME txqueuelen 1000
EOL
            chmod +x /usr/local/bin/slcan_add_$TARGET_NAME.sh
            echo "udev rule for $TARGET_NAME created in $SLCAN_RULE_PATH"
        else
            # 常规CAN设备
            cat >>${CAN_RULE_PATH} <<EOL
ACTION=="add", SUBSYSTEM=="net", ATTRS{idVendor}=="$VENDOR_ID", ATTRS{idProduct}=="$PRODUCT_ID", ATTRS{serial}=="$SERIAL", NAME="$TARGET_NAME", RUN+="/sbin/ip link set $TARGET_NAME up type can bitrate 1000000", RUN+="/sbin/ip link set $TARGET_NAME txqueuelen 1000"
EOL
            chmod +x ${CAN_RULE_PATH}
            echo "udev rule for $TARGET_NAME created in $CAN_RULE_PATH"
        fi
    done

    # 重新加载udev规则
    udevadm control --reload-rules
    udevadm trigger
    echo "Udev rules reloaded successfully. Reconnect your USB2CAN devices."
    exit 0
fi

if [ "$BIND_NAME" = "rm" ]; then
        if [ -z "$2" ] || [ "$2" = "slcan" ]; then
                rm -f "$SLCAN_RULE_PATH"
                echo "Removed $SLCAN_RULE_PATH"
        fi
        if [ -z "$2" ] || [ "$2" = "can" ]; then
                rm -f "$CAN_RULE_PATH"
                echo "Removed $CAN_RULE_PATH"
        fi
        exit 0
fi
