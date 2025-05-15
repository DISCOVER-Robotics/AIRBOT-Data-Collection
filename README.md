```bash
python3 main.py --components.names left_arm_leader left_arm \
                --components.paths airbot_play_mock airbot_play_mock  \
                --components.params '{}' '{"port": 50051}' \
                --components.roles l f \
                --dataset.directory example_task \
                --dataset.start-round 0 \
                --auto-control.rate 100 \
                --update_rate 20 \
```