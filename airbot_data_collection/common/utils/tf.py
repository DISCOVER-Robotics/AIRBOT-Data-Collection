from airbot_data_collection.common.utils.transformations import (
    compose_matrix,
    euler_from_quaternion,
    quaternion_from_matrix,
    translation_from_matrix,
)
from functools import wraps
from typing import Sequence, Tuple, List
import numpy as np


def pose2matrix(position: Sequence[float], orientation: Sequence[float]) -> np.ndarray:
    """Convert position and orientation to a 4x4 transformation matrix.

    Args:
        position (list or np.ndarray): A list or array of 3 elements representing the position (x, y, z).
        orientation (list or np.ndarray): A list or array of 4 elements representing the orientation as a quaternion (x, y, z, w).

    Returns:
        np.ndarray: A 4x4 transformation matrix.
    """
    return compose_matrix(translate=position, angles=euler_from_quaternion(orientation))


def matrix2pose(matrix: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    """Convert a 4x4 transformation matrix to position and orientation.

    Args:
        matrix (np.ndarray): A 4x4 transformation matrix.
    Returns:
        tuple: A tuple containing:
            - position (np.ndarray): A 1D array of 3 elements representing the position
            - orientation (np.ndarray): A 1D array of 4 elements representing the orientation as a quaternion (x, y, z, w).
    """
    position = translation_from_matrix(matrix)
    orientation = quaternion_from_matrix(matrix)
    return position, orientation


def tf_between_poses(
    position_a: Sequence[float],
    orientation_a: Sequence[float],
    position_b: Sequence[float],
    orientation_b: Sequence[float],
) -> np.ndarray:
    """Compute the transformation matrix from pose A to pose B.

    Args:
        position_a (list or np.ndarray): Position of pose A (x, y, z).
        orientation_a (list or np.ndarray): Orientation of pose A as a quaternion (x, y, z, w).
        position_b (list or np.ndarray): Position of pose B (x, y, z).
        orientation_b (list or np.ndarray): Orientation of pose B as a quaternion (x, y, z, w).

    Returns:
        np.ndarray: A 4x4 transformation matrix representing the transformation from pose A to pose B.
    """
    matrix_a = pose2matrix(position_a, orientation_a)
    matrix_b = pose2matrix(position_b, orientation_b)
    matrix_a_inv = np.linalg.inv(matrix_a)
    tf_matrix = np.dot(matrix_a_inv, matrix_b)
    return tf_matrix


def apply_tf_to_pose(
    position: Sequence[float], orientation: Sequence[float], tf_matrix: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Apply a transformation matrix to a pose.

    Args:
        position (np.ndarray): A 1D array of 3 elements representing the position (x, y, z).
        orientation (np.ndarray): A 1D array of 4 elements representing the orientation as a quaternion (x, y, z, w).
        tf_matrix (np.ndarray): A 4x4 transformation matrix to be applied.

    Returns:
        tuple: A tuple containing:
            - new_position (np.ndarray): A 1D array of 3 elements representing the new position.
            - new_orientation (np.ndarray): A 1D array of 4 elements representing the new orientation as a quaternion (x, y, z, w).
    """
    pose_matrix = pose2matrix(position, orientation)
    new_pose_matrix = np.dot(pose_matrix, tf_matrix)
    new_position, new_orientation = matrix2pose(new_pose_matrix)
    return new_position, new_orientation


def apply_rela_pose_to_pose(
    position: Sequence[float],
    orientation: Sequence[float],
    rela_position: Sequence[float],
    rela_orientation: Sequence[float],
) -> Tuple[np.ndarray, np.ndarray]:
    """Apply a relative pose to a pose.

    Args:
        position (np.ndarray): A 1D array of 3 elements representing the position (x, y, z).
        orientation (np.ndarray): A 1D array of 4 elements representing the orientation as a quaternion (x, y, z, w).
        rela_position (np.ndarray): A 1D array of 3 elements representing the relative position (x, y, z).
        rela_orientation (np.ndarray): A 1D array of 4 elements representing the relative orientation as a quaternion (x, y, z, w).

    Returns:
        tuple: A tuple containing:
            - new_position (np.ndarray): A 1D array of 3 elements representing the new position.
            - new_orientation (np.ndarray): A 1D array of 4 elements representing the new orientation as a quaternion (x, y, z, w).
    """
    rela_pose_matrix = pose2matrix(rela_position, rela_orientation)
    return apply_tf_to_pose(position, orientation, rela_pose_matrix)


def array_pose_to_list(
    position: np.ndarray, orientation: np.ndarray
) -> Tuple[List[float], List[float]]:
    """Convert position and orientation arrays to a single list.

    Args:
        position (np.ndarray): A 1D array of 3 elements representing the position (x, y, z).
        orientation (np.ndarray): A 1D array of 4 elements representing the orientation as a quaternion (x, y, z, w).

    Returns:
        list: A list containing the position and orientation elements.
    """
    return position.tolist(), orientation.tolist()


def array_pose_to_list_wrapper(func, **p_kwargs):
    """A decorator to convert array pose outputs of a function to list pose."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        return array_pose_to_list(*func(*args, **kwargs, **p_kwargs))

    return wrapper


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test functions for pose and transformation matrix conversions."
    )
    args = parser.parse_args()

    pos_a = [0.5, 0.0, 0.5]
    qat_a = [0.0, 0.0, 0.0, 1.0]
    pos_b = [0.5, 0.5, 0.5]
    qat_b = [0.0, 0.0, 0.7071, 0.7071]

    tf_ab = tf_between_poses(pos_a, qat_a, pos_b, qat_b)
    new_pos_b, new_qat_b = apply_tf_to_pose(pos_a, qat_a, tf_ab)
    new_pos_b_list, new_qat_b_list = array_pose_to_list_wrapper(
        apply_tf_to_pose, tf_matrix=tf_ab
    )(new_pos_b, new_qat_b)

    assert np.allclose(new_pos_b, pos_b)
    assert np.allclose(new_qat_b, qat_b)

    rela_pose_b = matrix2pose(tf_ab)
    assert np.allclose(pose2matrix(*rela_pose_b), tf_ab)

    new_pos_b2, new_qat_b2 = apply_rela_pose_to_pose(pos_a, qat_a, *rela_pose_b)
    assert np.allclose(new_pos_b2, pos_b)
    assert np.allclose(new_qat_b2, qat_b)

    print("All tests passed.")
