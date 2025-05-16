```bash
python3 main.py --path defaults/config.yaml \
                --components.names arm_leader arm \
                --components.paths airbot_play_mock airbot_play_mock  \
                --components.params '{}' '{"port": 50051}' \
                --components.roles l f \
                --components.groups left left \
                --dataset.directory example_task \
                --auto-control.rate 100 \
                --update-rate 20 \
                --sample-limit.start-round 0 \
                --sample-limit.size 1000 \
```