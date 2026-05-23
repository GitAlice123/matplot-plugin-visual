from __future__ import annotations

from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent

import matplotlib.pyplot as plt

from mpl_visual_editor import style_figure

STYLE_MODE = "edit"  # "edit": open GUI; "apply": apply saved patch; "off": raw plot.


def main() -> None:
    labels = ["Compute", "Network", "Storage", "Idle"]
    values = [38, 27, 21, 14]
    colors = ["#4c78a8", "#f58518", "#54a24b", "#b279a2"]

    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.0f%%",
        startangle=110,
        counterclock=False,
        colors=colors,
        wedgeprops={"linewidth": 1.2, "edgecolor": "white"},
        textprops={"fontsize": 10},
    )
    ax.set_title("Resource Breakdown")
    ax.legend(wedges, labels, title="Category", loc="center left", bbox_to_anchor=(1.0, 0.5))

    style_figure(
        fig,
        mode=STYLE_MODE,
        name="demo_pie",
        source_path=__file__,
        style_dir=EXAMPLES_DIR / "styles",
    )


if __name__ == "__main__":
    main()
