import av
import numpy as np
from io import BytesIO
import fractions
from typing import List, Union, Literal
from turbojpeg import TurboJPEG
from logging import getLogger
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class AvCoder:
    """
    A class for encoding video frames using PyAV.
    This class supports encoding frames in various formats and ensures that
    timestamps are strictly increasing.
    It can handle both NumPy arrays and raw byte data for frames.
    """

    def __init__(
        self,
        time_base: int = int(1e9),
        frame_format: str = "bgr24",
        async_encode: bool = True,
    ):
        self._time_base = fractions.Fraction(1, time_base)
        self._configured = False
        self._frame_format = frame_format
        self._preprocess = None
        self._reset()
        if async_encode:
            # set max_workers to 1 to ensure frames are processed in order
            self._executor = ThreadPoolExecutor(1, "av_coder")
        self._last_future = None

    def _reset(self):
        """
        Reset the encoder state.
        This method clears the output buffer and resets the start and last timestamps.
        """
        self._outbuf = BytesIO()
        self._container = av.open(self._outbuf, "w", format="mp4")
        self.stream = self._container.add_stream("h264", options={"preset": "fast"})
        self.stream.time_base = self._time_base
        self._start_time = 0
        self._last_time = 0
        self._configured = False

    def configure_stream(
        self,
        width: int,
        height: int,
        pix_fmt: Literal["yuv420p", "rgb24"] = "yuv420p",
    ):
        """
        Configure the stream with the given parameters.
        """
        stream = self.stream
        stream.width = width
        stream.height = height
        stream.pix_fmt = pix_fmt
        self._configured = True

    def set_frame_type(self, frame_type: str):
        if frame_type == "bytes":
            jpeg = TurboJPEG()
            self._preprocess = jpeg.decode
        elif frame_type == "ndarray":
            self._preprocess = lambda x: x
        else:
            raise ValueError(f"Unsupported frame type: {frame_type}")

    def _set_frame_type(self, frame: Union[np.ndarray, bytes]):
        """
        Set the frame type based on the input frame.
        This method is called internally to determine how to process the frame.
        """
        if isinstance(frame, bytes):
            self.set_frame_type("bytes")
        elif isinstance(frame, np.ndarray):
            self.set_frame_type("ndarray")
        else:
            raise TypeError(f"Unsupported frame type: {type(frame)}")

    def _encode_frame(
        self,
        frame: Union[np.ndarray, bytes],
        timestamp: int,
    ):
        """
        Encode a single video frame with the given timestamp.
        Args:
            frame (Union[np.ndarray, bytes]): The video frame to encode.
            timestamp (int): The timestamp for the frame in nanoseconds.
        """
        start = time.monotonic()
        if self._start_time == 0:
            self._start_time = timestamp
        if self._preprocess is None:
            self._set_frame_type(frame)
        video_frame = av.VideoFrame.from_ndarray(
            self._preprocess(frame), format=self._frame_format
        )
        if not self._configured:
            self.configure_stream(video_frame.width, video_frame.height)
        # Ensure timestamps are strictly increasing
        last_time = self._last_time
        if timestamp <= last_time:
            self.get_logger().warning(
                f"Frame timestamp {timestamp} is not greater than last timestamp {last_time}. Adjusting."
            )
            timestamp = last_time + 1
        self._last_time = timestamp
        video_frame.pts = timestamp - self._start_time
        video_frame.time_base = self._time_base
        for packet in self.stream.encode(video_frame):
            self._container.mux(packet)
        # print("cost time:", time.monotonic() - start)

    def encode_frame(
        self,
        frame: Union[np.ndarray, bytes],
        timestamp: int,
    ):
        """
        Encode a video frame with the given timestamp.
        Args:
            frame (Union[np.ndarray, bytes]): The video frame to encode.
            timestamp (int): The timestamp for the frame in nanoseconds.
        """
        if self._executor is not None:
            self._last_future = self._executor.submit(
                self._encode_frame, frame, timestamp
            )
        else:
            self._encode_frame(frame, timestamp)

    def end(self) -> bytes:
        """
        Finalize the encoding process and return the encoded data bytes.
        """
        if self._last_future:
            self._last_future.result()
        for packet in self.stream.encode():
            self._container.mux(packet)
        self._container.close()
        value = self._outbuf.getvalue()
        self._outbuf.close()
        self._reset()
        return value

    def get_logger(self):
        """
        Returns a logger instance for logging purposes.
        """
        return getLogger(self.__class__.__name__)

    @staticmethod
    def read_all_frames_pyav(
        video_path: str, frame_format: str = "bgr24", thread_type: str = "AUTO"
    ) -> List[np.ndarray]:
        """
        Reads all frames from a video file using PyAV.
        Args:
            video_path (str): Path to the video file.
        Returns:
            List[np.ndarray]: A list of frames, each represented as a NumPy array.
        """
        container = av.open(video_path)
        # Enable multithreading for decoding
        container.streams.video[0].thread_type = thread_type
        frames = []
        for frame in container.decode(video=0):
            frames.append(frame.to_ndarray(format=frame_format))
        container.close()
        return frames
