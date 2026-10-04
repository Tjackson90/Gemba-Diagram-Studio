# Build from the repository root: pyinstaller packaging/GembaStudio.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
root = Path(SPECPATH).parent
metadata = []
for package in ('PySide6','Pillow','numpy','scipy','sounddevice','soundfile','customtkinter'):
    metadata += copy_metadata(package)
a = Analysis([str(root / 'studio.py')], pathex=[str(root)],
             datas=[(str(root / 'fonts'), 'fonts'), (str(root / 'packaging' / 'licenses'), 'licenses'),
                    (str(root / 'audio' / 'samples'), 'audio/samples')]
                   + collect_data_files('customtkinter') + metadata,
             hiddenimports=['PIL._tkinter_finder'], hookspath=[],
             excludes=['pytest', 'ruff'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='GembaStudio',
          console=False, debug=False)
coll = COLLECT(exe, a.binaries, a.datas, name='GembaStudio')
