import json
from typing import Optional, List


class JsonPlayer:
    def __init__(self, file_path: str, topics: List[str]):
        assert topics, "no topic specified"
        self.file_path = file_path
        self.topics = topics
        self._data: dict = self._load_data()
        self._length = len(self._data[self.topics[0]])

    def _load_data(self):
        with open(self.file_path, "r") as f:
            return json.load(f)

    def seek(self, index: int):
        self._index = index

    def update(self) -> Optional[List[float]]:
        if self._index >= self._length:
            return None
        out = []
        for topic in self.topics:
            if "eef" in topic:
                key = "t"
                self._data[topic][self._index][key][0] *= 0.072
            else:
                key = "pos"
            out.extend(self._data[topic][self._index][key])
        self._index += 1
        return out


if __name__ == "__main__":
    player = JsonPlayer("path/to/json/file.json", ["/topic1", "/topic2"])
    player.seek(0)
    while True:
        data = player.update()
        if data is None:
            break
        print(data)
