import av
import numpy as np
from io import BytesIO
import fractions
from typing import List, Dict, Union
from turbojpeg import TurboJPEG
from logging import getLogger


logger = getLogger(__name__)


def read_all_frames_pyav(video_path: str) -> List[np.ndarray]:
    """
    Reads all frames from a video file using PyAV.
    Args:
        video_path (str): Path to the video file.
    Returns:
        List[np.ndarray]: A list of frames, each represented as a NumPy array.
    """
    container = av.open(video_path)
    frames = []
    for frame in container.decode(video=0):
        frames.append(frame.to_ndarray(format="rgb24"))
    container.close()
    return frames


def encode_h264(data: List[Dict[str, Union[int, bytes]]]) -> bytes:
    if isinstance(data[0]["data"], bytes):
        jpeg = TurboJPEG()
        preprocess = jpeg.decode
    else:
        # No preprocessing needed if data is already in numpy format
        preprocess = lambda x: x
    outbuf = BytesIO()
    # "ultrafast", "superfast", "veryfast", "faster", "fast"
    container = av.open(outbuf, "w", format="mp4", options={"preset": "fast"})
    stream = container.add_stream("h264", options={"preset": "fast"})
    stream.width = data[0]["data"].shape[1]
    stream.height = data[0]["data"].shape[0]
    stream.pix_fmt = "yuv420p"
    # The time base is set to 1e-9 second (i.e. timestamps are in nanoseconds)
    stream.time_base = fractions.Fraction(1, 1e9)
    start_time = data[0]["t"]
    last_time = start_time
    time_base = fractions.Fraction(1, 1000)
    for frame in data:
        video_frame = av.VideoFrame.from_ndarray(
            preprocess(frame["data"]), format="bgr24"
        )
        cur_time = frame["t"]
        # Ensure timestamps are strictly increasing
        if cur_time <= last_time:
            logger.warning(
                f"Frame timestamp {cur_time} is not greater than last timestamp {last_time}. Adjusting."
            )
            cur_time = last_time + 1e9 / 60
        video_frame.pts = cur_time - start_time
        last_time = cur_time
        video_frame.time_base = time_base
        for packet in stream.encode(video_frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return outbuf.getvalue()
