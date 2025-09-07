from airbot_data_collection.airbot.sensors.cameras.v4l2 import (
    V4L2CameraConcurrent,
    V4L2CameraConfig,
)


if __name__ == "__main__":
    from pprint import pprint
    import time

    v4l2 = V4L2CameraConcurrent(V4L2CameraConfig())
    if v4l2.configure():
        pprint(v4l2.get_info())
        for i in range(10):
            start = time.perf_counter()
            v4l2.capture_observation(0)
            obs = v4l2.result(5.0)
            for key, value in obs.items():
                print(
                    f"{i}: {key}: {value['t']}, {value['data'].shape}, {value['data'].dtype}"
                )
            print(f"Frame {i} took {(time.perf_counter() - start) * 1000:.3f} ms")
    v4l2.shutdown()
