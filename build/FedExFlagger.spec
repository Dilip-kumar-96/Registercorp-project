# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\Projects\\Registercorp-project\\src\\flagger\\main.py'],
    pathex=['D:\\Projects\\Registercorp-project\\src'],
    binaries=[],
    datas=[('D:\\Projects\\Registercorp-project\\src\\flagger\\dashboard\\templates', 'flagger/dashboard/templates'), ('D:\\Projects\\Registercorp-project\\src\\flagger\\dashboard\\static', 'flagger/dashboard/static'), ('D:\\Projects\\Registercorp-project\\.env.example', '.')],
    hiddenimports=['flask', 'jinja2', 'werkzeug', 'pystray', 'PIL', 'plyer', 'plyer.platforms.win.notification'],
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
    a.binaries,
    a.datas,
    [],
    name='FedExFlagger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
