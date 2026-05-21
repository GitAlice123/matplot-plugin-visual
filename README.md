# Matplotlib Visual Style Editor

A minimal prototype for visually tweaking the style of an existing Matplotlib
`Figure` and exporting the result as a Python post-processing function.

The intended user flow:

```python
from mpl_visual_editor import edit

# Build your normal Matplotlib figure here.
edit(fig)
```

Click **Export style_patch.py** in the editor to generate:

```python
from style_patch import apply_style

apply_style(fig)
```

This prototype does not parse or rewrite your original plotting script. It
inspects the live `Figure`, mutates common Matplotlib artists in place, and
exports a replayable patch.

## Supported in the first prototype

- Axes title, x/y labels, face color, x/y grid visibility
- Line color, width, style, marker, marker size, alpha, label
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
