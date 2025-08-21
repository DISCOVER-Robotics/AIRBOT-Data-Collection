import flatbuffers
import numpy as np
from foxglove_schemas_flatbuffer import RawImage


def numpy_to_rawimage(img: np.ndarray, encoding="rgb8", frame_id="camera"):
    height, width = img.shape[:2]
    step = img.strides[0]  # 一行字节数

    builder = flatbuffers.Builder(1024)

    # 转换字符串
    frame_id_offset = builder.CreateString(frame_id)
    encoding_offset = builder.CreateString(encoding)

    # 转换图像数据（numpy -> bytes）
    data_bytes = img.tobytes()

    data_vec = builder.CreateByteVector(data_bytes)
    # 构建 RawImage
    RawImage.Start(builder)
    RawImage.AddFrameId(builder, frame_id_offset)
    RawImage.AddWidth(builder, width)
    RawImage.AddHeight(builder, height)
    RawImage.AddEncoding(builder, encoding_offset)
    RawImage.AddStep(builder, step)
    RawImage.AddData(builder, data_vec)
    rawimage = RawImage.End(builder)

    builder.Finish(rawimage)

    return builder.Output()


def rawimage_to_numpy(raw_img: RawImage.RawImage):
    """
    将 RawImage flatbuffer 对象解码成 numpy 数组
    """
    width = raw_img.Width()
    height = raw_img.Height()
    step = raw_img.Step()
    encoding = raw_img.Encoding().decode("utf-8")

    data = raw_img.DataAsNumpy()  # 1D uint8 数组

    # 根据 encoding 选择 dtype 和通道数
    if encoding in ("rgb8", "bgr8", "8UC3"):
        channels = 3
        dtype = np.uint8
    elif encoding in ("rgba8", "bgra8"):
        channels = 4
        dtype = np.uint8
    elif encoding in ("mono8", "8UC1"):
        channels = 1
        dtype = np.uint8
    elif encoding in ("mono16", "16UC1"):
        channels = 1
        dtype = np.uint16
    elif encoding == "32FC1":
        channels = 1
        dtype = np.float32
    else:
        raise ValueError(f"Unsupported encoding: {encoding}")

    # 重新解释为 dtype
    arr = data.view(dtype)

    # 按 step 重构二维/三维数组
    if channels == 1:
        img = arr.reshape((height, step // arr.itemsize))[:, :width]
    else:
        cal_width = step // (channels * arr.itemsize)
        assert cal_width == width, (
            f"Calculated width {cal_width} does not match expected width {width}"
        )
        img = arr.reshape((height, cal_width, channels))[:, :width, :]
    return img


from airbot_data_collection.common.devices.cameras.intelrealsense import (
    IntelRealSenseCamera,
    IntelRealSenseCameraConfig,
)

rs = IntelRealSenseCamera(
    IntelRealSenseCameraConfig(enable_depth=True, align_depth=True)
)

assert rs.configure()

color, depth = rs.capture_observation()
print(color.shape, depth.shape)
print(color.dtype, depth.dtype)


enc_mapping = {
    1: {
        np.uint8: "8UC1",
        np.uint16: "16UC1",
        np.float32: "32FC1",
    },
    3: {
        np.uint8: "8UC3",
    },
}

img = color
# img = np.zeros((480, 848, 3), dtype=np.uint8)
channels = 1 if len(img.shape) == 2 else 3
print(channels)
encoding = enc_mapping[channels][img.dtype.type]
print(encoding)
buf = numpy_to_rawimage(img, encoding=encoding)

# 解析回 RawImage
raw_img = RawImage.RawImage.GetRootAs(buf, 0)

print("Width:", raw_img.Width())
print("Height:", raw_img.Height())
print("Encoding:", raw_img.Encoding())
print("Step:", raw_img.Step())
print("Data size:", raw_img.DataLength())

img_arr = rawimage_to_numpy(raw_img)

import cv2

print(img_arr.shape)

cv2.imshow("Raw image", img)
cv2.imshow("Converted image", img_arr)
cv2.waitKey(0)

assert rs.shutdown()
