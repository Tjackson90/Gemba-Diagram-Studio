"""
Export utility — resolution scaling, background compositing, file saving.
"""

from PIL import Image
from pathlib import Path
import config


def export_diagram(
    diagram_img,
    output_path,
    resolution="1080p",
    background="transparent",
    custom_size=None,
):
    """
    Export a diagram image at the specified resolution and background.

    Args:
        diagram_img: PIL.Image.Image (RGBA) — the rendered diagram
        output_path: str or Path — output file path (.png)
        resolution: "1080p", "4K", "Square", "Square 4K", or "Custom"
        background: "transparent" or "navy"
        custom_size: (width, height) tuple if resolution is "Custom"

    Returns:
        Path to the saved file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine target size
    if custom_size:
        target_w, target_h = custom_size
    elif resolution in config.RESOLUTIONS:
        target_w, target_h = config.RESOLUTIONS[resolution]
    else:
        target_w, target_h = config.RESOLUTIONS["1080p"]

    # Scale diagram to fit within target resolution while maintaining aspect ratio
    config.validate_size(target_w, target_h)
    if 'render_spec' in diagram_img.info:
        from services.documents import render_spec
        diagram_img = render_spec(diagram_img.info['render_spec'], (target_w, target_h))
    src_w, src_h = diagram_img.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    scaled = diagram_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Create canvas at target resolution
    if background == 'theme':
        canvas = Image.new('RGBA', (target_w,target_h), diagram_img.info.get('background','#12161c'))
    elif background == "navy":
        canvas = Image.new("RGBA", (target_w, target_h), config.NAVY_DEEP + (255,))
    else:
        canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    # Center the diagram on the canvas
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    canvas.alpha_composite(scaled.convert("RGBA"), (offset_x, offset_y))

    # Save
    canvas.save(str(output_path), "PNG")
    return output_path


def batch_export(
    diagram_img,
    base_name,
    output_dir,
    resolutions=None,
    backgrounds=None,
):
    """
    Export a diagram in multiple resolutions and backgrounds.

    Args:
        diagram_img: PIL.Image.Image (RGBA)
        base_name: base filename without extension (e.g., "Am7")
        output_dir: directory to save files
        resolutions: list of resolution keys, or None for all
        backgrounds: list of "transparent"/"navy", or None for both

    Returns:
        list of saved file paths
    """
    if resolutions is None:
        resolutions = list(config.RESOLUTIONS.keys())
    if backgrounds is None:
        backgrounds = ["transparent", "navy"]

    output_dir = Path(output_dir)
    saved = []

    for res in resolutions:
        for bg in backgrounds:
            suffix = f"_{res}_{bg}"
            from services.storage import safe_filename, unique_path
            filename = f"{safe_filename(base_name)}{suffix}.png"
            path = export_diagram(diagram_img, unique_path(output_dir / filename), res, bg)
            saved.append(path)

    return saved
