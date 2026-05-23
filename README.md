# Matplotlib Visual Style Editor

A minimal prototype for visually tweaking the style of an existing Matplotlib
`Figure` and exporting the result as a Python post-processing function.

The intended user flow is to keep plotting code unchanged, then pass the
finished `Figure` through `style_figure`:

```python
from mpl_visual_editor import style_figure

# Build your normal Matplotlib figure here.
style_figure(
    fig,
    mode="edit",  # "edit": open GUI; "apply": apply saved patch; "off": raw plot.
    name="my_plot",
    source_path=__file__,
)
```

Click **Export style patch** in the editor to generate a replayable patch:

```text
styles/my_plot_style_patch.py
```

Use the generated patch later by switching the mode:

```python
style_figure(
    fig,
    mode="apply",
    name="my_plot",
    source_path=__file__,
)
```

For continued editing, keep exporting to the same patch. The next time you use
`mode="edit"`, the editor automatically applies that plot's existing patch
first, so the window opens from your last saved style instead of the raw figure.

You can also choose a custom patch:

```python
style_figure(fig, mode="edit", style_path="styles/my_figure_style.py")
```

The editor will reopen from `styles/my_figure_style.py` next time and overwrite
that same file when you export.

If you want to ignore an existing patch and edit the raw figure, use:

```python
style_figure(fig, mode="edit", apply_existing=False)
```

If you only want to open the GUI directly without the workflow helpers, use:

```python
from mpl_visual_editor import edit

edit(fig)
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
- Ordinary `ax.text(...)` labels, such as values above bars, including group
  style controls for shared font/color/weight/style changes
- Legend visibility, font size, frame, frame alpha, frame colors
- Spine visibility, color, width
- Unsupported visible artists are listed as read-only `Unsupported: TypeName`
  entries so you can tell whether an object was detected but lacks an adapter.

## Install

Requires Python 3.9 or newer.

For local development, install the project in editable mode from the repository
root:

```bash
pip install -e .
```

After that, scripts can import `mpl_visual_editor` like a normal Python package
without modifying `sys.path`.

For a regular local install, use:

```bash
pip install .
```

## Demo

```bash
python examples/demo_line.py
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
    refs.py
    adapters/
        base.py
        registry.py
        figure.py
        axes.py
        axis.py
        text.py
        line.py
        bar.py
        legend.py
        spine.py
        unsupported.py
examples/
    demo_line.py
    demo_bar.py
README.md
pyproject.toml
requirements.txt
```

## Adapter architecture

The inspector uses artist adapters instead of a single growing `if/elif` chain.
Each adapter discovers one family of Matplotlib objects and returns stable
`ArtistRef` paths. New component support should be added by creating another
adapter, then wiring its form/edit/export behavior through the same registry.

## Notes

This is intentionally small. It favors a clear object inspector and exporter
over broad artist coverage. Future versions can add scatter, errorbar,
colorbar, image artists, patches, colormaps, and safer object identity matching.
