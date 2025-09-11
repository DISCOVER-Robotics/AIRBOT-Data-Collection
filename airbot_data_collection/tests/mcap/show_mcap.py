from airbot_data_collection.common.datasets.mcap_dataset import (
    McapFlatbufferSampleDataset,
    McapDatasetConfig,
)
from pprint import pprint
from pydantic_settings import CliApp


args = CliApp().run(McapDatasetConfig)

# dataset = McapFlatbufferSampleDataset(args)
dataset = McapFlatbufferSampleDataset(
    McapDatasetConfig(data_root="data/test/1227.mcap")
)
dataset.load()

pprint(dataset.reader.all_topic_names())
pprint(dataset.reader.topic_message_counts())
all_attachments = dataset.reader.all_attachment_names()
pprint(all_attachments)
color_topics = [att for att in all_attachments if "color" in att]
pprint(color_topics)

for index, sample in enumerate(dataset.reader.iter_attachment_samples(color_topics)):
    # print(f"Sample {index}: {sample.keys()}")
    # print(index)
    pass
