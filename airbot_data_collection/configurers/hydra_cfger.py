from hydra_zen import instantiate, store
from hydra.core import hydra_config
from hydra.utils import get_original_cwd
from hydra import main as hydra_main
from airbot_data_collection.configurers.basis import ConfigurerBasis, T
from airbot_data_collection.common.utils.utils import relative_path_between
from pathlib import Path
import argparse
import sys
import os


class Configurer(ConfigurerBasis[T]):
    """The configurer using Hydra as the backend."""

    def parse(self) -> None:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--config-path", "--path", default=None)
        parser.add_argument("--base-dir", default=os.getcwd())
        args, unknown = parser.parse_known_args()
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
        )(self.__set_config_dict)()

    def __set_config_dict(self, config_dict):
        self._config_dict = config_dict
        self.get_logger().info(f"Original working directory : {get_original_cwd()}")
        self.get_logger().info(
            f"Output directory  : {hydra_config.HydraConfig.get().runtime.output_dir}"
        )

    def on_configure(self) -> T:
        return self.config_class(**instantiate(self._config_dict))
