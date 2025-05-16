import cv2
from airbot_data_collection.common.visualiziers.basis import (
    GUIVisualizer,
    GUIVisualizerConfig,
    SampleInfo,
)
import numpy as np
from typing import Union, Iterable, Dict, Tuple
from pydantic import BaseModel
import logging


def prepare_cv2_imshow(logger: logging.Logger):

    logger.info("Preparing cv2.imshow")
    image = np.zeros((480, 640, 3), np.uint8)

    def show_image(name):
        logger.info(f"Showing {name}")
        for _ in range(1):
            cv2.imshow(name, image)
            cv2.waitKey(1)
        logger.info(f"{name} is ready")
        cv2.destroyAllWindows()

    show_image("Main image")

    logger.info("cv2.imshow is ready")


class OpenCVisualizerConfig(GUIVisualizerConfig):
    """Configuration for OpenCV visualizer."""

    window_type: int = cv2.WINDOW_NORMAL


class TextConfig(BaseModel):
    """Configuration for text overlay on the image."""

    text: str = ""
    fontFace: int = cv2.FONT_HERSHEY_SIMPLEX
    fontScale: int = 1
    thickness: int = 1
    color: Tuple[int, int, int] = (0, 0, 0)
    org: Tuple[int, int] = (0, 0)


class OpenCVisualizer(GUIVisualizer):
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

    def update(
        self,
        data: Union[np.ndarray, Iterable[np.ndarray], Dict[str, np.ndarray]],
        info: SampleInfo,
    ) -> None:
        """ "Show the data on the OpenCV window."""
        # TODO: add concatenation for the data
        if isinstance(data, np.ndarray):
            cv2.imshow(self.config.title, data)
        elif isinstance(data, dict):
            for key, value in data.items():
                if "color" in key:
                    cv2.imshow(f"{key}", value)
        else:
            for i, value in enumerate(data):
                cv2.imshow(f"{i}", value)
        if not self.config.ignore_info:
            image = self._put_info(self.info_image.copy(), info)
            cv2.imshow("info", image)
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
