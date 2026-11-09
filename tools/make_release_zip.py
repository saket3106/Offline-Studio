"""Build the public Windows package: the installed Application without any personal data, plus an empty
Models layout with instructions.

Usage:  python tools/make_release_zip.py v1.1.0 [out_dir]
Writes OfflineStudio-<version>-win64.zip (default out_dir: the OfflineGPT folder). Attach it to a GitHub release;
GitHub limits each attached file to 2 GiB."""
import fnmatch, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # OfflineGPT\ (this file is OfflineGPT\Source\tools\)
APP = ROOT / 'Application'
version = sys.argv[1]
out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT
TOP = 'OfflineStudio'

# Personal data and machine-specific state never leave this PC.
EXCLUDE_DIRS = {'generated', 'backups', 'logs', 'cache', 'thumbnails', 'attachments', 'input', 'output', 'diagnostics',
                'profiles', 'test-profiles', 'knowledge', 'memory', 'projects', 'agent-workspaces'}
EXCLUDE_FILES = ['chat.db', 'offline_gpt.sqlite3*', 'offline_gpt_config.json*', '*.dpapi', 'assistant_outbox.json',
                 '*crash.log', '*.log', '*.bak', '*.bak-*', '*.tmp', 'Offline GPT.exe.bak*', 'Offline Studio.exe.bak*']

MODELS_README = """Put model files in these folders. Offline Studio finds them by file name.

Chat\\    chat model (GGUF), e.g. Qwen3.5-9B-Q4_K_M.gguf, Qwen3-4B-Q4_K_M.gguf or gpt-oss-20b-MXFP4.gguf
Vision\\  Qwen3VL-8B-Instruct-Q4_K_M.gguf + mmproj-Qwen3VL-8B-Instruct-F16.gguf (image understanding)
Image\\   flux-2-klein-base-9b-Q4_K_M.gguf, Qwen3-8B-Q4_K_S.gguf, flux2-vae.safetensors, 4x-UltraSharp.pth
Whisper\\ ggml-large-v3-turbo-q5_0.bin (voice input)

See the README on GitHub for download links: https://github.com/saket3106/OfflineGPT
"""


# whisper/ ships older copies of the CUDA libraries that already sit in the Application root (the app puts the root
# on PATH when it starts the voice server; verified on GPU), plus demo tools the app never runs.
WHISPER_SKIP = {'cublas64_12.dll', 'cublaslt64_12.dll', 'cudart64_12.dll', 'nvblas64_12.dll', 'whisper-command.exe',
                'whisper-lsp.exe', 'whisper-quantize.exe', 'whisper-stream.exe', 'whisper-talk-llama.exe',
                'whisper-vad-speech-segments.exe', 'llama.dll', 'parakeet.dll', 'sdl2.dll'}


def skipped(rel: Path) -> bool:
    if rel.parts[0] == 'whisper' and rel.name.lower() in WHISPER_SKIP:
        return True
    if rel.parts[:2] == ('kokoro', 'cache'):  # spoken replies cached on this PC
        return True
    if rel.parts[0] in EXCLUDE_DIRS and len(rel.parts) > 1:
        return True
    return any(fnmatch.fnmatch(rel.name, pattern) for pattern in EXCLUDE_FILES) and len(rel.parts) == 1


out_dir.mkdir(parents=True, exist_ok=True)
target = out_dir / f'OfflineStudio-{version}-win64.zip'
count = size = 0
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
    for path in sorted(APP.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(APP)
        if skipped(rel):
            continue
        z.write(path, f'{TOP}/Application/{rel.as_posix()}')
        count += 1; size += path.stat().st_size
    z.writestr(f'{TOP}/Application/kokoro/cache/', '')
    for group in ('Chat', 'Vision', 'Image', 'Whisper'):
        z.writestr(f'{TOP}/Models/{group}/.keep', '')
    z.writestr(f'{TOP}/Models/README.txt', MODELS_README)
    z.writestr(f'{TOP}/START HERE.txt', 'Open Application\\Offline Studio.exe.\nPut your models in the Models folder first (see Models\\README.txt).\n')
if target.stat().st_size >= 2**31:
    print('WARNING: larger than the 2 GiB GitHub release limit')
print(f'{count} files, {size/1e9:.2f} GB raw -> {target.stat().st_size/1e9:.2f} GB zip: {target}')
