# Matplotlib Visual Style Editor

A small visual editor for the **last mile of Python plotting**.

`mpl_visual_editor` lets you keep your normal Matplotlib plotting code, open the finished `Figure` in a lightweight GUI, make small visual adjustments, add annotations, and export those adjustments as a reusable Python style patch.

The goal is not to replace Matplotlib, rewrite your plotting script, or become a full plotting application. The goal is to solve the annoying final step after the figure is already basically correct: moving labels, changing font sizes, adjusting colors, placing legends, adding arrows or text boxes, and exporting a clean final figure without repeatedly editing and rerunning plotting code.

This is especially useful for a small number of figures that need manual polish, such as paper figures, slides, reports, or figures with annotations. It is currently less suitable for batch-generating many figures at once, or for fully automated plotting pipelines where every style detail should be controlled programmatically.

## Why this exists

Matplotlib is powerful and precise, but small presentation-level changes often take disproportionate effort. A typical workflow looks like this:

1. Write Python code to generate the plot.
2. Notice that a label is slightly misplaced, a legend overlaps the data, or an arrow/text annotation is needed.
3. Guess the right Matplotlib parameters.
4. Rerun the script.
5. Repeat until the figure looks acceptable.

Let's look at an example demo, to show a typical matplotlib work with last-mile modifications. 
```python
import numpy as np
import matplotlib.pyplot as plt

x = np.arange(0, 60)
baseline = 60 + 0.08 * x + np.sin(x / 5) * 1.2
optimized = 62 + 0.16 * x + np.sin(x / 6) * 1.0

baseline[24:34] -= 5
optimized[24:34] -= 3

fig, ax = plt.subplots(figsize=(7, 4))

# The actual data plot is simple.
ax.plot(x, baseline, marker="o", markevery=6, label="Baseline")
ax.plot(x, optimized, marker="s", markevery=6, label="Optimized")

ax.set_xlabel("Iteration")
ax.set_ylabel("Throughput")
ax.set_title("A simple plot with last-mile annotations")
ax.grid(True, alpha=0.3)
ax.legend(loc="upper left")

# The last-mile polish starts here.
# These edits are useful, but they quickly become tedious because
# every position, offset, and style is controlled by code.

ax.axvspan(24, 34, alpha=0.15)
ax.axvline(24, linestyle="--", linewidth=1)
ax.axvline(34, linestyle="--", linewidth=1)

ax.text(
    29,
    72,
    "degradation window",
    ha="center",
    fontsize=9,
    fontweight="bold",
)

ax.annotate(
    "temporary drop",
    xy=(29, optimized[29]),
    xytext=(13, 69),
    arrowprops=dict(arrowstyle="->", linewidth=1.2),
    bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.9),
    fontsize=9,
)

ax.annotate(
    "recovery",
    xy=(38, optimized[38]),
    xytext=(44, 67),
    arrowprops=dict(arrowstyle="->", linewidth=1.2),
    bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.9),
    fontsize=9,
)

for i, label, dx, dy in [
    (24, "start", -6, 2),
    (34, "end", 1, -3),
    (50, "stable gain", -8, 2),
]:
    ax.scatter(x[i], optimized[i], s=80, facecolors="none", edgecolors="black")
    ax.text(x[i] + dx, optimized[i] + dy, label, fontsize=8)

ax.set_xlim(-2, 62)
ax.set_ylim(56, 76)
fig.subplots_adjust(left=0.12, right=0.96, top=0.88, bottom=0.15)

plt.show()
```
What you gonna get is a figure like this:
<img width="2241" height="646" alt="image" src="https://github.com/user-attachments/assets/432a1953-e0cf-4745-98c0-a807ff545b03" />


The base plot is only a few lines of Matplotlib code. However, once we add final annotations, highlighted regions, straight arrows, emphasized points, and layout tweaks, the code quickly becomes full of manual coordinates and fragile offsets. Even with an LLM or coding agent, last-mile figure polishing is hard to delegate: **it is difficult to describe the exact visual layout in your head**, and small details often require repeated prompt-code-render iterations. A WYSIWYG editor makes these adjustments direct and immediate.

