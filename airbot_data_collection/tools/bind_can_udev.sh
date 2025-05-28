#!/bin/bash

# usb2can_bind.sh
# 用法示例：
#   sudo ./usb2can_bind.sh --target can_lead can_follow --raw can0 can1
#   sudo ./usb2can_bind.sh rm [can|slcan]

CAN_RULE_PATH=/etc/udev/rules.d/91-usb-can-airbot.rules
SLCAN_RULE_PATH=/etc/udev/rules.d/91-usb-slcan-airbot.rules

print_usage() {
    echo "Usage:"
    echo "  $0 --target name1 name2 ... --raw dev1 dev2 ..."
    echo "  $0 rm [can|slcan]"
    exit 1
}

# --- 参数解析 ---
if [[ "$1" == "rm" ]]; then
    MODE="rm"
    TARGET_TYPE="$2"
else
    MODE="bind"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --target)
                shift
                while [[ $# -gt 0 && "$1" != "--raw" ]]; do
                    TARGETS+=("$1")
                    shift
                done
                ;;
            --raw)
                shift
                while [[ $# -gt 0 ]]; do
                    RAW_DEVS+=("$1")
                    shift
                done
                ;;
            *)
                echo "Unknown argument: $1"
                print_usage
                ;;
        esac
    done
    # 校验
    if [[ ${#TARGETS[@]} -lt 1 || ${#TARGETS[@]} -ne ${#RAW_DEVS[@]} ]]; then
        echo "--target 和 --raw 参数数量必须一致且不少于一个"
        print_usage
    fi
fi

# --- 清理模式 ---
if [[ "$MODE" == "rm" ]]; then
    if [[ -z "$TARGET_TYPE" || "$TARGET_TYPE" == "slcan" ]]; then
        rm -f "$SLCAN_RULE_PATH" && echo "Removed $SLCAN_RULE_PATH"
    fi
    if [[ -z "$TARGET_TYPE" || "$TARGET_TYPE" == "can" ]]; then
        rm -f "$CAN_RULE_PATH" && echo "Removed $CAN_RULE_PATH"
    fi
    exit 0
fi

# --- 绑定模式，检查权限 ---
if [[ $EUID -ne 0 ]]; then
    echo "请以 root 权限运行"
    exit 1
fi

DMESG_LOG=$(dmesg)
USB_LINES=$(echo "$DMESG_LOG" | grep -i "usb [0-9]-[0-9]: Product: DISCOVER Robotics USB to CAN adapter")
CAN_ATTACH_LINES=$(echo "$DMESG_LOG" | grep -iE "renamed from|link becomes ready")

for idx in "${!RAW_DEVS[@]}"; do
    DEV_NAME="${RAW_DEVS[$idx]}"
    CAN_NAME="${TARGETS[$idx]}"

    MATCH_LINE=$(echo "$CAN_ATTACH_LINES" | grep "$DEV_NAME")
    if [[ -z "$MATCH_LINE" ]]; then
        echo "未找到与 $DEV_NAME 对应的 dmesg 日志，跳过"
        continue
    fi

    MATCH_INDEX=$(echo "$DMESG_LOG" | grep -nF "$MATCH_LINE" | cut -d: -f1 | head -n1)
    if [[ -z "$MATCH_INDEX" ]]; then
        echo "无法定位 $DEV_NAME 的日志行号，跳过"
        continue
    fi

    USB_BLOCK=$(echo "$DMESG_LOG" | head -n "$MATCH_INDEX" | tac | grep -m1 -B5 "Product: DISCOVER Robotics USB to CAN adapter")
    USB_PORT_LINE=$(echo "$USB_BLOCK" | grep -m1 "usb [0-9]-[0-9]:")
    USB_RAW_ID=$(echo "$USB_PORT_LINE" | awk '{print $2}')
    USB_ID=$(echo "$USB_PORT_LINE" | grep -oP 'usb \K[0-9\-]+(?=:)')

    if [[ -z "$USB_ID" ]]; then
        echo "无法从行中解析 USB ID: $USB_PORT_LINE"
        continue
    fi

    SYSFS_PATH="/sys/bus/usb/devices/$USB_ID"
    if [[ ! -f "$SYSFS_PATH/idVendor" || ! -f "$SYSFS_PATH/idProduct" ]]; then
        echo "未能识别 USB ID ($USB_ID) 对应的 sysfs 路径，跳过"
        continue
    fi

    VENDOR_ID=$(cat "$SYSFS_PATH/idVendor" 2>/dev/null)
    PRODUCT_ID=$(cat "$SYSFS_PATH/idProduct" 2>/dev/null)
    SERIAL="${DEV_NAME}_serial"

    echo "设备 $DEV_NAME 与目标 $CAN_NAME 映射。USB: $USB_ID ($VENDOR_ID:$PRODUCT_ID)"

    if [[ "$VENDOR_ID" == "0483" && "$PRODUCT_ID" == "0000" ]]; then
        cat >>"$SLCAN_RULE_PATH" <<-EOL
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="$VENDOR_ID", ATTRS{idProduct}=="$PRODUCT_ID", SYMLINK+="$CAN_NAME", GROUP="dialout", MODE="0777", TAG+="systemd", ENV{SYSTEMD_WANTS}="slcan_$CAN_NAME@.service"
EOL

        cat >/etc/systemd/system/slcan_$CAN_NAME@.service <<-EOL
[Unit]
Description=SocketCAN device $CAN_NAME
After=dev-$CAN_NAME.device
BindsTo=dev-$CAN_NAME.device

[Service]
ExecStart=/usr/local/bin/slcan_add_$CAN_NAME.sh
Type=forking
EOL

        cat >/usr/local/bin/slcan_add_$CAN_NAME.sh <<-EOL
#!/bin/bash
/usr/bin/slcand -o -c -f -s8 -S 3000000 /dev/$CAN_NAME $CAN_NAME
sleep 1
/usr/sbin/ip link set up $CAN_NAME
/usr/sbin/ip link set $CAN_NAME txqueuelen 1000
EOL

        chmod +x /usr/local/bin/slcan_add_$CAN_NAME.sh
        echo "创建 slcan udev 规则: $CAN_NAME"
    else
        cat >>"$CAN_RULE_PATH" <<-EOL
ACTION=="add", SUBSYSTEM=="net", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="606f", NAME="$CAN_NAME", RUN+="/sbin/ip link set $CAN_NAME up type can bitrate 1000000", RUN+="/sbin/ip link set $CAN_NAME txqueuelen 1000"
EOL
        echo "创建 can udev 规则: $CAN_NAME"
    fi

done

udevadm control --reload-rules
udevadm trigger

echo "规则已加载，请重新插入设备以生效。"
