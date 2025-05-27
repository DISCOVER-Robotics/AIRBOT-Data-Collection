# python3 main.py --path defaults/config.yaml \
#                 --components.names mmk \
#                 --components.paths airbot_mmk \
#                 --components.params '{}' \
#                 --components.roles o \
#                 --components.groups mmk \
#                 --dataset.directory example_task \
#                 --auto-control.rate 100 \
#                 --update-rate 20 \
#                 --sample-limit.start-round 0 \
#                 --sample-limit.size 1000

python3 main.py --path defaults/config_playback.yaml \
                --components.names bson_player mmk \
                --components.paths bson_player airbot_mmk \
                --components.params "{}" "{}" \
                --components.roles l f \
                --components.groups mmk mmk \
                --dataset.directory example_task \
                --auto-control.rate 100 \
                --update-rate 20 \
                --sample-limit.start-round 0 \
                --sample-limit.size 1000

# python3 main.py --path defaults/config_vr.yaml \
#                 --components.names mmk_vr mmk \
#                 --components.paths airbot_mmk_vr airbot_mmk \
#                 --components.params '{}' '{}' \
#                 --components.roles l f \
#                 --components.groups mmk mmk \
#                 --dataset.directory example_task \
#                 --auto-control.rate 100 \
#                 --update-rate 20 \
#                 --sample-limit.start-round 0 \
#                 --sample-limit.size 1000