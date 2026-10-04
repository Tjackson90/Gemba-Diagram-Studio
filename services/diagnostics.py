"""Installation diagnostics and rotating local logs."""
import importlib.metadata
import logging
from logging.handlers import RotatingFileHandler
import platform
import config


def setup_logging():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(config.DATA_DIR/'studio.log', maxBytes=2_000_000,
                                   backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')


def diagnostics():
    from diagrams.video_export import _find_ffmpeg
    lines = [f'Python {platform.python_version()}', platform.platform(),
             f'Data: {config.DATA_DIR}', f'Exports: {config.OUTPUT_DIR}',
             f'FFmpeg: {_find_ffmpeg() or "MISSING"}']
    for package in ('Pillow','numpy','PySide6','customtkinter','sounddevice','soundfile','scipy','pedalboard'):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = 'not installed'
        lines.append(f'{package}: {version}')
    for font in (config.FONT_DISPLAY,config.FONT_BODY,config.FONT_BODY_BOLD):
        lines.append(f'{font}: {config.get_font_path(font) or "MISSING"}')
    return '\n'.join(lines)
