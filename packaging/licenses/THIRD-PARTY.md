# Qt desktop runtime

This application uses unmodified PySide6 (Qt for Python) 6.11.2 and the Qt
libraries supplied by its official binary wheels. The runtime is dynamically
linked; its shared libraries remain separate in `_internal/PySide6`. Users may
replace these libraries with compatible modified builds for their own use.

Qt for Python licensing: https://doc.qt.io/qtforpython-6/licenses.html
Qt licensing and source downloads: https://www.qt.io/licensing/open-source-lgpl-obligations
Qt source archives: https://download.qt.io/archive/qt/
PySide source: https://code.qt.io/cgit/pyside/pyside-setup.git/

The LGPLv3 and GPLv3 license texts are included beside this notice. Package
metadata and the original font licenses are bundled separately. No changes were
made to the Qt or PySide libraries. The application does not restrict reverse
engineering for debugging modifications to these libraries.
