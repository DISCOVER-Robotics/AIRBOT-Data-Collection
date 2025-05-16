```bash
python3 main.py --path defaults/config.yaml \
                --components.names arm_leader arm left_camera \
                --components.paths airbot_play airbot_play usb_cam \
                --components.params '{}' '{"port": 50051}' '{"camera_index": 0}' \
                --components.roles l f o \
                --components.groups left left left \
                --dataset.directory example_task \
                --auto-control.rate 100 \
                --update-rate 20 \
                --sample-limit.start-round 0 \
                --sample-limit.size 1000
```