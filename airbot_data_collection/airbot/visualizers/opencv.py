from airbot_data_collection.common.visualizers.opencv import (
    OpenCVisualizer,
    OpenCVisualizerConfig,
)


class AIRBOTOpenCVisualizer(OpenCVisualizer):
    """Visualizer based on OpenCV."""

    config: OpenCVisualizerConfig

    def update(self, data, info, warm_up: bool = False) -> bool:
        """Update the visualizer with new data and info."""
        return super().update(
            {key: d["data"] for key, d in data.items() if "color" in key}, info, warm_up
        )
