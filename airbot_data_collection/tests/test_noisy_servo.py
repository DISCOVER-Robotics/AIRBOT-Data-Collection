from typing import List
import numpy as np
from airbot_py.arm import AIRBOTPlay, RobotMode, SpeedProfile
import time


def add_gs_noise(position: list, mu: float, sigma: float) -> List[List[float]]:
    pos_arr = np.array(position)
    return (pos_arr + np.random.normal(mu, sigma, pos_arr.shape)).tolist()


def add_impulse_noise(
    data: list, prob: float, scale_min: float, scale_max: float
) -> List[float]:
    data_arr: np.ndarray = np.array(data)
    noise_mask = np.random.rand(*data_arr.shape) < prob
    if not np.any(noise_mask):
        return data
    impulse_values = np.random.uniform(scale_min, scale_max, size=data_arr.shape)
    data_arr[noise_mask] = impulse_values[noise_mask]
    return data_arr.tolist()


if __name__ == "__main__":
    freq = 20
    period = 1 / freq
    noise_interval = 0.05
    sigma = 0.01
    target_pose = [
        [
            0.15773574091781126,
            -0.0010935813145392297,
            0.2291495893485753,
        ],
        [
            0.6126003688688748,
            -0.3932126654650998,
            -0.4917124129233684,
            -0.47783207380483467,
        ],
    ]

    play = AIRBOTPlay(port=50051)

    with play as play:
        play.set_speed_profile(SpeedProfile.FAST)
        play.switch_mode(RobotMode.SERVO_CART_POSE)

        print("current pose", play.get_end_pose())
        noise_value = 0.05
        noise_prob = 0.2
        for i in range(100):
            cur_pose = play.get_end_pose()
            noise_data = add_impulse_noise(
                cur_pose[0], noise_prob, -noise_value, noise_value
            )
            play.servo_cart_pose([noise_data, cur_pose[1]])
            # play.servo_cart_pose([add_gs_noise(cur_pose[0], 0.0, sigma), cur_pose[1]])
            time.sleep(noise_interval)
            play.servo_cart_pose(target_pose)
            time.sleep(period)
            print(i)
        input("Press Enter to continue...")
        play.switch_mode(RobotMode.PLANNING_POS)
        play.move_to_joint_pos([0.0] * 6)
