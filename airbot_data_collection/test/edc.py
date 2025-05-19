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
    # 遍历视频流中的每一帧
    for frame in container.decode(video=0):
        # 将帧转换为 numpy 数组 (RGB 格式)
        frames.append(frame.to_ndarray(format="rgb24"))
    container.close()
    return frames


# # 使用示例
# video_path = "/home/ghz/视频/test.mp4"
# all_frames = read_all_frames_pyav(video_path)
# print(f"共读取 {len(all_frames)} 帧")


def test_decode_jpeg():
    from PIL import Image

    # 创建一个简单的 RGB 图像（红色 100x100）
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    # 使用 PyAV 解码
    decoded = decode_jpeg_pyav(jpeg_bytes)

    assert isinstance(decoded, np.ndarray)
    assert decoded.shape == (100, 100, 3)
    # 检查是否大致是红色（由于 JPEG 是有损压缩，不能期望精确）
    red_mean = decoded[:, :, 0].mean()
    green_mean = decoded[:, :, 1].mean()
    blue_mean = decoded[:, :, 2].mean()
    assert red_mean > 200 and green_mean < 50 and blue_mean < 50
    print("Test passed.")


# 运行测试
test_decode_jpeg()
