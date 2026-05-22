# Matplotlib Visual Style Editor

A minimal prototype for visually tweaking the style of an existing Matplotlib
`Figure` and exporting the result as a Python post-processing function.

The intended user flow:

```python
from mpl_visual_editor import edit

# Build your normal Matplotlib figure here.
edit(fig)
```

Click **Export style patch** in the editor to generate a patch next to the
calling script:

```text
examples/demo_basic.py -> examples/demo_basic_style_patch.py
examples/demo_bar.py   -> examples/demo_bar_style_patch.py
```

Use the generated patch from normal plotting code:

```python
from examples.demo_basic_style_patch import apply_style

apply_style(fig)
```

For continued editing, keep exporting to the same patch. The next time you call
`edit(fig)`, the editor automatically applies that script-specific patch first,
so the window opens from your last saved style instead of the raw figure.

You can also choose a custom patch:

```python
edit(fig, export_path="styles/my_figure_style.py")
```

The editor will reopen from `styles/my_figure_style.py` next time and overwrite
that same file when you export.

If you want to ignore an existing patch and edit the raw figure, use:

```python
edit(fig, apply_existing=False)
```

Use **Export figure...** in the editor to write the currently styled figure as
PDF, PNG, SVG, JPEG, or TIFF.

This prototype does not parse or rewrite your original plotting script. It
inspects the live `Figure`, mutates common Matplotlib artists in place, and
exports a replayable patch.

## Supported in the first prototype

- Axes title, x/y labels, face color, x/y grid visibility
- Line color, width, style, marker, marker size, alpha, label
- Bar series visibility, label, fill color, edge color, edge width, alpha, hatch, width
- Text content, color, size, weight, style
- Legend visibility, font size, frame, frame alpha, frame colors
- Spine visibility, color, width

## Install

```bash
pip install -r requirements.txt
```

## Demo

```bash
python examples/demo_basic.py
```

```bash
python examples/demo_bar.py
```

## Project layout

```text
mpl_visual_editor/
    __init__.py
    editor.py
    inspector.py
    exporter.py
examples/
    demo_basic.py
README.md
requirements.txt
```

## Notes

This is intentionally small. It favors a clear object inspector and exporter
over broad artist coverage. Future versions can add image artists, patches,
tick styling, colormaps, and safer object identity matching.
