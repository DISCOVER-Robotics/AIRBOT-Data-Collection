from transitions import Machine
from pynput import keyboard
from pathlib import Path
from PIL import Image
import numpy as np
import copy
import os
import concurrent.futures
import json
import shutil
import cv2
import queue
import threading
from PIL import Image
import traceback


# Monkey patch，自动忽略非法参数 like preset
_original_save = Image.Image.save


def safe_save(self, fp, format=None, **params):
    if "preset" in params:
        print("Found 'preset' in save() call — printing call stack:")
        traceback.print_stack()
        del params["preset"]
    return _original_save(self, fp, format=format, **params)


Image.Image.save = safe_save


class DataFileManager:
    """Manages the file operations related to the data collection task.

    The class is responsible for managing data format processing and storage during the
    data collection process. Such as creating directories, managing cache for images and
    low-dimensional data, and organizing the data based on the provided task name and root path.
    It also maintains the state for each task, including the current episode, camera
    settings, and the associated timestamps.

    Attributes:
        task_path (Path): The path to the directory for the current task.
        num_image_writers_per_camera (int): The number of image writers per camera.
        cam_cache (list): A cache for storing camera information.
        current_episode (int): The current episode number.
        low_dim (dict): A dictionary for low-dimensional data.
        images_timestamp (dict): A dictionary for timestamps of images.
        low_dim_timestamps (dict): A dictionary for timestamps of low-dimensional data.
        low_dim_keys (dict): A dictionary for keys of low-dimensional data.
        low_dim_time_keys (dict): A dictionary for time-based keys of low-dimensional data.
        cameras_keys (dict): A dictionary for camera keys.
        dicts_cache (list): A cache for storing dictionaries.
        joint_num (int): The number of joints.
    """

    def __init__(self, root_path: Path, task_name: str) -> None:
        """Initializes a new instance of the DataFileManager class.

        This method sets up the task path by combining the provided root path
        and task name. It also creates the necessary directories if they do not
        already exist. Several internal caches and state variables are initialized.

        Args:
            root_path (Path): The root directory where task files will be stored.
            task_name (str): The name of the task which will be used to create a
                             subdirectory under the root path.

        Returns:
            None: This function does not return any value.
        """
        self.task_path = Path(root_path) / task_name
        if not os.path.exists(self.task_path):
            os.makedirs(self.task_path)
        self.num_image_writers_per_camera = 2

        self.cam_cache = []
        self.current_episode = 0
        self.low_dim = {}
        self.images_timestamp = {}
        self.low_dim_timestamps = {}
        self.low_dim_keys = {}
        self.low_dim_time_keys = {}
        self.cameras_keys = {}
        self.dicts_cache = []
        self.joint_num = 6

    def save_image(img: np.ndarray, frame_index: int, images_dir: Path) -> None:
        """Saves the given image as a PNG file.

        Args:
            img (np.ndarray): The image to be saved, in numpy array format.
            frame_index (int): The index of the current frame, used to generate the file name.
            images_dir (Path): The directory where the image will be saved.

        Returns:
            None: This function does not return any value.

        This function saves the image as a PNG file in the specified directory with a filename
        based on the frame index (e.g., frame_000001.png). The function also ensures that the
        necessary parent directories are created if they do not already exist.
        """
        img = Image.fromarray(img)
        path = images_dir / f"frame_{frame_index:06d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), quality=100)

    def init_keys(self, observation, camera_keys) -> None:
        """Initializes various keys used for accessing data in the observation.

        Args:
            observation (dict): A dictionary containing the observation data, including keys for
                                low-dimensional data, images, and camera settings.
            camera_keys (list): A list of keys representing the cameras.

        Returns:
            None: This function does not return any value.

        This function initializes keys for low-dimensional data, camera settings, and image data
        based on the provided observation. It also determines the number of leader and follower
        robots based on the joint position data, and loads a template dictionary from a JSON file
        depending on the number of leaders. Finally, it checks the current episode and increments
        it to avoid name conflicts when saving data.
        """
        self.low_dim_keys = list(observation["low_dim"].keys())
        self.low_dim_time_keys = [
            key for key in observation["low_dim"] if "time" in key
        ]
        # TODO : get cameras keys
        self.cameras_keys = camera_keys  # robot.cameras
        self.image_keys = [key for key in observation if "image" in key]
        self.cam_num = len(self.image_keys)
        # Get leader/follower num
        self.leader_num = int(
            len(observation["low_dim"]["observation/arm/joint_position"])
            / self.joint_num
        )
        self.follower_num = int(
            len(observation["low_dim"]["action/arm/joint_position"]) / self.joint_num
        )
        if self.leader_num == 1:
            with open("./replay1.json") as file:
                self.template_dict = json.load(file)
        elif self.leader_num == 2:
            with open("./replay2.json") as file:
                self.template_dict = json.load(file)
        while os.path.exists(self.task_path / f"{self.current_episode}"):
            self.current_episode += 1

    def add_raw_data(self, observation: dict, current_frame: int) -> None:
        """Adds raw data to internal storage structures.

        This method processes and stores raw data from an observation dictionary into internal
        data structures such as low-dimensional data, image timestamps, and image data.

        Args:
            observation (dict): A dictionary containing the raw data from the environment.
                The dictionary contains keys for low-dimensional data, image data, and time-related information.
            current_frame (int): The current frame index. This is used for appending data
                to the appropriate lists.

        Returns:
            None: This function does not return any value.

        The method updates internal data structures:
            - Adds low-dimensional data to `self.low_dim`
            - Adds timestamps for the images to `self.images_timestamp`
            - Appends image data to `self.cam_cache`
        """
        for key in self.low_dim_keys:
            if key not in self.low_dim:
                self.low_dim[key] = []
            self.low_dim[key].append(observation["low_dim"][key])

        for key in self.cameras_keys:
            if key not in self.images_timestamp:
                self.images_timestamp[key] = []
            self.images_timestamp[key].append(observation["/time/" + key])

        for key in self.image_keys:

            img = observation[key]

            # 类型检查：是否为 numpy.ndarray
            if not isinstance(img, np.ndarray):
                print(
                    f"add_raw_data [WARNING] Frame {current_frame} - {key} is not a numpy array. Got type: {type(img)}"
                )
                continue  # 或 raise ValueError(...) 终止执行

            # 可选：形状检查，确保是三通道图像
            if img.ndim != 3 or img.shape[2] not in [3, 4]:
                print(
                    f"add_raw_data [WARNING] Frame {current_frame} - {key} has unexpected shape: {img.shape}"
                )
                continue  # 或 raise

            self.cam_cache.append(observation[key])

    def convert_data(self) -> None:
        """Converts raw data into a structured format for further processing.

        This method takes the raw data stored in internal structures and converts it into a
        structured format that follows a predefined template. The data is organized for
        leader and follower robots, as well as for image data, and timestamps are added.

        Returns:
            None: This function does not return any value.

        This method performs the following:
            - Extracts keys for action, observation, and image data from the template.
            - Converts time-related keys and updates the timestamps.
            - Fills the structured template with low-dimensional data for the arm and end-effector (eef) positions,
            poses, and actions for both leader and follower robots.
            - Adds image data for each camera into the structured template.

        It is assumed that the template is pre-loaded and that there is an existing
        structure for each type of data (e.g., joint positions, end-effector poses).
        """
        arm_keys = [
            k
            for k, v in self.template_dict["data"].items()
            if "action" in k or "observation" in k
        ]
        cam_keys = [k for k, v in self.template_dict["data"].items() if "image" in k]
        frame_num = len(self.low_dim[self.low_dim_keys[0]])

        for key in self.low_dim_time_keys:
            self.low_dim_timestamps[key.replace("/time", "")] = self.low_dim.pop(key)
        if len(self.low_dim_time_keys) == 1:
            self.low_dim_timestamps = self.low_dim_timestamps.popitem()[1]

        for key in arm_keys:
            self.template_dict["data"][key] = [
                copy.deepcopy(self.template_dict["data"][key][0])
                for _ in range(frame_num)
            ]
            for i in range(len(self.template_dict["data"][key])):
                self.template_dict["data"][key][i]["t"] = int(
                    self.low_dim_timestamps[i] * 1000
                )
        for key in cam_keys:
            self.template_dict["data"][key] = [
                copy.deepcopy(self.template_dict["data"][key][0])
                for _ in range(frame_num)
            ]

        for cam_index in range(self.cam_num):
            for i in range(
                len(self.template_dict["data"][f"/images/cam{cam_index+1}"])
            ):
                self.template_dict["data"][f"/images/cam{cam_index+1}"][i]["t"] = int(
                    self.images_timestamp[f"cam{cam_index+1}"][i] * 1000
                )

        for i in range(frame_num):
            for leader_index in range(self.leader_num):
                self.template_dict["data"][
                    f"/observation{leader_index+1}/arm/joint_position"
                ][i]["data"]["pos"] = self.low_dim["observation/arm/joint_position"][i][
                    leader_index * self.joint_num : (leader_index + 1) * self.joint_num
                ]
                self.template_dict["data"][
                    f"/observation{leader_index+1}/eef/joint_position"
                ][i]["data"]["t"] = [
                    self.low_dim["observation/eef/joint_position"][i][leader_index]
                ]
                self.template_dict["data"][f"/observation{leader_index+1}/eef/pose"][i][
                    "data"
                ]["t"] = self.low_dim["observation/eef/pose"][i][
                    leader_index * self.joint_num : 3 + leader_index * self.joint_num
                ]
                self.template_dict["data"][f"/observation{leader_index+1}/eef/pose"][i][
                    "data"
                ]["r"] = self.low_dim["observation/eef/pose"][i][
                    3
                    + leader_index * self.joint_num : 7
                    + leader_index * self.joint_num
                ]
            for follower_index in range(self.follower_num):
                self.template_dict["data"][
                    f"/action{follower_index+1}/arm/joint_position"
                ][i]["data"]["pos"] = self.low_dim["action/arm/joint_position"][i][
                    follower_index
                    * self.joint_num : (follower_index + 1)
                    * self.joint_num
                ]
                self.template_dict["data"][
                    f"/action{follower_index+1}/eef/joint_position"
                ][i]["data"]["t"] = [
                    self.low_dim["action/eef/joint_position"][i][follower_index]
                ]
                self.template_dict["data"][f"/action{follower_index+1}/eef/pose"][i][
                    "data"
                ]["t"] = self.low_dim["action/eef/pose"][i][0:3][
                    follower_index * self.joint_num : 3
                    + follower_index * self.joint_num
                ]
                self.template_dict["data"][f"/action{follower_index+1}/eef/pose"][i][
                    "data"
                ]["r"] = self.low_dim["action/eef/pose"][i][3:][
                    3
                    + follower_index * self.joint_num : 7
                    + follower_index * self.joint_num
                ]
            """
            for cam_index in range(self.cam_num):
                self.template_dict["data"][f"/images/cam{cam_index+1}"][i][
                    "data"
                ] = self.cam_cache[self.cam_num * i + cam_index]
                # self.template_dict['data']['/images/cam2'][i]['data'] = self.cam_cache[2*i+1]
            """
            for cam_index in range(self.cam_num):
                # 计算出当前帧的对应图像在 cam_cache 中的索引
                img = self.cam_cache[self.cam_num * i + cam_index]

                # 写入到模板结构中对应的位置
                self.template_dict["data"][f"/images/cam{cam_index+1}"][i]["data"] = img

                # 打印图像类型确认：确保是 numpy.ndarray
                # print(f"[DEBUG_convert_data] 写入后 Frame {i} cam{cam_index+1} data 类型: {type(img)}, 形状: {getattr(img, 'shape', 'N/A')}")

    def save_data(self) -> None:
        """Converts data and saves it to a BSON file.

        This method converts the current raw data using `convert_data` and then saves
        it to a BSON file in the appropriate directory. It also creates a new directory
        for the current episode if it does not already exist.

        The saved BSON file is stored in the format:
            <task_path>/<current_episode>/data.bson

        Returns:
            None: This function does not return any value.

        The `current_episode` is incremented after the data is saved.
        """
        self.convert_data()  # 这一步没问题？
        # Save dict to bson file
        if not os.path.exists(self.task_path / f"{self.current_episode}"):
            os.makedirs(self.task_path / f"{self.current_episode}")
        from airbot_data.io import save_bson

        print("start saving bason")
        # 在这里检查template_dict的图像类型

        # 遍历 template_dict 中的所有图像项，打印类型和形状
        for cam_index in range(self.cam_num):
            cam_key = f"/images/cam{cam_index+1}"
            if cam_key not in self.template_dict["data"]:
                print(f"[WARNING] {cam_key} not found in template_dict['data']")
                continue
            for i, frame in enumerate(self.template_dict["data"][cam_key]):
                img = frame.get("data", None)
                # print(f"[Save_Bason_DEBUG] cam{cam_index+1} frame {i} type: {type(img)}, shape: {getattr(img, 'shape', 'N/A')}")
                # 也可以加入类型断言
                assert isinstance(
                    img, np.ndarray
                ), f"[ERROR] cam{cam_index+1} frame {i} is not a numpy array! Got: {type(img)}"

        save_bson(
            self.template_dict, self.task_path / f"{self.current_episode}" / "data.bson"
        )
        print("Save data to ", self.task_path / f"{self.current_episode}" / "data.bson")
        self.current_episode += 1

    def save(self) -> None:
        """Converts data and appends it to the cache.

        This method converts the current raw data using `convert_data` and appends
        the result to the `dicts_cache` list. It does not create a new file or directory.

        Returns:
            None: This function does not return any value.

        The data is stored in the `dicts_cache` for later use or batch saving.
        """
        self.convert_data()
        self.dicts_cache.append(self.template_dict)

    def save_last(self) -> None:
        """Saves all cached data to BSON files.

        This method iterates through the data stored in the `dicts_cache` list and
        saves each entry as a BSON file. A new directory is created for each episode
        if it does not already exist.

        Returns:
            None: This function does not return any value.

        The saved BSON files are stored in the format:
            <task_path>/<episode_index>/data.bson
        """
        from airbot_data.io import save_bson

        for episode_index in range(len(self.dicts_cache)):
            if not os.path.exists(self.task_path / f"{episode_index}"):
                os.makedirs(self.task_path / f"{episode_index}")
            save_bson(
                self.template_dict, self.task_path / f"{episode_index}" / "data.bson"
            )
            print("Save data to ", self.task_path / f"{episode_index}" / "data.bson")

    def clear_cache(self) -> None:
        """Clears all cached data and reloads the template.

        This method clears all the internal caches, including camera images, low-dimensional
        data, and timestamps. After clearing the cache, it reloads the template from a
        default replay file (`replay1.json`).

        Returns:
            None: This function does not return any value.

        The caches are cleared to free up memory or reset data for a new episode.
        """
        self.cam_cache = []
        self.low_dim = {}
        self.images_timestamp = {}
        self.low_dim_timestamps = {}
        self.low_dim_keys = {}
        self.low_dim_time_keys = {}
        self.cameras_keys = {}
        with open("./replay1.json") as file:
            self.template_dict = json.load(file)

    def save_all_images(self, observation: dict, current_frame: int) -> None:
        """Saves all images in the observation using multi-threading.

        This method saves images from the provided `observation` dictionary to disk
        using multi-threading for efficiency. Each image is saved in its corresponding
        directory within the `task_path`.

        Args:
            observation (dict): A dictionary containing image data. Each key corresponds
                to a camera and the associated image data.
            current_frame (int): The current frame index used to name the saved image files.

        Returns:
            None: This function does not return any value.

        Multi-threading is used to save images concurrently for all cameras and frames.
        """
        futures = []
        # Save Images With Muti-Thread
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(self.image_keys) * self.num_image_writers_per_camera
        ) as executor:
            for key in self.image_keys:
                tmp_imgs_dir = self.task_path / f"{self.current_episode}" / key
                if not os.path.exists(tmp_imgs_dir):
                    os.makedirs(tmp_imgs_dir)
                futures += [
                    executor.submit(
                        self.save_image,
                        observation[key],
                        current_frame,
                        tmp_imgs_dir,
                    )
                ]

    def remove_last_episode(self) -> None:
        """Removes the directory of the last episode.

        This method removes the directory corresponding to the last episode and its
        contents from the file system. It also decrements the `current_episode` index.

        Returns:
            None: This function does not return any value.

        If the directory cannot be removed (e.g., due to an error), an error message
        is printed.
        """
        rm_path = self.task_path / f"{self.current_episode-1}"
        try:
            shutil.rmtree(rm_path)
            print(
                f"Directory {rm_path} and its contents have been removed successfully"
            )
            self.current_episode -= 1
        except OSError as e:
            print(f"Error: {rm_path} : {e.strerror}")


