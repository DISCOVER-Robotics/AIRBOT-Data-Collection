from typing import List
import numpy as np
from airbot_py.arm import AIRBOTPlay, RobotMode, SpeedProfile
from itertools import count
import time


def add_noise_to_position(position: list, mu: float, sigma: float) -> List[List[float]]:
    pos_arr = np.array(position)
    return (pos_arr + np.random.normal(mu, sigma, pos_arr.shape)).tolist()


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
        for i in range(100):
            cur_pose = play.get_end_pose()
            play.servo_cart_pose(
                [add_noise_to_position(cur_pose[0], 0.0, sigma), cur_pose[1]]
            )
            time.sleep(noise_interval)
            play.servo_cart_pose(target_pose)
            time.sleep(period)
            print(i)
        input("Press Enter to continue...")
        play.switch_mode(RobotMode.PLANNING_POS)
        play.move_to_joint_pos([0.0] * 6)
