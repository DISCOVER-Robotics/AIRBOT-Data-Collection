from airbot_data_collection.common.visualiziers.basis import (
    VisualizerBasis,
    GUIVisualizerConfig,
    SampleInfo,
)
import numpy as np
from typing import Union, Iterable, Dict, Tuple
from pydantic import BaseModel
import logging
import matplotlib.pyplot as plt


class PltVisualizer(VisualizerBasis):
    config: GUIVisualizerConfig

    def on_configure(self) -> bool:
        plt.ion()
        self._displays = {}
        return True

    def update(self, data: Dict[str, np.ndarray], info: SampleInfo) -> bool:
        if not self._displays:
            img_num = len(data)
            if img_num == 1:
                pass
            elif img_num
            fig, axes = plt.subplots(self.config, 2, figsize=(12, 10))
            axes = axes.flatten()  # 将2D数组展平为1D，便于索引
            for key, image in data.items():
                self._displays

        
        return True