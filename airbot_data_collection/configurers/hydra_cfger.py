from hydra_zen import instantiate, store
from pathlib import Path
from omegaconf import DictConfig, OmegaConf
from airbot_data_collection.configurers.basis import ConfigurerBasis, T
from airbot_data_collection.common.utils.utils import relative_path_between
from hydra.core import hydra_config
import hydra
import argparse
import sys


class Configurer(ConfigurerBasis[T]):
    """The configurer using Hydra as the backend."""

    def parse(self) -> None:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--config-path", "--path", default=None)
        parser.add_argument(
            "--base-dir",
            default=str(Path.cwd()),
            help="The base directory for config path."
            "__main__ for main file directory. Default to the current working directory.",
        )
        parser.add_argument(
            "--cfger-help", action="store_true", help="Show this help message"
        )
        parser.add_argument(
            "--add-cwd-mode",
            type=str,
            default="append",
            choices=["prepend", "append", "none"],
            help="Whether to add the current working directory to sys.path, and where to add it",
        )
        parser.add_argument(
            "--show-resolved",
            "-sr",
            action="store_true",
            help="Show the resolved config and exit",
        )
        args, unknown = parser.parse_known_args()
        self._show_resolved = args.show_resolved
        sys.argv = sys.argv[:1] + unknown
        config_name = "class_config"
        store(self.config_class, name=config_name)
        store.add_to_hydra_store()
        config_path = args.config_path
        if config_path is not None:
            base_dir = self._main_dir if args.base_dir == "__main__" else args.base_dir
            ori_config_path = Path(args.config_path)
            if ori_config_path.suffix == ".yaml":
                config_dir = ori_config_path.parent
                config_name = ori_config_path.stem
            else:
                config_dir = ori_config_path
            if not config_dir.is_absolute():
                config_dir = Path(base_dir).absolute() / config_dir
            if not config_dir.exists():
                raise FileNotFoundError(f"{config_dir} not found")
            config_path = relative_path_between(
                config_dir,
                Path(__file__).absolute().parent,
            )
            print(f"Base dir: {base_dir}")
            config_path = str(config_path)
        self._dict_config = None
        add_cwd_mode = args.add_cwd_mode
        cwd = str(Path.cwd().absolute())
        if add_cwd_mode == "prepend":
            sys.path.insert(0, cwd)
        elif add_cwd_mode == "append":
            sys.path.append(cwd)
        hydra.main(config_path, config_name, None)(self.__set_dict_config)()
        sys.path.pop()
        if self._dict_config is None:
            exit(0)

    @classmethod
    def merge_dicts(cls, base: dict, overrides: dict):
        merged = OmegaConf.merge(base, overrides)
        # cls.get_logger().info(f"Merged config:\n{OmegaConf.to_yaml(merged)}")
        return merged

    def __set_dict_config(self, dict_config: DictConfig) -> None:
        self._dict_config = dict_config
        self.get_logger().info(
            f"Original working directory : {hydra.utils.get_original_cwd()}"
        )
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


if __name__ == "__main__":
    from pydantic import BaseModel

    class DataCollectionArgs(BaseModel):
        option: str = "foo"

    configurer = Configurer(
        DataCollectionArgs,
    )
    configurer.parse()
    assert configurer.configure()
