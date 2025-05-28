#!/bin/bash

# usb2can_bind.sh
# 用法示例：
#   sudo ./usb2can_bind.sh --target can_lead can_follow
#   sudo ./usb2can_bind.sh rm [can|slcan]

CAN_RULE_PATH=/etc/udev/rules.d/91-usb-can-airbot.rules
SLCAN_RULE_PATH=/etc/udev/rules.d/91-usb-slcan-airbot.rules

print_usage() {
    echo "Usage:"
    echo "  $0 --target name1 name2 ..."
    echo "  $0 rm [can|slcan]"
    exit 1
}

# --- 参数解析 ---
if [[ "$1" == "rm" ]]; then
    MODE="rm"
    TARGET_TYPE="$2"
else
    MODE="bind"
    # 解析 --target 后的所有参数
    if [[ "$1" != "--target" ]]; then
        echo "Missing --target"
        print_usage
    fi
    shift
    TARGETS=("$@")
    # 必须至少提供一个目标名称
    if [[ ${#TARGETS[@]} -lt 1 ]]; then
        echo "请至少指定一个目标 CAN 名称"
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

# 计算要等待的设备数量
EXPECTED_COUNT=${#TARGETS[@]}
echo "等待插入 $EXPECTED_COUNT 台 USB2CAN 设备..."

# 记录当前已有设备，忽略它们
mapfile -t IGNORED < <(lsusb \
    | awk '/ID (0483:0000|1d50:606f)/ {print $2 "/" $4}' \
    | sed 's/://')

# 监听新设备插入
DETECTED=()
while [[ ${#DETECTED[@]} -lt EXPECTED_COUNT ]]; do
    sleep 1
    mapfile -t NOW < <(lsusb \
        | awk '/ID (0483:0000|1d50:606f)/ {print $2 "/" $4}' \
        | sed 's/://')
    for dev in "${NOW[@]}"; do
        if [[ ! " ${IGNORED[*]} " =~ " $dev " ]] && [[ ! " ${DETECTED[*]} " =~ " $dev " ]]; then
            echo "检测到新设备: $dev"
            DETECTED+=( "$dev" )
            (( ${#DETECTED[@]} == EXPECTED_COUNT )) && break 2
        fi
    done
done

echo "共检测到 ${#DETECTED[@]} 台新设备，开始生成 udev 规则..."

# 逐一按顺序绑定 TARGETS
for idx in "${!DETECTED[@]}"; do
    DEV_PATH="/dev/bus/usb/${DETECTED[$idx]}"
    SERIAL=$(udevadm info --query=property \
        --path="$(udevadm info --query=path --name="$DEV_PATH")" \
        | awk -F= '/ID_SERIAL_SHORT/ {print $2}')
    [[ -z "$SERIAL" ]] && SERIAL="Unknown"

    CAN_NAME="${TARGETS[$idx]}"
    VENDOR_ID=$(udevadm info --query=property \
        --path="$(udevadm info --query=path --name="$DEV_PATH")" \
        | awk -F= '/ID_VENDOR_ID/ {print $2}')
    PRODUCT_ID=$(udevadm info --query=property \
        --path="$(udevadm info --query=path --name="$DEV_PATH")" \
        | awk -F= '/ID_MODEL_ID/ {print $2}')

    if [[ "$VENDOR_ID" == "0483" && "$PRODUCT_ID" == "0000" ]]; then
        # slcan 规则
        cat >>"$SLCAN_RULE_PATH" <<-EOL
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="0000", ATTRS{serial}=="$SERIAL", SYMLINK+="$CAN_NAME", GROUP="dialout", MODE="0777", TAG+="systemd", ENV{SYSTEMD_WANTS}="slcan_$CAN_NAME@.service"
EOL
        chmod +x "$SLCAN_RULE_PATH"

        # service 文件
        cat >/etc/systemd/system/slcan_$CAN_NAME@.service <<-EOL
[Unit]
Description=SocketCAN device $CAN_NAME
After=dev-$CAN_NAME.device
BindsTo=dev-$CAN_NAME.device

[Service]
ExecStart=/usr/local/bin/slcan_add_$CAN_NAME.sh
Type=forking
EOL
        chmod +x /etc/systemd/system/slcan_$CAN_NAME@.service

        # 启动脚本
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
        # can 规则
        cat >>"$CAN_RULE_PATH" <<-EOL
ACTION=="add", SUBSYSTEM=="net", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="606f", ATTRS{serial}=="$SERIAL", NAME="$CAN_NAME", RUN+="/sbin/ip link set $CAN_NAME up type can bitrate 1000000", RUN+="/sbin/ip link set $CAN_NAME txqueuelen 1000"
EOL
        chmod +x "$CAN_RULE_PATH"
        echo "创建 can udev 规则: $CAN_NAME"
    fi
done

# 重新加载 udev
udevadm control --reload-rules
udevadm trigger

echo "规则已加载，请重新插入设备以生效。"
