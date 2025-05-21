from airbot_data_collection.common.visualiziers.opencv import (
    OpenCVisualizer,
    OpenCVisualizerConfig,
)


class AIRBOTBsonOpenCVisualizer(OpenCVisualizer):
    """Visualizer based on OpenCV."""

    config: OpenCVisualizerConfig

    def update(self, data, info) -> bool:
        """Update the visualizer with new data and info."""
        if self.config.swap_rgb_bgr:
            image_data = {
                key: d["data"][..., ::-1] for key, d in data.items() if "color" in key
            }
        else:
            image_data = {key: d["data"] for key, d in data.items() if "color" in key}
        return super().update(image_data, info)
