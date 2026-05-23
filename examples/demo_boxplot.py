from __future__ import annotations

from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent

import matplotlib.pyplot as plt
import numpy as np

from mpl_visual_editor import style_figure

STYLE_MODE = "edit"  # "edit": open GUI; "apply": apply saved patch; "off": raw plot.


def main() -> None:
    rng = np.random.default_rng(19)
    samples = [
        rng.normal(42, 5.0, 80),
        rng.normal(48, 6.0, 80),
        rng.normal(53, 4.5, 80),
        rng.normal(57, 7.0, 80),
    ]
    labels = ["Baseline", "Tuned", "Cached", "RDMA"]
    colors = ["#4c78a8", "#f58518", "#54a24b", "#b279a2"]

    fig, ax = plt.subplots(figsize=(7, 4.8))
    box = ax.boxplot(
        samples,
        labels=labels,
        patch_artist=True,
        showmeans=True,
        boxprops={"linewidth": 1.4},
        medianprops={"color": "#222222", "linewidth": 1.8},
        meanprops={"marker": "D", "markerfacecolor": "#ffffff", "markeredgecolor": "#222222"},
        flierprops={"marker": "o", "markersize": 4, "alpha": 0.5},
    )
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_ylabel("Latency (us)")
    ax.set_title("Latency Distribution by Configuration")
    ax.grid(True, axis="y", alpha=0.25)

    style_figure(
        fig,
        mode=STYLE_MODE,
        name="demo_boxplot",
        source_path=__file__,
        style_dir=EXAMPLES_DIR / "styles",
    )


if __name__ == "__main__":
    main()
