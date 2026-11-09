@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "VOICE_SOURCE=%~dp0..\whisper-assets"
set "VOICE_DEST=%~dp0dist\Offline GPT"
if exist "%~dp0..\offline-gpt-build-env\Scripts\python.exe" (
  "%~dp0..\offline-gpt-build-env\Scripts\python.exe" -c "import PySide6, PyInstaller, pymupdf, docx, pptx" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=%~dp0..\offline-gpt-build-env\Scripts\python.exe"
)
if not defined PYTHON_EXE (
  py -3.12 -c "import PySide6, PyInstaller, pymupdf, docx, pptx" >nul 2>nul
  if not errorlevel 1 (set "PYTHON_EXE=py"&set "PYTHON_ARGS=-3.12")
)
if not defined PYTHON_EXE (
  py -3.13 -c "import PySide6, PyInstaller, pymupdf, docx, pptx" >nul 2>nul
  if not errorlevel 1 (set "PYTHON_EXE=py"&set "PYTHON_ARGS=-3.13")
)
if not defined PYTHON_EXE (
  echo Build prerequisites are missing. Install Python 3.12 or 3.13, PySide6, and PyInstaller first.
  echo This script does not download packages.
  pause
  exit /b 1
)
if not exist "%VOICE_SOURCE%\whisper-server-win32-x64-cuda.zip" (
  echo The local Whisper server archive was not found in ..\whisper-assets.
  pause
  exit /b 1
)
if not exist "%VOICE_SOURCE%\ggml-large-v3-turbo-q5_0.bin" (
  echo The local Whisper model was not found in ..\whisper-assets.
  pause
  exit /b 1
)
if not exist "%~dp0ui\index.html" (
  echo The bundled React UI was not found in ui\index.html.
  echo Build frontend-source with pnpm and copy its dist files into ui first.
  pause
  exit /b 1
)
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import os; os.environ['PATH']=os.pathsep.join(p for p in os.environ.get('PATH','').split(os.pathsep) if 'poppler' not in p.casefold()); from PyInstaller.__main__ import run; run(['--noconfirm','--clean','--windowed','--onedir','--contents-directory','.','--name','Offline GPT','--add-data','ui;ui','--add-data','assistant_system_prompt.md;.','--hidden-import','PySide6.QtWebEngineCore','--hidden-import','PySide6.QtWebEngineWidgets','--hidden-import','PySide6.QtWebChannel','--hidden-import','intelligence','--hidden-import','router','--hidden-import','validators','--hidden-import','math_engine','--hidden-import','code_engine','--hidden-import','rag_engine','--hidden-import','tool_registry','--hidden-import','memory_manager','--hidden-import','logic_engine','--hidden-import','grounding','app.py'])"
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
rem Qt6Core imports the unversioned Windows ICU ABI. PyInstaller can pick up ICU 78
rem from the Poppler runtime, whose suffixed exports do not match Qt6Core.
if exist "%VOICE_DEST%\icuuc.dll" del /q "%VOICE_DEST%\icuuc.dll"
if exist "%VOICE_DEST%\icudt78.dll" del /q "%VOICE_DEST%\icudt78.dll"
if not exist "%~dp0..\stable-diffusion\sd-cli.exe" (
  echo The sibling stable-diffusion runtime folder was not found.
  echo Keep the Offline GPT and stable-diffusion folders side by side before building.
  pause
  exit /b 1
)
robocopy "%~dp0..\stable-diffusion" "%VOICE_DEST%\stable-diffusion" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
  echo Could not copy the direct Flux image runtime into dist.
  pause
  exit /b 1
)
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import os,shutil,zipfile; from pathlib import Path; src=Path(os.environ['VOICE_SOURCE']); dst=Path(os.environ['VOICE_DEST']); dst.mkdir(parents=True,exist_ok=True); archive=zipfile.ZipFile(src/'whisper-server-win32-x64-cuda.zip'); incoming=archive.open('whisper-server-win32-x64-cuda.exe'); outgoing=(dst/'whisper-server.exe').open('wb'); shutil.copyfileobj(incoming,outgoing,1024*1024); outgoing.close(); incoming.close(); archive.close(); shutil.copy2(src/'ggml-large-v3-turbo-q5_0.bin',dst/'ggml-large-v3-turbo-q5_0.bin')"
if errorlevel 1 (
  echo Could not bundle the local Whisper server and model.
  pause
  exit /b 1
)
for %%F in (llama-server.exe llama-server-impl.dll mtmd.dll llama.dll llama-common.dll ggml-base.dll ggml-cpu.dll ggml-cuda.dll ggml_llamacpp.dll cublas64_12.dll cublasLt64_12.dll cudart64_12.dll libomp.dll MSVCP140.dll VCRUNTIME140.dll VCRUNTIME140_1.dll VCOMP140.dll) do (
  if not exist "%~dp0%%F" (
    echo The bundled local GPT-OSS runtime file is missing: %%F
    pause
    exit /b 1
  )
  copy /Y "%~dp0%%F" "%VOICE_DEST%\%%F" >nul
  if errorlevel 1 (
    echo Could not bundle the local GPT-OSS runtime file: %%F
    pause
    exit /b 1
  )
)
echo Built the UI executable under dist\Offline GPT.
echo The direct Flux runtime was copied inside dist\Offline GPT\stable-diffusion.
echo The app uses its bundled llama.cpp runtime for GPT-OSS and Qwen3-VL.
echo Keep the model weights and projector in the app folder, or choose their local paths in Settings.
pause