class KeyHandler:
    """Handles key press events for controlling data collection and robot states.

    This class listens for specific key presses and triggers actions in the associated
    `Machine` object. These actions include starting or stopping data collection, printing
    current states, removing the last saved episode, and controlling the robot's behavior.
    """

    def __init__(self, collector: Machine) -> None:
        """Initializes the KeyHandler with the given Machine instance.

        Args:
            collector (Machine): The Machine instance responsible for data collection and state management.
        """
        self.collector = collector

    def show_instruction(self) -> None:
        """Displays the instructions for the key press actions.

        This function provides a user-friendly guide to inform the user about the available
        key press actions for controlling the system.
        """
        print(
            """(Press:
            'Space Bar' to start recording the data,
            'q' to discard current recording or rerecording the last episode,
            'p' to print current arms' states,
            'r' to remove the last saved episode,
            'z' to exit program when robot in Wait state
            'i' to show this instructions again.
        )"""
        )

    def handle_keypress(self, key: keyboard.Key) -> None:
        """Handles key press events and triggers the appropriate actions.

        This function listens for key presses and initiates the corresponding actions in the
        `Machine` instance. The actions can include starting or stopping data collection,
        printing states, removing episodes, or changing robot states.

        Args:
            key: The key event triggered by the user.

        Returns:
            None: This function does not return any value.
        """
        # 根据按键事件触发状态机的状态
        try:
            if key == keyboard.Key.space:
                collect_thread = threading.Thread(target=self.collector.CollectBegin)
                collect_thread.daemon = True
                collect_thread.start()
                self.collector.change_flag = True
            elif key.char == "q":
                ct_thread = threading.Thread(target=self.collector.CollectTermination)
                ct_thread.daemon = True
                ct_thread.start()
                self.change_flag = True
            elif key.char == "p":
                print("Current State: ", self.collector.state)
                print("Current change log: ", self.collector.change_flag)
                print("Current episode: ", self.collector.file_manager.current_episode)
            elif key.char == "r":
                if self.collector.file_manager.current_episode > 0:
                    if self.collector.state == "Wait":
                        self.collector.file_manager.remove_last_episode()
                    else:
                        print(self.collector.state, " do not allow remove!")
                print("Current episode: ", self.collector.file_manager.current_episode)
            elif key.char == "0":
                self.collector.trigger("Resetting")
            elif key.char == "z":
                self.collector.trigger("Exit")
                self.change_flag = True
            elif key.char == "i":
                self.show_instruction()
            elif key.char == "s":
                ct_thread = threading.Thread(target=self.collector.CollectOver)
                ct_thread.daemon = True
                ct_thread.start()
            else:
                print("Invalid key pressed")

        except Exception as e:
            print("ERROR: ", e)


