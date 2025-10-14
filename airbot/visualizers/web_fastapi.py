from airbot_data_collection.common.visualizers.web_fastapi import (
    FastAPIVisualizer,
    WebVisualizerConfig,
)


class AIRBOTFastAPIVisualizer(FastAPIVisualizer):
    """Visualizer based on fastapi."""

    config: WebVisualizerConfig

    def update(self, data: dict, info):
        """Update the visualizer with new data and info."""
        image_data = {key: d["data"] for key, d in data.items() if "color" in key}
        return super().update(image_data, info)
