#!/bin/sh

# 定义CAN接口和要发送的帧
CAN_IFACE=$1
SEND_CMD="008#05"

# 启动监听CAN总线，使用后台进程，并重定向输出
candump $CAN_IFACE,108:7FF > /tmp/can_recv.log &
DUMP_PID=$!

# 给一点时间确保 candump 已启动
sleep 0.1

# 发送CAN帧
cansend $CAN_IFACE $SEND_CMD

# 等待一小段时间确保接收
sleep 0.5

# 杀掉 candump 进程
kill $DUMP_PID

# 输出第一帧
FIRST_LINE=$(head -n 1 /tmp/can_recv.log)
echo "接收到的第一帧: $FIRST_LINE"
