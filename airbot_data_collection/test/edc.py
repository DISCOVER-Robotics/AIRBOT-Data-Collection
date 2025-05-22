import av
import numpy as np
import io


def decode_jpeg_pyav(jpeg_bytes: bytes) -> np.ndarray:
    container = av.open(io.BytesIO(jpeg_bytes), format="jpeg_pipe")
    for frame in container.decode(video=0):
        # 返回第一个帧作为图像 (H x W x 3, RGB)
        return frame.to_ndarray(format="rgb24")
    raise ValueError("No frame could be decoded from the input JPEG bytes.")


def read_all_frames_pyav(video_path):
    container = av.open(video_path)
    frames = []
    for frame in container.decode(video=0):
        frames.append(frame.to_ndarray(format="rgb24"))
    container.close()
    return frames


if __name__ == "__main__":

    from PIL import Image

    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    decoded = decode_jpeg_pyav(jpeg_bytes)
    assert isinstance(decoded, np.ndarray)
    assert decoded.shape == (100, 100, 3)
    red_mean = decoded[:, :, 0].mean()
    green_mean = decoded[:, :, 1].mean()
    blue_mean = decoded[:, :, 2].mean()
    assert red_mean > 200 and green_mean < 50 and blue_mean < 50
    print("Test passed.")
