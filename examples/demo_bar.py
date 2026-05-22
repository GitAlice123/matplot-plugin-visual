from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np

from mpl_visual_editor import edit


def main() -> None:
    categories = ["Q1", "Q2", "Q3", "Q4"]
    x = np.arange(len(categories))
    width = 0.36

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(x - width / 2, [12, 18, 15, 22], width, label="Product A", color="#4c78a8")
    ax.bar(x + width / 2, [10, 14, 19, 17], width, label="Product B", color="#f58518")

    ax.set_xticks(x, categories)
    ax.set_ylabel("Revenue")
    ax.set_title("Quarterly Revenue")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.25)

    edit(fig)


if __name__ == "__main__":
    main()
