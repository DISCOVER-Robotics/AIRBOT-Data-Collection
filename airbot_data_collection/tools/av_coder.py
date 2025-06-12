import av
import numpy as np
from io import BytesIO
import fractions
from typing import List, Optional, Union, Literal, Dict
from turbojpeg import TurboJPEG
from logging import getLogger
import time
from concurrent.futures import ThreadPoolExecutor


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
        else:
            self._executor = None
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
        # start = time.monotonic()
        if self._start_time == 0:
            assert timestamp > 0, "Timestamp must be greater than 0"
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
    def decode(
        video: Union[str, bytes],
        indices: Optional[List[int]] = None,
        frame_format: str = "bgr24",
        thread_type: str = "AUTO",
    ) -> Union[List[np.ndarray], Dict[int, np.ndarray]]:
        """
        Reads all frames from a video file using PyAV.
        Args:
            video_path (str): Path to the video file or the encoded video bytes.
        Returns:
            List[np.ndarray]: A list of frames, each represented as a NumPy array.
        """
        if isinstance(video, bytes):
            container = av.open(BytesIO(video))
        else:
            container = av.open(video, "r")
        # Enable multithreading for decoding
        container.streams.video[0].thread_type = thread_type
        frame_cnt = container.streams.video[0].frames
        if indices is not None:
            indices = sorted(set(indices))
            end_index = indices[-1]
            assert 0 <= end_index < frame_cnt, f"{end_index} out of bounds"
            frames = {}
            exp_cnt = len(indices)
        else:
            frames = []
            exp_cnt = frame_cnt
        for index, frame in enumerate(container.decode(video=0)):
            frame_arr = frame.to_ndarray(format=frame_format)
            if indices is None:
                frames.append(frame_arr)
            elif index == indices[0]:
                frames[index] = frame_arr
                indices.pop(0)
                if not indices:
                    break
        container.close()
        assert (
            len(frames) == exp_cnt
        ), f"Frame count mismatch: {len(frames)} != {exp_cnt}"
        return frames


if __name__ == "__main__":

    av_coder = AvCoder(async_encode=False)

    def test_decode(video, indices=None):
        """
        Test encoding a single frame.
        """
        start = time.monotonic()
        frames = av_coder.decode(video, indices)
        print(f"Frame resolution: {frames[0].shape}")
        cost_time = time.monotonic() - start
        print(f"Decode cost time: {cost_time:.2f} seconds for {len(frames)} frames")
        print(f"Time cost decoding per frame: {cost_time / len(frames):.4f} seconds")
        return frames

    frames = test_decode("/home/ghz/视频/示教器问题.mp4")
    start = time.monotonic()
    init_stamp = time.time_ns()
    for i, frame in enumerate(frames):
        stamp = init_stamp + i * 1e9 // 30
        # print(
        #     f"Encoding frame {i} with shape {frame.shape} and dtype {frame.dtype} and timestamp {stamp}"
        # )
        av_coder.encode_frame(frame, stamp)
    encoded_data = av_coder.end()
    print(f"Encoded data size: {len(encoded_data)} bytes")
    print(f"Encoding cost time: {time.monotonic() - start:.2f} seconds")
    print(
        f"Time cost encoding per frame: {(time.monotonic() - start) / len(frames):.4f} seconds"
    )

    # Test decoding the encoded data
    frames = test_decode(encoded_data)
    test_decode(encoded_data, [0, 2, 4]).keys()
