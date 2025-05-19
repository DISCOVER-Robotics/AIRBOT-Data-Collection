import numpy as np
from PIL import Image, ImageTk
from tkinter import Tk, Canvas
from dataclasses import dataclass
import math
import time


@dataclass
class SampleInfo:
    round: int
    index: int


class AutoGridVisualizer:
    def __init__(self, width=640, height=480):
        self.root = Tk()
        self.root.title("Auto Grid Viewer")
        self.canvas = Canvas(self.root, width=width, height=height + 40, bg="gray")
        self.canvas.pack()

        self.width = width
        self.height = height
        self.tk_images = {}
        self.image_ids = {}
        self.text_ids = {}

    def update(self, data: dict[str, np.ndarray], info: SampleInfo):
        num = len(data)
        grid_cols = math.ceil(math.sqrt(num))
        grid_rows = math.ceil(num / grid_cols)
        img_w = self.width // grid_cols
        img_h = self.height // grid_rows

        for i, (title, img) in enumerate(data.items()):
            row, col = divmod(i, grid_cols)
            x = col * img_w
            y = row * img_h + 20

            # Convert to PIL Image (assume RGB np.ndarray)
            image_pil = Image.fromarray(img.astype(np.uint8), mode="RGB")
            image_pil = image_pil.resize((img_w, img_h - 20))
            tk_image = ImageTk.PhotoImage(image_pil)

            self.tk_images[i] = tk_image

            if i in self.image_ids:
                self.canvas.itemconfig(self.image_ids[i], image=tk_image)
                self.canvas.coords(self.image_ids[i], x, y)
            else:
                self.image_ids[i] = self.canvas.create_image(
                    x, y, anchor="nw", image=tk_image
                )

            # Title text
            title_y = row * img_h
            if f"title_{i}" in self.text_ids:
                self.canvas.itemconfig(self.text_ids[f"title_{i}"], text=title)
                self.canvas.coords(self.text_ids[f"title_{i}"], x + 5, title_y)
            else:
                self.text_ids[f"title_{i}"] = self.canvas.create_text(
                    x + 5,
                    title_y,
                    text=title,
                    fill="blue",
                    font=("Helvetica", 12, "bold"),
                    anchor="nw",
                )

        # Info text at bottom
        info_text = f"Round: {info.round} | Index: {info.index}"
        if "info" in self.text_ids:
            self.canvas.itemconfig(self.text_ids["info"], text=info_text)
        else:
            self.text_ids["info"] = self.canvas.create_text(
                10,
                self.height + 10,
                text=info_text,
                fill="black",
                font=("Helvetica", 12),
                anchor="nw",
            )

        self.root.update_idletasks()
        self.root.update()


def create_color_image(color: tuple[int, int, int], shape=(240, 320, 3)) -> np.ndarray:
    return np.ones(shape, dtype=np.uint8) * np.array(color, dtype=np.uint8)


if __name__ == "__main__":
    vis = AutoGridVisualizer(640, 480)

    images = {
        "Red": create_color_image((255, 0, 0)),
        "Green": create_color_image((0, 255, 0)),
        "Blue": create_color_image((0, 0, 255)),
        # "Yellow": create_color_image((255, 255, 0)),
        # "Cyan": create_color_image((0, 255, 255)),
        # "Magenta": create_color_image((255, 0, 255)),
        # "White": create_color_image((255, 255, 255)),
    }

    round_num = 1
    index = 0

    while True:
        start = time.monotonic()
        vis.update(images, SampleInfo(round=round_num, index=index))
        print(f"time cost: {time.monotonic() - start:.3f}s")
        time.sleep(1)
        index += 1
