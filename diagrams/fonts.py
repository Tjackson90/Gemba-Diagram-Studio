"""Bundled fonts, including explicit variable-font weight selection."""
from functools import lru_cache
from PIL import ImageFont
import config


@lru_cache(maxsize=128)
def load_font(font_file, size):
    size = max(8, int(size))
    path = config.get_font_path(font_file)
    if not path:
        raise FileNotFoundError(f'Bundled font missing: {font_file}')
    font = ImageFont.truetype(path, size)
    if 'DMSans' in path:
        axes = font.get_variation_axes()
        values = [axis['default'] for axis in axes]
        for i, axis in enumerate(axes):
            if axis['name'] == b'Weight':
                values[i] = 700 if font_file == config.FONT_BODY_BOLD else 400
        font.set_variation_by_axes(values)
    return font
