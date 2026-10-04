#!/usr/bin/env python3
"""
GembaGuitar Diagram Studio
===========================
Generate branded chord and scale diagrams + audio for the GembaGuitar YouTube channel.

Usage:
    python studio.py                         Launch the GUI
    python studio.py gui                     Launch the GUI (explicit)
    python studio.py chord Am7 --png         Generate Am7 chord diagram
    python studio.py scale A blues --png     Generate A Blues scale diagram
    python studio.py batch chords.txt --png  Batch generate from file

Run `python studio.py --help` for full CLI documentation.
"""

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from cli.commands import main as cli_main


def main():
    from services.diagnostics import setup_logging
    setup_logging()
    if sys.argv[1:] == ["--smoke-test"]:
        from gui.qt_app import run
        run(smoke=True)
        return
    if sys.argv[1:] == ["--legacy-ui"]:
        from gui.app import run
        run()
        return
    # If no arguments, launch GUI
    if len(sys.argv) == 1:
        from gui.qt_app import run
        run()
    else:
        cli_main()


if __name__ == "__main__":
    main()
