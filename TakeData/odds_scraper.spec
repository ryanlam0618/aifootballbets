# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# 收集所有 Playwright 相關模塊
datas, binaries, hiddenimports = collect_all('playwright')

# OddsHarvester 路徑
import os
odds_src = os.path.join(os.path.dirname(os.path.abspath(SPEC)), '..', 'OddsHarvester', 'src')
datas += [(odds_src, 'src')]

a = Analysis(
    ['odds_batch_scraper.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'src.main',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='odds_batch_scraper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
