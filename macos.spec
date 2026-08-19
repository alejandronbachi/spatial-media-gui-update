# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')], # Correctly bundles your dark theme icons folder tree
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'shiboken6'], # Safely blocks PySide6 clashing dependencies
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SpatialMediaBatchInjector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # Hides the raw macOS terminal shell popup window at launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Bakes your native Apple app icon format cleanly into the App Bundle frame
    icon=['assets/icons/app_icon.icns'], 
)

# Mac-specific App Bundle construction wrapper required by macOS CoreGraphics runtimes
app = BUNDLE(
    exe,
    name='SpatialMediaBatchInjector.app',
    icon='assets/icons/app_icon.icns',
    bundle_identifier='alejandronbachi.spatialmedia.batchinjector',
)
