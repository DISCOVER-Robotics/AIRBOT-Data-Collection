from airbot_data.io import load_bson
import argparse
from pprint import pprint


def main():
    parser = argparse.ArgumentParser(description="Show BSON file content")
    parser.add_argument("bson_file", type=str, help="Path to the BSON file")
    parser.add_argument(
        "-s",
        "--start-index",
        type=int,
        default=0,
        help="Start index for displaying data",
    )
    parser.add_argument(
        "-e",
        "--end-index",
        type=int,
        default=10,
        help="End index for displaying data",
    )
    args = parser.parse_args()

    data = load_bson(args.bson_file)

    print(data.keys())
    print(data["data"].keys())
    pprint(data["metadata"]["topics"])

    for i in range(args.start_index, args.end_index):
        print(f"Index: {i}")
        for topic in data["data"].keys():
            if "image" in topic:
                image = data["data"][topic][i]["data"]
                image_t = data["data"][topic][i]["t"]
                print(topic, image.shape, image.dtype, image_t)
            else:
                print(topic, data["data"][topic][i])
        print("\n")


if __name__ == "__main__":
    main()