class Visualizer:
    """Handles the visualization of demonstration information and camera data.

    This class manages displaying text information (such as episode and step numbers)
    and images (from camera feeds) in a graphical interface using OpenCV. It updates
    the displayed information and images in real time.
    """

    def __init__(self) -> None:
        """Initializes the Visualizer instance with default settings.

        This constructor sets up the window size, font settings, queue, and initial
        text for episode and steps. It also initializes the image canvas for display.

        Attributes:
            height (int): The height of the display window.
            width (int): The width of the display window.
            font (int): Font type for displaying text.
            font_scale_up (float): Font scale for the upper text (episode).
            font_scale_down (float): Font scale for the lower text (steps).
            thickness_up (int): Thickness of the upper text.
            thickness_down (int): Thickness of the lower text.
            frame_queue (queue.Queue): Queue for storing camera frames to be displayed.
            lock (threading.Lock): Lock for synchronizing access to shared data.
            image (np.ndarray): Image canvas for displaying the background.
            text_top (str): Text to display for the episode information.
            text_bottom (str): Text to display for the step information.
            episode (int): Current episode number.
            steps (int): Current number of steps.
        """
        # Set font properties for text display
        self.height, self.width = 600, 800
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale_up = 1
        self.font_scale_down = 2
        self.thickness_up = 1
        self.thickness_down = 2
        self.frame_queue = queue.Queue(maxsize=1)  # Set queue size to 1
        self.lock = threading.Lock()

        # Initialize a white image background
        self.image = np.ones((self.height, self.width, 3), dtype=np.uint8) * 255
        self.text_top = "Episode: 0"
        self.text_bottom = "Steps: 0"

        # Calculate text size for centering the text
        self.text_width_top, self.text_height_top = cv2.getTextSize(
            self.text_top, self.font, self.font_scale_up, self.thickness_up
        )[0]
        self.text_width_bottom, self.text_height_bottom = cv2.getTextSize(
            self.text_bottom, self.font, self.font_scale_down, self.thickness_down
        )[0]
        self.episode = 0
        self.steps = 0

    def show_info_on_image(self) -> None:
        """Displays the current episode and step information on the image.

        This function overlays the episode and step text on the image background,
        and then displays the image with the updated text using OpenCV.
        """
        with self.lock:
            episode = self.episode
            steps = self.steps
        text_top = f"Episode: {episode}"
        text_bottom = f"Steps: {steps}"
        image_copy = self.image.copy()

        # Calculate positions to center the text on the image
        x_top = (self.width - self.text_width_top) // 2
        y_top = int(self.height * 0.25)

        x_bottom = (self.width - self.text_width_bottom) // 2
        y_bottom = int(self.height * 0.75)

        # Add the episode and step text to the image
        cv2.putText(
            image_copy,
            text_top,
            (x_top, y_top),
            self.font,
            self.font_scale_up,
            (0, 0, 255),
            self.thickness_up,
        )
        cv2.putText(
            image_copy,
            text_bottom,
            (x_bottom, y_bottom),
            self.font,
            self.font_scale_down,
            (0, 255, 0),
            self.thickness_down,
        )
        # Show the image with the updated text
        with self.lock:
            cv2.imshow("Demonstration Information", image_copy)
        cv2.waitKey(1)

    def show_cameras(self) -> None:
        """Continuously displays camera data from the frame queue.

        This function runs in a separate thread and keeps displaying the latest
        frames from the camera in real time. It updates the image windows for each
        camera key available in the observation.
        """
        while True:
            self.show_info_on_image()  # Display information on the image
            try:
                # Retrieve the latest frame from the queue (timeout after 1 second)
                observation = self.frame_queue.get(timeout=1)
                image_keys = [key for key in observation if "image" in key]
                for key in image_keys:
                    with self.lock:
                        # Display each camera feed in a separate window
                        cv2.imshow(
                            key, cv2.cvtColor(observation[key], cv2.COLOR_RGB2BGR)
                        )
            except queue.Empty:
                pass  # If no new frame, just skip
                # print("No new frame to display")
                # continue
            finally:
                cv2.waitKey(1)  # Allow OpenCV to update windows

    def update_info(self, episode: int, steps: int) -> None:
        """Updates the episode and step information.

        This method is called to update the current episode and step count in the
        visualizer, and it uses a lock to ensure thread-safe access to the shared data.

        Args:
            episode (int): The new episode number.
            steps (int): The new step count.
        """
        with self.lock:
            self.episode = episode
            self.steps = steps
