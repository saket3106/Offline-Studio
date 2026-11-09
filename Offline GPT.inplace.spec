# -*- mode: python ; coding: utf-8 -*-


import os
if os.environ.get('OFFLINEGPT_APPROVED_INPLACE_BUILD')!='20261104-owner-approved':
    raise RuntimeError('Fresh owner approval is required; no analysis or build was authorized.')

from pathlib import Path
import sys
canonical=Path(SPECPATH).absolute()
sys.path.insert(0,str(canonical))
from in_place_packaging import validate_build_locations,manifest_inputs,runtime_modules,verify_build_environment
validate_build_locations(canonical,DISTPATH,workpath,specnm)
environment_receipt=os.environ.get('OFFLINEGPT_BUILD_ENV_RECEIPT')
if not environment_receipt:raise RuntimeError('Reviewed process-local native search environment is required')
verify_build_environment(environment_receipt,canonical.parent/'Application')
approved_source=manifest_inputs(canonical)
required_modules=runtime_modules(canonical,approved_source)

from PyInstaller.utils.hooks import collect_all
from runtime_contracts import validate_windows_payload_paths
from agent_packaging import collect_agent_inputs
agent_data,agent_binaries,agent_imports=collect_agent_inputs(canonical/'requirements-agent-windows-py312.lock')
voice_data=[];voice_binaries=[];voice_imports=[]
for package in ['kokoro_onnx','espeakng_loader','phonemizer','onnxruntime']:
    data,binary,hidden=collect_all(package)
    voice_data+=data;voice_binaries+=binary;voice_imports+=hidden

a = Analysis(
    [str(canonical/'app.py')],
    pathex=[str(canonical)],
    binaries=voice_binaries+agent_binaries,
    datas=[(str(canonical/'ui'), 'ui'), (str(canonical/'assistant_system_prompt.md'), '.'), (str(canonical/'codex-rejected-cas.pem'), '.')]+voice_data+agent_data,
    hiddenimports=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel', 'intelligence', 'router', 'validators', 'math_engine', 'code_engine', 'rag_engine', 'tool_registry', 'memory_manager', 'logic_engine', 'grounding','thread_diagnostics','voice_runtime','live_voice','PySide6.QtMultimedia','image_pipeline','workspace_services','integrated_runtime','model_inspection','model_runtime','model_library','document_tools','agent_runtime','agent_mcp','agent_workspace','agent_permissions','agent_desktop','agent_artifacts','agent_memory','agent_resources']+voice_imports+agent_imports+sorted(required_modules),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt uses the unversioned Windows ICU ABI. A Poppler directory on the build
# host PATH contains a same-named ICU DLL with versioned exports. Bundling it
# would shadow Windows ICU and break QtCore before the app can show a window.
a.binaries = [entry for entry in a.binaries if not (entry[0].lower() in {'icuuc.dll','icudt78.dll'} and 'poppler' in entry[1].lower())]
# Deliberate local-only gate, before any EXE is built.
import os
from pathlib import Path
from in_place_packaging import validate_analysis,verify_compiled_application
if os.environ.get('OFFLINEGPT_APPROVED_INPLACE_BUILD')!='20261104-owner-approved':
    raise RuntimeError('Fresh owner approval is required; no build was authorized.')
canonical=Path(SPECPATH).resolve()
installation=canonical.parent/'Application'
release_root=Path(os.environ.get('OFFLINEGPT_RELEASE_ROOT',str(canonical.parent/'Recovery/VoiceRepair20261026'))).absolute()
receipt=Path(os.environ.get('OFFLINEGPT_COMPATIBILITY_RECEIPT',str(release_root/'PACKAGING_COMPATIBILITY.json'))).absolute()
from in_place_packaging import pin_analysis_native_inputs
pin_analysis_native_inputs(a,installation,environment_receipt)
validate_analysis(a,installation,canonical,receipt)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Offline Studio',
    icon=str(canonical/'frontend-source/public/brand/offline-gpt.ico'),
    version=str(canonical/'windows_version_info.txt'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)

import json
compiled_receipt=release_root/'COMPILED_SOURCE_ACCEPTANCE.json'
compiled_receipt.write_text(json.dumps(verify_compiled_application(exe.name,a,canonical,receipt),indent=2),encoding='utf-8')
