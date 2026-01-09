import tempfile
import numpy as np
import unittest
from pathlib import Path
from hydra.utils import instantiate
from omegaconf import OmegaConf
from collections import defaultdict
from time import time_ns


def _get_cfg_path() -> Path:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cfg",
        type=str,
        default="tests/modules/samplers/mock_sampler.yaml",
        help="Path to the configuration file.",
    )
    args, unknown = parser.parse_known_args()
    return Path(args.cfg)


def _make_payload() -> dict:
    stamp = time_ns()
    payload = {
        "/left/follow/arm/joint_state/position": {
            "data": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "t": stamp,
        },
        "/left/follow/eef/joint_state/position": {
            "data": [0.042676811087298046],
            "t": stamp + 1000,
        },
        "/left/lead/arm/joint_state/position": {
            "data": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "t": stamp + 2000,
        },
        "/left/lead/eef/joint_state/position": {
            "data": [0.038898526876328846],
            "t": stamp + 3000,
        },
        "/right/follow/arm/joint_state/position": {
            "data": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "t": stamp + 4000,
        },
        "/right/follow/eef/joint_state/position": {
            "data": [0.04263859970960877],
            "t": stamp + 5000,
        },
        "/right/lead/arm/joint_state/position": {
            "data": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "t": stamp + 6000,
        },
        "/right/lead/eef/joint_state/position": {
            "data": [0.010088901680831866],
            "t": stamp + 7000,
        },
        # RGB/Depth mock frames (common shape conventions)
        "/camera/rgb": {
            "data": np.zeros((8, 8, 3), dtype=np.uint8),
            "t": stamp + 8000,
        },
        "/camera/depth": {
            "data": np.zeros((8, 8), dtype=np.uint16),
            "t": stamp + 9000,
        },
    }
    return payload


class TestDataSampler(unittest.TestCase):
    def test_instantiate_and_contract(self):
        cfg_path = _get_cfg_path()
        cfg = OmegaConf.load(cfg_path)
        from airdc.common.samplers.basis import DataSampler

        sampler: DataSampler = instantiate(cfg)
        self.assertIsInstance(sampler, DataSampler)
        sampler.set_info({})
        # ConfigurableBasis contract: should be configurable.
        self.assertTrue(sampler.configure())

        with tempfile.TemporaryDirectory(prefix="airdc-test-sampler-") as tmp:
            data_dir = Path(tmp)
            for cur_round in range(2):
                path = sampler.compose_path(data_dir, cur_round)
                self.assertIsInstance(path, Path)

                round_data = defaultdict(list)
                for _ in range(2):
                    payload = _make_payload()
                    updated = sampler.update(payload)
                    self.assertIsInstance(updated, dict)
                    for key, value in updated.items():
                        round_data[key].append(value)

                self.assertTrue(sampler.save(path, round_data))
                self.assertIn(sampler.remove(path), [True, None])

                # Ensure clear/shutdown hooks don't raise.
                sampler.clear()

        sampler.shutdown()


if __name__ == "__main__":
    unittest.main()
