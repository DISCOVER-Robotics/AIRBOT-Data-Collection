#!/bin/bash

CAN_RULE_PATH=/etc/udev/rules.d/91-usb-can-airbot.rules
SLCAN_RULE_PATH=/etc/udev/rules.d/91-usb-slcan-airbot.rules

# Remove rules
if [ "$1" = "rm" ]; then
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

# Must run as root
if [ $EUID -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

# Function to get USB info (VID, PID, SERIAL) from interface name
get_usb_info_from_interface() {
    local IFACE=$1

    DEV_PATH=$(readlink -f /sys/class/net/$IFACE/device)
    USB_DEV=$(echo "$DEV_PATH" | grep -oE 'usb[0-9]+/[0-9-]+')
    FULL_USB_PATH="/sys/bus/usb/devices/$USB_DEV"

    if [ ! -d "$FULL_USB_PATH" ]; then
        echo "Could not find USB path for $IFACE"
        return 1
    fi

    VENDOR=$(cat $FULL_USB_PATH/idVendor 2>/dev/null)
    PRODUCT=$(cat $FULL_USB_PATH/idProduct 2>/dev/null)
    SERIAL=$(cat $FULL_USB_PATH/serial 2>/dev/null)

    if [ -z "$VENDOR" ] || [ -z "$PRODUCT" ] || [ -z "$SERIAL" ]; then
        echo "Missing USB ID info for $IFACE"
        return 1
    fi

    echo "$VENDOR|$PRODUCT|$SERIAL"
    return 0
}

# Add rule based on VID/PID/SERIAL
add_udev_rule() {
    local VENDOR=$1
    local PRODUCT=$2
    local SERIAL=$3
    local NAME=$4

    if [[ "$VENDOR" == "0483" && "$PRODUCT" == "0000" ]]; then
        echo "Creating slcan rule for $NAME"
        cat >>"$SLCAN_RULE_PATH" <<EOL
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="$VENDOR", ATTRS{idProduct}=="$PRODUCT", ATTRS{serial}=="$SERIAL", SYMLINK+="$NAME", GROUP="dialout", MODE="0777", TAG+="systemd", ENV{SYSTEMD_WANTS}="slcan_$NAME@.service"
EOL

        # Create slcan service and script
        cat >/etc/systemd/system/slcan_$NAME@.service <<EOL
[Unit]
Description=SocketCAN device $NAME
After=dev-$NAME.device
BindsTo=dev-$NAME.device

[Service]
ExecStart=/usr/local/bin/slcan_add_$NAME.sh
Type=forking
EOL

        cat >/usr/local/bin/slcan_add_$NAME.sh <<EOL
#!/bin/bash
/usr/bin/slcand -o -c -f -s8 -S 3000000 /dev/$NAME $NAME
sleep 1
/usr/sbin/ip link set up $NAME
/usr/sbin/ip link set $NAME txqueuelen 1000
EOL
        chmod +x /usr/local/bin/slcan_add_$NAME.sh
        chmod +x /etc/systemd/system/slcan_$NAME@.service
    else
        echo "Creating native CAN rule for $NAME"
        cat >>"$CAN_RULE_PATH" <<EOL
ACTION=="add", SUBSYSTEM=="net", ATTRS{idVendor}=="$VENDOR", ATTRS{idProduct}=="$PRODUCT", ATTRS{serial}=="$SERIAL", NAME="$NAME", RUN+="/sbin/ip link set $NAME up type can bitrate 1000000", RUN+="/sbin/ip link set $NAME txqueuelen 1000"
EOL
    fi
}

# Parse --raw mode
if [[ "$1" == "--raw" && "$4" == "--new" ]]; then
    RAW1=$2
    RAW2=$3
    NEW1=$5
    NEW2=$6

    for idx in 1 2; do
        CUR_IF="RAW$idx"
        NEW_IF="NEW$idx"
        echo "Processing interface: ${!CUR_IF} -> ${!NEW_IF}"

        USB_INFO=$(get_usb_info_from_interface "${!CUR_IF}")
        if [ $? -ne 0 ]; then
            echo "Failed to get USB info for ${!CUR_IF}"
            exit 1
        fi

        IFS='|' read VENDOR PRODUCT SERIAL <<< "$USB_INFO"
        add_udev_rule "$VENDOR" "$PRODUCT" "$SERIAL" "${!NEW_IF}"
    done

    udevadm control --reload-rules
    udevadm trigger
    echo "Rules applied. Please replug USB2CAN devices."
    exit 0
fi

# Otherwise: fallback to interactive mode (original script)
echo "Running in interactive mode..."
# [此处保留你原有的手动设备映射部分，不重复粘贴]
