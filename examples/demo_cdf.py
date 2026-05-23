from __future__ import annotations

from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent

import matplotlib.pyplot as plt
import numpy as np

from mpl_visual_editor import style_figure

STYLE_MODE = "edit"  # "edit": open GUI; "apply": apply saved patch; "off": raw plot.


def empirical_cdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(values)
    y = np.arange(1, len(x) + 1) / len(x)
    return x, y


def main() -> None:
    rng = np.random.default_rng(7)
    baseline = rng.lognormal(mean=2.1, sigma=0.35, size=180)
    optimized = rng.lognormal(mean=1.85, sigma=0.28, size=180)
    x_base, y_base = empirical_cdf(baseline)
    x_opt, y_opt = empirical_cdf(optimized)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(x_base, y_base, drawstyle="steps-post", linewidth=2.0, label="Baseline")
    ax.plot(x_opt, y_opt, drawstyle="steps-post", linewidth=2.0, label="Optimized")
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("Latency Distribution")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")

    style_figure(
        fig,
        mode=STYLE_MODE,
        name="demo_cdf",
        source_path=__file__,
        style_dir=EXAMPLES_DIR / "styles",
    )


if __name__ == "__main__":
    main()
