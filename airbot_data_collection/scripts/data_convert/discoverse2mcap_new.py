from airbot_data_collection.common.utils.mcap_utils import (
    McapFlatbufferWriter,
    FlatbufferSchemas,
)
from airbot_data_collection.airbot.samplers.mcap_sampler import (
    AIRBOTMcapDataSampler,
    AIRBOTMcapDataSamplerConfig,
    TaskInfo,
)
from airbot_data_collection.utils import zip
from mcap.writer import Writer
import os
import time
import json
from pydantic import BaseModel
from pydantic_settings import CliApp
from typing import Dict
from functools import cache


class Config(BaseModel):
    """Configuration for the DISCOVERSE to MCAP conversion.
    Args:
        root (str): Root directory containing the task data.
        task_name (str): Name of the task to process.
        output_dir (str): Directory to save the output MCAP files. If not provided,
            it defaults to `<root>/mcap/<task_name>`.
    """

    root: str
    task_name: str
    output_dir: str = ""


config = CliApp.run(Config)

start = time.perf_counter()
directory = f"{config.root}/{config.task_name}"
output_dir = config.output_dir or f"{config.root}/mcap/{config.task_name}"

os.makedirs(output_dir, exist_ok=True)

# find all folders in the directory
folders = [f.path for f in os.scandir(directory) if f.is_dir()]
print(folders)

config = AIRBOTMcapDataSamplerConfig(task_info=TaskInfo(task_name=config.task_name))

for folder in folders:
    fd_base = os.path.basename(folder)
    if not fd_base.isdigit():
        print(f"Skipping folder {folder} as it does not match the expected format.")
        continue
    episode = int(fd_base)
    output_file_path = f"{output_dir}/{episode}.mcap"
    print(f"{output_file_path=}")
    mcap_writer = Writer(output_file_path)
    mcap_writer.start()
    flb_writer = McapFlatbufferWriter()
    flb_writer.set_writer(mcap_writer)
    all_schemas = set(FlatbufferSchemas)
    all_schemas.remove(FlatbufferSchemas.COMPRESSED_IMAGE)
    flb_writer.register_schemas(all_schemas)
    AIRBOTMcapDataSampler.add_config_metadata(mcap_writer, config)
    # find all .mp4 files in the folder
    mp4_files = [
        f.path for f in os.scandir(folder) if f.is_file() and f.name.endswith(".mp4")
    ]
    print(f"{mp4_files=}")
    # add video attachments
    for mp4_file in mp4_files:
        with open(mp4_file, "rb") as f:
            name = f"/{os.path.basename(mp4_file).removesuffix('.mp4')}/color/image_raw"
            print(f"Adding video attachment: {name}")
            AIRBOTMcapDataSampler.add_video_attachment(
                mcap_writer,
                name,
                f.read(),
            )

    topic_mapping = {
        "obs": {
            "jq": (
                ("/follow/arm/joint_states/position", slice(0, 6)),
                ("/follow/eef/joint_states/position", slice(6, 7)),
            ),
            "eef_pos": "/follow/arm/pose/position",
            "end_force": ("/follow/arm/wrench/force", slice(0, 3)),
        },
        "act": "/lead/arm/pose/position",
    }

    path = f"{folder}/obs_action.json"
    if not os.path.exists(path):
        print(f"Skipping file {path} as it does not exist.")
        continue

    @cache
    def to_topic_with_slice(key: str, name: str):
        topic = topic_mapping[key][name]
        topics = (
            ((topic, None),)
            if isinstance(topic, str)
            else (topic,)
            if isinstance(topic[0], str)
            else topic,
        )
        return topics

    with open(path) as f:
        act_obs: Dict[str, Dict[str, list]] = json.load(f)
        print(f"{act_obs.keys()=}")
        # register joint state channels
        for key, value in act_obs.items():
            for name, data in value.items():
                topic_with_slices = to_topic_with_slice(key, name)
                for tpc, _ in topic_with_slices:
                    print(f"register channel for topic: {tpc}")
                    flb_writer.register_channel(tpc, FlatbufferSchemas.FLOAT_ARRAY)

        # for keys, values in

        # add joint states messages
        stamps_ns = []
        # for stamp, jq, eef_pos, eer_eff, act in zip(
        #     act_obs["time"],
        #     act_obs["obs"]["jq"],
        #     act_obs["obs"]["eef_pos"],
        #     act_obs["obs"]["end_force"],
        #     act_obs["act"],
        #     strict=True,
        # ):
        #     stamp_ns = int(stamp * 1e9)
        #     for group, value in zip(groups, [act, jq]):
        #         for component, slc in zip(components, slices):
        #             flb_writer.add_field_array(
        #                 {"position": to_topic(group, component)},
        #                 data={"position": value[slc]},
        #                 publish_time=stamp_ns,
        #                 log_time=stamp_ns,
        #             )

        #     stamps_ns.append(stamp_ns)
        # AIRBOTMcapDataSampler.add_log_stamps_attachment(
        #     mcap_writer,
        #     stamps_ns,
        # )
    mcap_writer.finish()


print(
    f"Time taken: {time.perf_counter() - start:.3f} seconds of {len(folders)} folders"
)
