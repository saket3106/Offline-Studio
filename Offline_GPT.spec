# -*- mode: python ; coding: utf-8 -*-
import os

clean_path = [
    p for p in os.environ.get("PATH", "").split(os.pathsep)
    if "poppler" not in p.lower() and "conda" not in p.lower()
]
os.environ["PATH"] = os.pathsep.join(clean_path)

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("ui", "ui"), ("assistant_system_prompt.md", ".")],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "PySide6.QtMultimedia",
        "pymupdf",
        "docx",
        "pptx",
        "intelligence",
        "router",
        "validators",
        "math_engine",
        "code_engine",
        "rag_engine",
        "tool_registry",
        "memory_manager",
        "logic_engine",
        "grounding",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy"],
    noarchive=False,
)

bad_dlls = {"icuuc.dll", "icudt78.dll", "icuin.dll", "icudt.dll"}
a.binaries = [x for x in a.binaries if x[0].lower() not in bad_dlls]

pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Offline GPT",
    debug=False,
    console=False,
    upx=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="Offline GPT",
)
