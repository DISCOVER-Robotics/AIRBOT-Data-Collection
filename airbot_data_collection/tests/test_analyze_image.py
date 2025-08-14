import cv2
from matplotlib import pyplot as plt
import numpy as np
from pathlib import Path


def extract_rgb_mask(data_root, task_name, peak_choices: list, show=False, save=True):
    ep_dir = f"{data_root}/{task_name}/all_variations/episodes"
    ep_length = len(list(Path(ep_dir).glob("episode*")))
    for ep_index in range(0, ep_length):
        episode = Path(ep_dir) / f"episode{ep_index}"
        print(f"Processing {episode}...")
        rgb_length = len(list(episode.glob("front_rgb/*.png")))
        mask_length = len(list(episode.glob("front_mask/*.png")))
        assert rgb_length == mask_length, (
            f"RGB ({rgb_length}) and mask ({mask_length}) counts do not match in {episode}"
        )
        peaks_num = 0
        if save:
            output_dir = episode / "front_rgb_mask"
            output_dir.mkdir(parents=True, exist_ok=True)
        for index in range(0, rgb_length):
            rgb = episode / "front_rgb" / f"{index}.png"
            mask = episode / "front_mask" / f"{index}.png"
            raw_mask_image = cv2.imread(str(mask))
            raw_rgb_image = cv2.imread(str(rgb))

            gray_image = cv2.cvtColor(raw_mask_image, cv2.COLOR_BGR2GRAY)
            # print(raw_mask_image.shape)
            hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256])
            # print(hist.shape)
            # print(hist[0:3])

            peak_start = -1
            peaks = []
            for i, point in enumerate(hist):
                if point > 0:
                    if peak_start < 0:
                        peak_start = i
                else:
                    if peak_start >= 0:
                        peaks.append((peak_start, i))
                        peak_start = -1
            assert peaks_num == 0 or len(peaks) == peaks_num, (
                f"Expected {peaks_num} peaks, but found {len(peaks)} in {episode}"
            )
            print(f"{index}: {len(peaks)} Peaks found at:", peaks)

            cur_peak_choices = peak_choices.copy()
            for i, pc in enumerate(peak_choices.copy()):
                if isinstance(pc, int):
                    cur_peak_choices[i] = peaks[pc]
                elif isinstance(pc, slice):
                    cur_peak_choices.pop(i)
                    cur_peak_choices.extend(peaks[pc])
            print(f"Using peak choices: {cur_peak_choices}")

            mask = np.zeros_like(gray_image)
            for peak in cur_peak_choices:
                roi = (gray_image >= peak[0]) & (gray_image < peak[1])
                mask[roi] = 1
            masked_image = (mask[..., np.newaxis] * raw_rgb_image).astype(np.uint8)

            if show:
                plt.plot(hist)
                cv2.imshow("RGB Image", raw_rgb_image)
                cv2.imshow("Gray Image", gray_image)
                cv2.imshow("Original Image", raw_mask_image)
                cv2.imshow("Masked RGB Image", masked_image)
                plt.xlim([0, 256])
                plt.show(block=False)
                if cv2.waitKey(0) == 27:  # Wait for ESC key to exit
                    cv2.destroyAllWindows()
                    exit(0)
            if save:
                output_file = (output_dir / f"{index}.png").absolute()
                # print(output_file)
                cv2.imwrite(str(output_file), masked_image)


if __name__ == "__main__":
    # data_root = "/home/ghz/Work/Research/manipulate-anything/data/GT_12T_100EP"
    data_root = (
        "/home/ghz/Work/Research/manipulate-anything/data/GT_12T_data/train_12_GT"
    )
    task_name = "open_wine_bottle"

    task_peaks = {
        "lamp_on": [(7, 14), slice(4, None)],
        "open_box": [(7, 14), slice(4, None)],
        "open_wine_bottle": [(7, 14), slice(4, None)],
        # "open_jar": [(7, 14), slice(4, None)],
    }

    # task_name = "close_box"
    # extract_rgb_mask(data_root, task_name, [(11, 14), (37, 41)], show=False, save=True)
    extract_rgb_mask(
        data_root, task_name, [(7, 14), slice(4, None)], show=True, save=False
    )

# # 打包成单个整数通道：0xRRGGBB
# packed_img = (
#     (raw_mask_image[..., 0].astype(np.uint32) << 16)
#     | (raw_mask_image[..., 1].astype(np.uint32) << 8)
#     | (raw_mask_image[..., 2].astype(np.uint32))
# )
