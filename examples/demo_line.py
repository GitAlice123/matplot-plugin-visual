from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt

from mpl_visual_editor import style_figure

STYLE_MODE = "edit"  # "edit": open GUI; "apply": apply saved patch; "off": raw plot.


def main() -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot([1, 2, 3], [1, 4, 9], marker="o", label="A")
    ax.plot([1, 2, 3], [1, 2, 3], marker="s", label="B")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title("Demo")
    ax.legend()
    ax.grid(True, alpha=0.3)

    style_figure(
        fig,
        mode=STYLE_MODE,
        name="demo_line",
        source_path=__file__,
        style_dir=ROOT / "examples" / "styles",
    )


if __name__ == "__main__":
    main()
