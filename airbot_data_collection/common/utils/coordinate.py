import math
from typing import List, Tuple


class CoordinateConverter:
    """坐标系转换类：将左手坐标系(Z前)转换为右手坐标系(X前,Y左,Z上)"""

    @staticmethod
    def normalize_quaternion(x, y, z, w):
        """归一化四元数"""
        magnitude = math.sqrt(x * x + y * y + z * z + w * w)
        if magnitude < 1e-10:
            return [0.0, 0.0, 0.0, 1.0]
        return [x / magnitude, y / magnitude, z / magnitude, w / magnitude]

    @staticmethod
    def quaternion_to_axis_angle(q):
        """四元数转换为轴角表示"""
        # 确保四元数是单位长度
        q = CoordinateConverter.normalize_quaternion(q[0], q[1], q[2], q[3])

        # 提取旋转角度
        angle = 2 * math.acos(q[3])

        # 如果角度接近0，轴可以是任意的，默认为z轴
        if math.isclose(angle, 0.0, abs_tol=1e-10):
            return [0.0, 0.0, 1.0, 0.0]

        # 提取并归一化旋转轴
        s = math.sqrt(1 - q[3] * q[3])
        if s < 1e-10:
            # 避免除以接近零的数
            axis = [1.0, 0.0, 0.0]
        else:
            axis = [q[0] / s, q[1] / s, q[2] / s]

        return [*axis, angle]

    @staticmethod
    def axis_angle_to_quaternion(axis, angle):
        """轴角表示转换为四元数"""
        # 归一化轴
        magnitude = math.sqrt(sum(x * x for x in axis))
        if magnitude < 1e-10:
            return [0.0, 0.0, 0.0, 1.0]  # 单位四元数表示无旋转

        normalized_axis = [x / magnitude for x in axis]

        # 创建四元数
        half_angle = angle / 2
        sin_half = math.sin(half_angle)

        q = [
            normalized_axis[0] * sin_half,
            normalized_axis[1] * sin_half,
            normalized_axis[2] * sin_half,
            math.cos(half_angle),
        ]

        return q

    @staticmethod
    def convert_left_to_right_handed(
        position, rotation
    ) -> Tuple[List[float], List[float]]:
        """
        将左手坐标系(Z前)转换为右手坐标系(X前,Y左,Z上)
        参数:
            position: [x, y, z] 原始左手坐标系位置
            rotation: [x, y, z, w] 原始左手坐标系四元数
        返回:
            transformed_position: [x, y, z] 转换后的右手坐标系位置
            transformed_rotation: [x, y, z, w] 转换后的右手坐标系四元数
        """
        # 位置转换: (X, Y, Z) -> (Z, -X, Y)
        transformed_position = [
            position[2],  # 新X = 原Z (前向)
            -position[0],  # 新Y = -原X (左向)
            position[1],  # 新Z = 原Y (上向)
        ]

        # 从原始四元数中提取旋转的轴和角度
        original_axis_angle = CoordinateConverter.quaternion_to_axis_angle(rotation)

        # 根据坐标系变换规则，调整旋转轴
        # 原坐标系: X右, Y上, Z前 -> 新坐标系: X前, Y左, Z上
        original_axis = original_axis_angle[0:3]
        angle = original_axis_angle[3]

        # 转换旋转轴: (X, Y, Z) -> (Z, -X, Y)
        transformed_axis = [
            original_axis[2],  # 新X = 原Z
            -original_axis[0],  # 新Y = -原X
            original_axis[1],  # 新Z = 原Y
        ]

        # 从转换后的轴和角度创建新的四元数
        # 由于从左手系到右手系的转换，需要反转旋转方向（取反角度）
        transformed_rotation = CoordinateConverter.axis_angle_to_quaternion(
            transformed_axis, -angle
        )

        # 归一化
        transformed_rotation = CoordinateConverter.normalize_quaternion(
            *transformed_rotation
        )

        return transformed_position, transformed_rotation
