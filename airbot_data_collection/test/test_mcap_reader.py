from airbot_data_collection.common.utils.mcap_utils import McapFlatbufferReader
from pprint import pprint
import time


with open(
    "/home/ghz/Work/OpenGHz/data-collection/airbot-data-collection/airbot_data_collection/data/arm1-001/0.mcap",
    "rb",
) as f:
    reader = McapFlatbufferReader(f)

    pprint(reader.all_topic_names())
    pprint(reader.all_attachment_names())

    # start = time.perf_counter()
    # for low_dim in reader.iter_message_samples():
    #     print(time.perf_counter() - start)
    #     pprint(low_dim)
    #     start = time.perf_counter()

    # start = time.perf_counter()
    # for images in reader.iter_attachment_samples(["/env_camera/env/color/image_raw"]):
    #     print(time.perf_counter() - start)
    #     pprint(images.keys())
    #     start = time.perf_counter()

    counts = reader.topic_message_counts()
    count = reader.equal_message_counts(counts)
    pprint(count)
    assert count, "Message counts are not equal across topics"

    # start = time.perf_counter()
    # time_costs = []
    # for data in reader.iter_samples(attachments=["/env_camera/env/color/image_raw"]):
    #     print(time.perf_counter() - start)
    #     time_costs.append(time.perf_counter() - start)
    #     pprint(data.keys())
    #     start = time.perf_counter()

    # print("Total samples:", len(time_costs))
    # print("Average time cost per sample:", sum(time_costs) / len(time_costs))
    # print(sorted(time_costs))
