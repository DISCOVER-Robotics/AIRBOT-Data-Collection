from hydra_zen import instantiate, store
from hydra.core import hydra_config
from hydra.utils import get_original_cwd
from hydra import main as hydra_main
from pathlib import Path
from omegaconf import DictConfig, OmegaConf
from airbot_data_collection.configurers.basis import ConfigurerBasis, T
from airbot_data_collection.common.utils.utils import relative_path_between
import argparse
import sys
import os


class Configurer(ConfigurerBasis[T]):
    """The configurer using Hydra as the backend."""

    def parse(self) -> None:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--config-path", "--path", default=None)
        parser.add_argument("--base-dir", default=os.getcwd())
        parser.add_argument("--show-resolved", "-sr", action="store_true")
        args, unknown = parser.parse_known_args()
        self._show_resolved = args.show_resolved
        sys.argv = sys.argv[:1] + unknown
        config_name = "class_config"
        store(self.config_class, name=config_name)
        store.add_to_hydra_store()
        base_dir = self._main_dir if args.base_dir == "__main__" else args.base_dir
        ori_config_path = Path(args.config_path)
        if ori_config_path.suffix == ".yaml":
            config_dir = ori_config_path.parent
            config_name = ori_config_path.stem
        else:
            config_dir = ori_config_path
        config_path = relative_path_between(
            Path(base_dir).absolute() / config_dir,
            Path(__file__).absolute().parent,
        )
        self.get_logger().info(f"Config path: {config_path.absolute()}")
        self.get_logger().info(f"Base dir: {base_dir}")
        return hydra_main(
            str(config_path),
            config_name,
            None,
        )(self.__set_dict_config)()

    @classmethod
    def merge_dicts(cls, base: dict, overrides: dict):
        merged = OmegaConf.merge(base, overrides)
        cls.get_logger().info(f"Merged config:\n{OmegaConf.to_yaml(merged)}")
        return merged

    def __set_dict_config(self, dict_config: DictConfig) -> None:
        self._dict_config = dict_config
        self.get_logger().info(f"Original working directory : {get_original_cwd()}")
        self.get_logger().info(
            f"Output directory  : {hydra_config.HydraConfig.get().runtime.output_dir}"
        )
        if self._show_resolved:
            OmegaConf.resolve(dict_config)
            print(OmegaConf.to_yaml(dict_config))
            exit(0)

    def on_configure(self) -> T:
        dict_config: DictConfig = instantiate(self._dict_config)
        instance = self.config_class(**dict_config)
        return instance


OmegaConf.register_new_resolver("merge_cfg", Configurer.merge_dicts)