This project keeps the strengths of code-based plotting while adding an interactive final adjustment layer. You still create the figure in Python. The editor only inspects and mutates the live Matplotlib `Figure`, then exports a replayable patch that can be applied later. With this project, you can write your code like this:
```python
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from mpl_visual_editor import style_figure


STYLE_MODE = "edit"
# Use "edit" while polishing the figure interactively.
# After exporting a style patch, switch to "apply" for reproducible generation.
# Use "off" to see the raw Matplotlib figure.


x = np.arange(0, 60)
baseline = 60 + 0.08 * x + np.sin(x / 5) * 1.2
optimized = 62 + 0.16 * x + np.sin(x / 6) * 1.0

baseline[24:34] -= 5
optimized[24:34] -= 3

fig, ax = plt.subplots(figsize=(7, 4))

# The actual data plot stays simple.
ax.plot(x, baseline, marker="o", markevery=6, label="Baseline")
ax.plot(x, optimized, marker="s", markevery=6, label="Optimized")

ax.set_xlabel("Iteration")
ax.set_ylabel("Throughput")
ax.set_title("A simple plot with last-mile visual editing")
ax.grid(True, alpha=0.3)
ax.legend(loc="upper left")


# Instead of writing dozens of fragile last-mile Matplotlib calls,
# open the visual editor, adjust the figure interactively, and export a
# reusable Python style patch.
style_figure(
    fig,
    mode=STYLE_MODE,
    name="last_mile_demo",
    source_path=__file__,
    style_dir=Path(__file__).parent / "styles",
    save_path=Path(__file__).parent / "figures" / "last_mile_demo.pdf",
)
```

## Core idea

Your original plotting code remains the source of truth for the data and the basic plot structure.

`mpl_visual_editor` adds a second layer:

```text
original plotting code  ->  Matplotlib Figure  ->  visual editor  ->  style patch
                                                        |
                                                        v
                                                  final figure export
```

The exported style patch is a normal Python file that defines `apply_style(fig)`. You can commit this patch together with your plotting script and reapply it when regenerating the same figure.

## Typical use cases

Good fits:

- Polishing one or a few paper-quality Matplotlib figures.
- Adjusting fonts, colors, line widths, markers, legends, grids, axes, and labels after the plot already exists.
- Adding final annotations such as arrows, lines, rectangles, ellipses, diamonds, triangles, or text boxes.
- Making small manual adjustments that are tedious to express in Matplotlib code.
- Keeping the original plotting script mostly unchanged while storing visual edits separately.

Less ideal fits:

- Generating hundreds or thousands of figures in a fully automated batch.
- Replacing Matplotlib's plotting API.
- Building complex interactive dashboards.
- Large-scale graphic design work.
- Editing arbitrary Matplotlib artists that do not yet have adapters.
- Making semantic data transformations. The editor is intended for visual styling and annotation, not data processing.

## Features

Current prototype features include:

- Open an existing Matplotlib `Figure` in a PySide6 GUI.
- Inspect supported Matplotlib artists in an object list.
- Edit common figure, axes, line, bar, scatter, patch, wedge, text, axis, legend, spine, arrow, fill, shape, and text-box properties.
- Add editor-created annotations, including lines, arrows, double arrows, rectangles, rounded rectangles, ellipses, triangles, diamonds, and text boxes.
- Move selected text, legends, shapes, and text boxes visually.
- Edit text inline by double-clicking text objects.
- Undo and redo recent editing operations.
- Export a reusable Python style patch.
- Reopen a figure with the existing patch automatically applied, so editing can continue from the last saved style.
- Apply a saved style patch without opening the GUI.
- Disable the editor and generate the raw plot.
- Export the currently styled figure to common image/document formats such as PDF, PNG, SVG, JPEG, and TIFF.
- Detect unsupported visible artists and show them as read-only entries, so users can see what was found even if editing support is not implemented yet.

## Installation

Requires Python 3.9 or newer.

For local development, clone the repository and install it in editable mode:

```bash
git clone https://github.com/GitAlice123/matplot-plugin-visual.git
cd matplot-plugin-visual
pip install -e .
```

For a regular local install:

```bash
pip install .
```

The package depends on:

```text
matplotlib>=3.8
PySide6>=6.6
```

Because the editor uses a Qt GUI backend, it should be run in an environment where GUI windows can be opened. On a remote server, you may need X11 forwarding, a desktop session, or another GUI-capable setup.

## Quick start

Add `style_figure` after your normal Matplotlib plotting code:

```python
import matplotlib.pyplot as plt
from mpl_visual_editor import style_figure

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
    mode="edit",
    name="demo_line",
    source_path=__file__,
)
```

Run the script. The editor window will open. Make visual changes, then click **Export style patch**.

By default, the patch is written to:

```text
styles/demo_line_style_patch.py
```

The next time you run the same script in `mode="edit"`, the editor applies the existing patch first, so you continue editing from the last saved style instead of starting from the raw figure.

## Workflow modes

`style_figure` supports three modes:

```python
STYLE_MODE = "edit"   # open GUI, edit interactively, export style patch
STYLE_MODE = "apply"  # apply existing style patch, do not open GUI
STYLE_MODE = "off"    # leave the raw Matplotlib figure unchanged
```

A common workflow is:

```python
STYLE_MODE = "edit"
```

Use this while designing the final figure. When the figure is ready and you want reproducible non-interactive generation, switch to:

```python
STYLE_MODE = "apply"
```

For debugging or comparing against the original plot, use:

```python
STYLE_MODE = "off"
```

## Saving the final figure

You can let `style_figure` save the final figure after applying the selected mode:

```python
style_figure(
    fig,
    mode="apply",
    name="demo_line",
    source_path=__file__,
    save=True,
)
```

With `save=True`, the default output path is:

```text
figures/demo_line.pdf
```

You can also choose an explicit path:

```python
style_figure(
    fig,
    mode="apply",
    name="demo_line",
    source_path=__file__,
    save_path="figures/demo_line.png",
    save_kwargs={"dpi": 300, "bbox_inches": "tight"},
)
```

Inside the GUI, you can also use **Export figure...** to export the currently styled figure manually.

## Custom style patch path

By default, the style patch path is derived from `name` and `style_dir`:

```python
style_figure(
    fig,
    mode="edit",
    name="my_plot",
    style_dir="styles",
)
```

This writes:

```text
styles/my_plot_style_patch.py
```

You can provide a custom patch path:

```python
style_figure(
    fig,
    mode="edit",
    style_path="styles/custom_style.py",
)
```

Or use the lower-level editor API directly:

```python
from mpl_visual_editor import edit

edit(fig, export_path="styles/custom_style.py")
```

## Ignoring an existing patch

When `mode="edit"`, an existing patch is applied before the GUI opens by default. This is useful for continuing previous edits.

To edit the raw figure and ignore the existing patch:

```python
style_figure(
    fig,
    mode="edit",
    name="my_plot",
    source_path=__file__,
    apply_existing=False,
)
```

## Applying a patch manually

A generated style patch is a Python file that contains an `apply_style(fig)` function. You normally apply it through `style_figure(mode="apply")`, but you can also use the helper directly:

```python
from mpl_visual_editor import apply_style_patch

applied = apply_style_patch(fig, "styles/my_plot_style_patch.py")
```

`applied` is `True` when the patch exists and was applied. If the patch is missing, the helper can warn, ignore, or raise an error depending on the `missing` argument.

## Demo scripts

The repository includes several small demos:

```bash
python examples/demo_line.py
python examples/demo_bar.py
python examples/demo_scatter.py
python examples/demo_cdf.py
python examples/demo_boxplot.py
python examples/demo_pie.py
```

Each demo uses the same pattern:

1. Build a normal Matplotlib figure.
2. Call `style_figure(...)`.
3. Edit in the GUI.
4. Export a style patch.
5. Reuse the patch later with `mode="apply"`.

## Editor overview

The editor window is organized around three main areas:

- **Object list**: detected figure objects, such as the figure, axes, lines, bars, text, legend, and supported patches.
- **Canvas preview**: the live Matplotlib figure.
- **Properties panel**: editable properties for the selected object.

Common actions:

- Select an object from the list or click it on the canvas.
- Change style properties in the properties panel.
- Drag supported objects directly on the canvas.
- Double-click text to edit it inline.
- Use **Add shape** to insert annotations.
- Use **Undo** and **Redo** for recent edits.
- Use **Export style patch** to save a reusable patch.
- Use **Export figure...** to save the current figure as an output file.

## Supported object types

The editor uses an adapter-based architecture. Each adapter is responsible for discovering, editing, highlighting, deleting, and exporting a family of Matplotlib artists.

Currently supported or partially supported object families include:

| Object type | Examples of editable properties |
| --- | --- |
| Figure | width, height, aspect ratio |
| Axes | title, x/y labels, face color, x/y grid visibility |
| X/Y axis | scale, tick start/end/interval, tick label font, color, rotation, label padding |
| Line | visibility, label, color, line width, line style, draw style, marker, marker size, marker fill/edge, alpha |
| Scatter | visibility, label, marker, fill color, edge color, edge width, marker area, alpha |
| Bar series | visibility, label, fill color, edge color, edge width, alpha, hatch, bar width |
| Text | text content, position, rotation, color, font size, weight, style |
| Text group | shared color, font size, weight, style for multiple text labels |
| Legend | visibility, font size, frame, frame alpha, face color, edge color, spacing, draggable position |
| Spine | visibility, color, width |
| Patch / boxplot patch | visibility, fill color, edge color, edge width, alpha, hatch |
| Pie wedge | visibility, fill color, edge color, width, alpha, hatch, center, radius, angles |
| Arrow | visibility, color, line width, style, head size, alpha, saved position |
| Fill region | visibility, fill color, edge color, edge width, alpha, simple editable geometry when available |
| Editor-created shapes | position, size, angle, fill, border, line style, alpha |
| Editor-created text boxes | text, position, rotation, font, box fill, box edge, box alpha |

