from airbot_data_collection.common.visualiziers.opencv import (
    OpenCVisualizer,
    OpenCVisualizerConfig,
)


class AIRBOTBsonOpenCVisualizer(OpenCVisualizer):
    """Visualizer based on OpenCV."""

    config: OpenCVisualizerConfig

    def update(self, data, info):
        """Update the visualizer with new data and info."""
        image_data = {
            key: d["data"][..., ::-1] for key, d in data.items() if "color" in key
        }
        return super().update(image_data, info)
