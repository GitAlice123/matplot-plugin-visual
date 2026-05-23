from __future__ import annotations

from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent

import matplotlib.pyplot as plt
import numpy as np

from mpl_visual_editor import style_figure

STYLE_MODE = "edit"  # "edit": open GUI; "apply": apply saved patch; "off": raw plot.


def main() -> None:
    rng = np.random.default_rng(11)
    group_a = rng.normal(loc=(2.0, 3.0), scale=(0.45, 0.5), size=(45, 2))
    group_b = rng.normal(loc=(3.2, 2.2), scale=(0.5, 0.35), size=(45, 2))
    sizes_a = rng.uniform(35, 110, size=len(group_a))
    sizes_b = rng.uniform(40, 130, size=len(group_b))

    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.scatter(group_a[:, 0], group_a[:, 1], s=sizes_a, marker="o", alpha=0.75, label="WiFi")
    ax.scatter(group_b[:, 0], group_b[:, 1], s=sizes_b, marker="D", alpha=0.75, label="RDMA")
    ax.set_xlabel("Throughput (Gbps)")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Throughput vs Latency")
    ax.grid(True, alpha=0.25)
    ax.legend()

    style_figure(
        fig,
        mode=STYLE_MODE,
        name="demo_scatter",
        source_path=__file__,
        style_dir=EXAMPLES_DIR / "styles",
    )


if __name__ == "__main__":
    main()
