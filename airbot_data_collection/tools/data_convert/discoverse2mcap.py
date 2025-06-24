from airbot_data_collection.tools.mcap_utils import (
    McapFlatbufferWriter,
    FlatbufferSchemas,
)
from airbot_data_collection.airbot.samplers.mcap_sampler import (
    AIRBOTMcapDataSampler,
    AIRBOTMcapDataSamplerConfig,
    TaskInfo,
)
from mcap.writer import Writer
import os
import time
import json
import argparse


start = time.perf_counter()
root = "/home/ghz/Work/airbot/DISCOVERSE/data"
task_name = "jujube_pick"
directory = f"{root}/{task_name}"
output_dir = f"{root}/mcap/{task_name}"
os.makedirs(output_dir, exist_ok=True)

# find all folders in the directory
folders = [f.path for f in os.scandir(directory) if f.is_dir()]
print(folders)

config = AIRBOTMcapDataSamplerConfig(task_info=TaskInfo(task_name=task_name))

for folder in folders:
    episode = int(os.path.basename(folder))
    output_file_path = f"{output_dir}/{episode + 4}.mcap"
    print(output_file_path)
    mcap_writer = Writer(output_file_path)
    mcap_writer.start()
    flb_writer = McapFlatbufferWriter()
    flb_writer.set_writter(mcap_writer)
    all_schemas = set(FlatbufferSchemas)
    all_schemas.remove(FlatbufferSchemas.COMPRESSED_IMAGE)
    flb_writer.register_schemas(all_schemas)
    AIRBOTMcapDataSampler.add_config_metadata(mcap_writer, config)
    # find all .mp4 files in the folder
    mp4_files = [
        f.path for f in os.scandir(folder) if f.is_file() and f.name.endswith(".mp4")
    ]
    print(mp4_files)
    # add video attachments
    for mp4_file in mp4_files:
        with open(mp4_file, "rb") as f:
            name = f"{os.path.basename(mp4_file).removesuffix('.mp4')}/color/image_raw"
            print(f"Adding video attachment: {name}")
            AIRBOTMcapDataSampler.add_video_attachment(
                mcap_writer,
                name,
                f.read(),
            )

    def to_topic(group: str, component: str) -> str:
        return f"{group}/{component}/joint_state/position"

    # load json dict
    groups = ["lead", "follow"]
    components = ["arm", "eef"]
    slices = [slice(0, 6), slice(6, 7)]
    with open(f"{folder}/obs_action.json") as f:
        act_obs: dict = json.load(f)
        print(act_obs.keys())
        # register joint state channels
        for group in groups:
            for comp in components:
                flb_writer.register_channel(
                    to_topic(group, comp), FlatbufferSchemas.FLOAT_ARRAY
                )
        # add joint states messages
        stamps_ns = []
        for stamp, obs, act in zip(
            act_obs["time"],
            act_obs["obs"]["jq"],
            act_obs["act"],
            strict=True,
        ):
            stamp_ns = int(stamp * 1e9)
            for group, value in zip(groups, [act, obs]):
                # print(value)
                for component, slc in zip(components, slices):
                    flb_writer.add_joint_state(
                        {"position": to_topic(group, component)},
                        data={"position": value[slc]},
                        publish_time=stamp_ns,
                        log_time=stamp_ns,
                    )
            stamps_ns.append(stamp_ns)
            AIRBOTMcapDataSampler.add_log_stamps_attachment(
                mcap_writer,
                stamps_ns,
            )
    mcap_writer.finish()


print(
    f"Time taken: {time.perf_counter() - start:.3f} seconds of {len(folders)} folders"
)
