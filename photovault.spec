# photovault.spec
# PyInstaller packaging config for PhotoVault
# Build: pyinstaller photovault.spec
# Output: dist/PhotoVault.app (macOS) or dist/PhotoVault/ (folder)

from PyInstaller.building.api import PYZ, EXE, COLLECT
from PyInstaller.building.build_main import Analysis

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "customtkinter",
        "PIL._tkinter_finder",
        "pymobiledevice3",
        "tkcalendar",
        "pillow_heif",
        "piexif",
        "src.gui.screen1_connect",
        "src.gui.screen2_destination",
        "src.gui.screen3_dates",
        "src.gui.screen4_summary",
        "src.gui.screen5_progress",
        "src.gui.screen6_complete",
        "src.gui.screen7_delete",
        "src.device.mock_device",
        "src.device.iphone_device",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PhotoVault",
)