Visible artists without editing support are listed as read-only `Unsupported: TypeName` entries. This helps distinguish between "the editor did not detect this object" and "the editor detected it, but no adapter supports editing it yet."

## What gets exported

The exported style patch stores serializable properties for supported artists. It does not rewrite your original plotting script.

For example, after editing a figure named `my_plot`, the editor may generate:

```text
styles/my_plot_style_patch.py
```

That file contains:

```python
def apply_style(fig):
    ...
    return fig
```

The patch is applied to a future `Figure` by resolving object paths such as axes, lines, collections, patches, text objects, legends, and editor-created annotations.

## Important limitations

This project is still a prototype. Keep these constraints in mind:

- It does not parse or rewrite your original Python plotting code.
- It mutates the live Matplotlib `Figure` and exports a replayable post-processing patch.
- The generated patch assumes the regenerated figure has a compatible structure. If you reorder lines, remove axes, change containers, or substantially rewrite the plot, the old patch may no longer apply correctly.
- Not every Matplotlib artist is editable yet.
- Some advanced Matplotlib objects may be detected as unsupported.
- The editor is designed for manual final polish, not high-throughput batch styling.
- GUI usage requires a working Qt-capable environment.
- For long-term reproducibility, commit both the original plotting script and the generated style patch.

## Recommended project structure

One practical layout is:

```text
project/
    plots/
        plot_latency.py
        plot_throughput.py
    styles/
        latency_style_patch.py
        throughput_style_patch.py
    figures/
        latency.pdf
        throughput.pdf
```

Each plotting script owns the data and base Matplotlib plot. Each style patch owns the final visual polish.

## Suggested pattern for paper figures

A simple pattern for paper figures is:

```python
from pathlib import Path
import matplotlib.pyplot as plt
from mpl_visual_editor import style_figure

ROOT = Path(__file__).resolve().parent
STYLE_MODE = "edit"  # switch to "apply" when the figure is finalized

fig, ax = plt.subplots(figsize=(7, 4.5))

# 1. Normal plotting code.
ax.plot(...)
ax.set_xlabel(...)
ax.set_ylabel(...)
ax.legend()

# 2. Last-mile visual editing layer.
style_figure(
    fig,
    mode=STYLE_MODE,
    name="latency_cdf",
    source_path=__file__,
    style_dir=ROOT / "styles",
    save_path=ROOT / "figures" / "latency_cdf.pdf",
)
```

During editing, use `STYLE_MODE = "edit"`. For final regeneration, use `STYLE_MODE = "apply"`.

## Development notes

The codebase is organized around small modules:

```text
mpl_visual_editor/
    __init__.py
    workflow.py
    editor.py
    inspector.py
    exporter.py
    refs.py
    snapshots.py
    shapes.py
    fills.py
    adapters/
        base.py
        registry.py
        figure.py
        axes.py
        axis.py
        line.py
        scatter.py
        bar.py
        text.py
        legend.py
        spine.py
        patch.py
        wedge.py
        arrow.py
        fill.py
        shape.py
        unsupported.py
examples/
    demo_line.py
    demo_bar.py
    demo_scatter.py
    demo_cdf.py
    demo_boxplot.py
    demo_pie.py
```

The main design is adapter-based:

- `inspector.py` asks registered adapters to discover editable artists.
- Each adapter returns stable `ArtistRef` objects.
- The editor uses the selected adapter to build the property form and interaction behavior.
- `snapshots.py` converts supported artist properties into serializable dictionaries.
- `exporter.py` writes those dictionaries into a replayable Python module.
- `workflow.py` provides the high-level `style_figure` helper for normal plotting scripts.

To add support for another Matplotlib object type, implement a new adapter and register it in the adapter registry. A good adapter should define how to inspect, highlight, edit, snapshot, export, and reapply the relevant artist properties.

## Roadmap ideas

Possible future improvements:

- Broader adapter coverage for more Matplotlib artist types.
- More robust identity matching when the plot structure changes.
- Better support for error bars, colorbars, heatmaps, images, and complex collections.
- More annotation tools.
- Better batch-mode ergonomics after a style has been finalized.
- Optional preview screenshots or visual regression tests for style patches.
- Improved documentation with screenshots and GIFs.

## Status

This is an early prototype. It is already useful for small, manually polished Matplotlib figures, especially when the figure needs a few final layout, style, or annotation edits. Expect rough edges, and prefer keeping the original plotting code simple and stable while using this editor as a final visual adjustment layer.

## Contributing

Contributions are very welcome.

This project is intentionally small and still incomplete. Many Matplotlib artist types and editing workflows are not supported yet. If you are interested in improving the editor, good starting points include adding new adapters, improving patch export robustness, polishing the GUI, adding examples, or reporting unsupported objects from real figures.
