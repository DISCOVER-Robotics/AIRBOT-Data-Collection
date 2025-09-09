from multiprocessing.managers import SharedMemoryManager
from multiprocessing import get_context, current_process
from multiprocessing.connection import Connection
from multiprocessing.sharedctypes import Synchronized
from pydantic import BaseModel, ConfigDict
from typing import Union, Dict, Type, Optional
from airbot_data_collection.basis import Sensor, System
from airbot_data_collection.basis import ConcurrentMode
from airbot_data_collection.common.utils.event_rpc import (
    EventRpcManager,
    EventRpcServer,
)
from airbot_data_collection.utils import init_logging
from airbot_data_collection.common.utils.shareable_numpy import ShareableNumpy
from airbot_data_collection.common.utils.shareable_value import ShareableValue
from numpy import uint64
from setproctitle import setproctitle


class ConcurrentWrapperConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    interface: Union[Sensor, System]
    mode: ConcurrentMode = ConcurrentMode.process


class SensorConcurrentWrapper(Sensor):
    """A wrapper for sensors to run in a separate thread or process."""

    config: ConcurrentWrapperConfig

    def on_configure(self) -> bool:
        # TODO: use protocol instead of inheriting Sensor?
        if self.config.mode is not ConcurrentMode.process:
            raise NotImplementedError(
                "Only process mode is supported for SensorConcurrentWrapper."
            )
        self._rpc = EventRpcManager(EventRpcManager.get_args(self.config.mode))
        spawn_ctx = get_context("spawn")
        parent, child = spawn_ctx.Pipe()
        self._smm = SharedMemoryManager(ctx=spawn_ctx)
        self._smm.start()
        self._concurrent = EventRpcManager.get_concurrent_cls(self.config.mode)(
            target=self._concurrent_loop,
            args=(self.config.interface, child, self._rpc.server),
            name=f"{self.__class__.__name__}Concurrent",
        )
        self._concurrent.start()
        if parent.poll(5.0):
            if parent.recv():
                self.get_logger().info("Receiving info and first observation...")
                if parent.poll(5.0):
                    self._info, obs = parent.recv()
                    self._obs: Dict[
                        str, Dict[str, Union[ShareableNumpy, Synchronized]]
                    ] = {}
                    obs: dict
                    for key, value in obs.items():
                        self._obs[key] = {
                            # "t": spawn_ctx.Value("Q", value["t"], lock=True),
                            "t": ShareableValue.from_value(
                                value["t"], uint64, smm=self._smm
                            ),
                            "data": ShareableNumpy.from_array(
                                value["data"], smm=self._smm
                            ),
                        }
                    self.get_logger().info("Sending shm observation...")
                    parent.send(self._obs)
                    parent.close()
                    return True
            else:
                self.get_logger().error("Failed to configure the interface.")
        else:
            self.get_logger().error("Timeout waiting for configure response.")
        return False

    @staticmethod
    def _concurrent_loop(
        interface: Sensor, conn: Connection, rpc_server: EventRpcServer
    ):
        init_logging()
        logger = interface.get_logger()
        logger.info("Configuring the interface...")
        setproctitle(f"{current_process().name}:{logger.name}")
        conn.send(interface.configure())
        conn.send((interface.get_info(), interface.capture_observation(5.0)))
        if not conn.poll(5.0):
            logger.error("Timeout waiting for shm observation.")
            return
        shm_obs = conn.recv()
        conn.close()
        while rpc_server.wait():
            for key, value in interface.capture_observation(5.0).items():
                shm_obs[key]["t"].value = value["t"]
                shm_obs[key]["data"][:] = value["data"]
            rpc_server.respond()
        logger.info("Shutting down the interface...")
        interface.shutdown()

    def _get_obs(self):
        return {
            key: {"t": value["t"].value, "data": value["data"].array}
            for key, value in self._obs.items()
        }

    def capture_observation(self, timeout: Optional[float] = None):
        if self._rpc.client.request(timeout=timeout):
            if timeout is not None and timeout <= 0:
                return None
            return self._get_obs()
        raise TimeoutError("Timeout waiting for observation.")

    def result(self, timeout: Optional[float] = None):
        if timeout is None or timeout > 0:
            if self._rpc.client.wait(timeout=timeout):
                return self._get_obs()
            raise TimeoutError("Timeout waiting for observation.")
        raise ValueError("Timeout must be None or positive.")

    def get_info(self):
        return self._info

    def shutdown(self):
        self._rpc.shutdown()
        self._concurrent.join(timeout=5.0)
        self._smm.shutdown()
        if self._concurrent.is_alive():
            self.get_logger().warning("Concurrent process did not terminate in time.")
        return True


def concurrent_wrapper(
    interface_cls: Type[Sensor], config_cls: Optional[Type[BaseModel]] = None
):
    class ConcurrentWrappedClass(SensorConcurrentWrapper):
        def __init__(
            self,
            config: Optional[BaseModel] = None,
            _concurrent=ConcurrentMode.process,
            **kwargs,
        ):
            super().__init__(
                ConcurrentWrapperConfig(
                    interface=interface_cls(config=config or config_cls, **kwargs),
                    mode=_concurrent,
                )
            )

    return ConcurrentWrappedClass


if __name__ == "__main__":
    from airbot_data_collection.airbot.sensors.cameras.mock import (
        MockCamera,
        MockCameraConfig,
    )
    import cv2
    import time

    init_logging()
    # con_mock_cam = SensorConcurrentWrapper(
    #     ConcurrentWrapperConfig(
    #         interface=MockCamera(MockCameraConfig()), mode=ConcurrentMode.process
    #     )
    # )
    # con_mock_cam = concurrent_wrapper(MockCamera)(
    #     MockCameraConfig(random=True), concurrent=ConcurrentMode.process
    # )
    con_mock_cam = concurrent_wrapper(MockCamera, MockCameraConfig)(
        _concurrent=ConcurrentMode.process, random=True
    )
    assert con_mock_cam.configure()
    con_mock_cam.get_logger().info("Successfully configured")
    for i in range(10):
        start = time.perf_counter()
        obs = con_mock_cam.capture_observation()
        print(f"{(time.perf_counter() - start) * 1000:.3} ms")
        for key, value in obs.items():
            print(key, value["t"])
            cv2.imshow(key, value["data"])
            cv2.waitKey(1)

    cv2.destroyAllWindows()
    con_mock_cam.shutdown()
