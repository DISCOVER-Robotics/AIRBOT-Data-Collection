import logging
from threading import current_thread, main_thread
import cv2
import numpy as np
from pydantic import BaseModel

from airbot_data_collection.common.visualizers.basis import (
    GUIVisualizerConfig,
    SampleInfo,
    VisualizerBasis,
)

def prepare_cv2_imshow(logger: logging.Logger):
    """Prepare OpenCV imshow for displaying images before import pynput.
    Otherwise, the imshow will block and not show the image.
    """

    logger.info("Preparing cv2.imshow")
    image = np.zeros((480, 640, 3), np.uint8)

    def show_image(name):
        logger.info(f"Showing {name}")
        cv2.imshow(name, image)
        cv2.waitKey(1)
        logger.info(f"{name} is ready")
        cv2.destroyAllWindows()

    show_image("Prepared image")

    logger.info("cv2.imshow is ready")


def decode_image(
    data: bytes, pixel_format: str, width: int = 0, height: int = 0
) -> np.ndarray:
    """Decode the image data based on the pixel format."""
    if pixel_format == "MJPEG":
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    elif pixel_format == "YUYV":
        assert (
            width > 0 and height > 0
        ), "Width and height must be provided for YUYV format"
        return cv2.cvtColor(
            np.frombuffer(data, np.uint8).reshape((height, width, 2)),
            cv2.COLOR_YUV2BGR_YUYV,
        )
    else:
        raise ValueError(f"Unsupported pixel format: {pixel_format}")


class OpenCVisualizerConfig(GUIVisualizerConfig):
    """Configuration for OpenCV visualizer."""

    window_type: int = cv2.WINDOW_NORMAL
    # -1 means do not wait key
    wait_key: int = 1


class TextConfig(BaseModel):
    """Configuration for text overlay on the image."""

    text: str = ""
    fontFace: int = cv2.FONT_HERSHEY_SIMPLEX
    fontScale: int = 1
    thickness: int = 1
    color: tuple[int, int, int] = (0, 0, 0)
    org: tuple[int, int] = (0, 0)


class OpenCVisualizer(VisualizerBasis):
    """Visualizer based on OpenCV."""

    config: OpenCVisualizerConfig

    def on_configure(self) -> bool:
        if not self.config.ignore_info:
            self.text_config = TextConfig()
            self.info_image = (
                np.ones((self.config.height, self.config.width, 3), dtype=np.uint8)
                * 255
            )
        return True

    def update(self, data: dict[str, np.ndarray], info: SampleInfo) -> bool:
        """Show the data on the OpenCV window."""
        # TODO: add concatenation for the data?
        if current_thread() is not main_thread():
            self.get_logger().warning("Not running in the main thread, skipping imshow")
            return True
        for key, value in data.items():
            if isinstance(value, bytes):
                value = decode_image(value, self.config.pixel_format)
            if self.config.swap_rgb_bgr:
                value = value[..., ::-1]
            cv2.imshow(key, value)
        if not self.config.ignore_info:
            image = self._put_info(self.info_image.copy(), info)
            cv2.imshow("info", image)
        if self.config.wait_key > 0:
            cv2.waitKey(1)
        return True

    def shutdown(self):
        cv2.destroyAllWindows()

    def _put_info(self, image: np.ndarray, info: SampleInfo) -> None:
        """Put the current episode and step information on the image.

        This function overlays the episode and step text on the image background,
        and then displays the image with the updated text using OpenCV.
        """
        text_top = f"Sample Round: {info.round}"
        text_bottom = f"Sample Index: {info.index}"
        image = image

        # Calculate text size for centering the text
        self.text_width_top, self.text_height_top = cv2.getTextSize(
            text_top,
            self.text_config.fontFace,
            self.text_config.fontScale,
            self.text_config.thickness,
        )[0]
        self.text_width_bottom, self.text_height_bottom = cv2.getTextSize(
            text_bottom,
            self.text_config.fontFace,
            self.text_config.fontScale,
            self.text_config.thickness,
        )[0]

        x_top = (self.config.width - self.text_width_top) // 2
        y_top = int(self.config.height * 0.25)
        x_bottom = (self.config.width - self.text_width_bottom) // 2
        y_bottom = int(self.config.height * 0.75)

        text_cfg_dict = self.text_config.model_dump()
        text_cfg_dict["text"] = text_top
        text_cfg_dict["org"] = (x_top, y_top)
        cv2.putText(image, **text_cfg_dict)
        text_cfg_dict["text"] = text_bottom
        text_cfg_dict["org"] = (x_bottom, y_bottom)
        cv2.putText(image, **text_cfg_dict)
        return image
