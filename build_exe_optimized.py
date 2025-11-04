#!/usr/bin/env python
"""
優化的 PyInstaller 打包腳本
排除不必要的模組，加快打包速度，減小 exe 大小
"""

import PyInstaller.__main__
import sys

# 排除不需要的大型套件
excludes = [
    'torch',
    'torchvision', 
    'tensorflow',
    'matplotlib',
    'scipy',
    'IPython',
    'jupyter',
    'notebook',
    'nbformat',
    'jedi',
    'parso',
    'zmq',
    'setuptools_scm',
    'pytest',
    'sphinx',
   'PIL.ImageQt',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
]

# 建立排除參數
exclude_args = []
for module in excludes:
    exclude_args.extend(['--exclude-module', module])

# PyInstaller 參數
args = [
    'gui_app.py',
    '--onefile',
    '--noconsole',
    '--name=PDFVerifier',
    '--clean',
    # 排除不需要的模組
    *exclude_args,
    # 隱藏導入（確保GUI模組被包含）
    '--hidden-import=reference_extractor_gui',
    '--hidden-import=gemini_search_client_gui',
    '--hidden-import=utils',
    '--hidden-import=document_processor',
    '--hidden-import=crossref_client',
    # 增加日誌等級以便除錯
    '--log-level=INFO',
]

print("開始優化打包...")
print(f"排除的模組: {', '.join(excludes)}")
print("\n執行 PyInstaller...")

try:
    PyInstaller.__main__.run(args)
    print("\n✓ 打包完成！")
    print("exe 檔案位置: dist\\PDFVerifier.exe")
except Exception as e:
    print(f"\n✗ 打包失敗: {e}")
    sys.exit(1)