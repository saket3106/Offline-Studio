"""Private local GPT-OSS inference and one-shot image runtime management."""



from __future__ import annotations







import ctypes



import hashlib



import json



import os



import subprocess



import sys



import threading



import time



import re



import shutil



import socket



import queue



import http.client



import io



import select



import urllib.error



import urllib.parse



import urllib.request



import secrets



import logging



from contextlib import contextmanager



from pathlib import Path



from runtime_contracts import ExistingTextAdapter



from model_runtime import ModelInfo, ModelBehavior, Family, EngineTextRuntime, TemplateContentStream, model_display_name







APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(os.environ.get("OFFLINE_STUDIO_DEV_APP_DIR") or Path(__file__).resolve().parent).resolve()



_runtime_logger = logging.getLogger("offline_gpt.runtime")











class EmptyVisibleResponseError(RuntimeError):



    """Completion ended but contained no safe user-facing assistant text."""











def structured_agent_format(schema,behavior,tools):



    if schema is None:return None



    if behavior.harmony or tools or not isinstance(schema,dict):



        raise ValueError('Structured Agent output requires a non-Harmony, tool-free bundled request.')



    encoded=json.dumps(schema,allow_nan=False)



    if len(encoded.encode('utf-8'))>16384:raise ValueError('Agent response schema exceeds its bounded budget.')



    return {'type':'json_object','schema':json.loads(encoded)}











class ToolCallCompletion:



    """A model requested local tools and needs an assistant continuation."""







    def __init__(self, calls):



        self.calls = list(calls or [])



CONFIG_PATH = Path(os.environ.get("OFFLINE_GPT_DATA_DIR",str(APP_DIR))) / "offline_gpt_config.json"



DEFAULT_CONFIG = {



    "chat_model": "openai/gpt-oss-20b",



    "chat_backend": "bundled",



    # Retained as inert migration data for older profiles.  OfflineGPT's



    # normal configuration always uses the application-owned bundled runtime.



    "lms_exe": "",



    "chat_url": "http://127.0.0.1:1234/v1",



    "chat_gpu": "auto",



    "chat_gpu_layers": -1,



    "chat_context": 4096,



    "chat_system_prompt_path": "assistant_system_prompt.md",



    "chat_validation_retries": 2,



    "gpt_oss_gguf": "gpt-oss-20b-MXFP4.gguf",



    "vision_model": "Qwen3VL-8B-Instruct-Q4_K_M.gguf",



    "vision_projector": "mmproj-Qwen3VL-8B-Instruct-F16.gguf",



    "vision_context": 4096,



    "sd_cli": "stable-diffusion/sd-cli.exe",



    "flux_model": "flux-2-klein-base-9b-Q4_K_M.gguf",



    "flux_encoder": "Qwen3-8B-Q4_K_S.gguf",



    "flux_vae": "flux2-vae.safetensors",



    "flux_upscaler": "4x-UltraSharp.pth",



    "image_output_directory": "generated",



    "flux_width": 1024,



    "flux_height": 576,



    "image_output_format": "png",



    "image_jpeg_quality": 96,



    "flux_steps": 20,



    "flux_quality_preset": "balanced",

    "flux_detail_level": "standard",

    # One smart chat box: research only when a message needs it (the first search still asks).
    "intelligence_mode": "hybrid",



    "flux_cfg_scale": 4.0,



    "flux_threads": 4,



    "flux_backend": "auto",



    "flux_memory": "low",



    "upscale_repeats": 1,



    "voice_server_path": "whisper-server.exe",



    "voice_model_path": "ggml-large-v3-turbo-q5_0.bin",



    "voice_cuda_runtime_path": "stable-diffusion",



    "voice_threads": 4,



    "voice_language": "auto",



    "voice_device_id": "",



    "voice_vad_sensitivity": "medium",



    "voice_transcription_mode": "streaming",



    "model_lifecycle_mode": "balanced",



    "model_keepalive_seconds": 90,



    "emergency_ram_threshold_mb": 256,



}











def load_config():



    if CONFIG_PATH.exists():



        try:



            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))



        except Exception as exc:



            raise RuntimeError(f"Cannot read {CONFIG_PATH}: {exc}") from exc



    else:



        saved = {}



    result = {**DEFAULT_CONFIG, **saved}



    # Keep the bundled engine as the default; the external engine is opt-in.



    legacy_bundled = str(result.get("chat_model", "")).strip().lower() in {"", "gpt-oss-20b-local"}



    if legacy_bundled:



        result["chat_model"] = DEFAULT_CONFIG["chat_model"]



    # Older profiles may contain the removed external-backend selection.  Do



    # not allow that value to make the desktop app depend on another AI



    # application; the bundled llama.cpp runtime is the sole normal route.



    requested_backend = str(result.get("chat_backend", "bundled")).strip().lower()



    result["chat_backend"] = "bundled"



    if requested_backend == "lmstudio":



        result["chat_backend_migration"] = "external_backend_reset_to_bundled"



    result["chat_url"] = "http://127.0.0.1:1234/v1"



    try:



        result["chat_context"] = max(2048, min(8192, int(result.get("chat_context", 4096))))



    except (TypeError, ValueError):



        result["chat_context"] = 4096



    if result["chat_backend"] == "bundled":



        result["chat_context"] = min(4096, result["chat_context"])



    try:



        result["chat_validation_retries"] = max(0, min(3, int(result.get("chat_validation_retries", 2))))



    except (TypeError, ValueError):



        result["chat_validation_retries"] = 2



    result["chat_system_prompt_path"] = str(result.get("chat_system_prompt_path", "assistant_system_prompt.md")).strip() or "assistant_system_prompt.md"



    cpu_requested=str(saved.get('chat_gpu','')).lower()=='cpu' or type(saved.get('chat_gpu_layers')) is int and saved['chat_gpu_layers']==0



    result["chat_gpu_layers"] = 0 if cpu_requested else -1



    result["chat_gpu"] = "cpu" if cpu_requested else "auto"



    result["vision_model"] = str(result.get("vision_model", "")).strip()



    try:



        result["vision_context"] = max(2048, min(8192, int(result.get("vision_context", 4096))))



    except (TypeError, ValueError):



        result["vision_context"] = 4096



    result["model_lifecycle_mode"] = str(result.get("model_lifecycle_mode", "balanced")).strip().lower()



    if result["model_lifecycle_mode"] not in {"low_ram", "balanced", "fast"}:



        result["model_lifecycle_mode"] = "balanced"



    try:



        result["model_keepalive_seconds"] = max(0, int(result.get("model_keepalive_seconds", 90)))



    except (TypeError, ValueError):



        result["model_keepalive_seconds"] = 90



    try:



        result["emergency_ram_threshold_mb"] = max(128, int(result.get("emergency_ram_threshold_mb", 256)))



    except (TypeError, ValueError):



        result["emergency_ram_threshold_mb"] = 256



    result["flux_quality_preset"] = str(result.get("flux_quality_preset", "balanced")).strip().lower()



    if str(result.get("flux_detail_level", "standard")).strip().lower() not in {"standard", "detailed", "high", "extreme"}:

        result["flux_detail_level"] = "standard"

    if result["flux_quality_preset"] not in {"fast", "balanced", "quality"}:



        result["flux_quality_preset"] = "balanced"



    try:



        raw_steps = int(result.get("flux_steps", 20))



        if raw_steps == 12:



            preset_steps = {"fast": 14, "balanced": 20, "quality": 28}



            result["flux_steps"] = preset_steps.get(result["flux_quality_preset"], 20)



        else:



            result["flux_steps"] = max(1, min(100, raw_steps))



    except (TypeError, ValueError):



        result["flux_steps"] = 20



    return result











def save_config(value):



    # A crash must not expose partially written model/settings JSON to readers.



    import tempfile



    descriptor,name=tempfile.mkstemp(prefix='.offline-gpt-config-',suffix='.tmp',dir=CONFIG_PATH.parent)



    try:



        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:



            json.dump(value,stream,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())



        os.replace(name,CONFIG_PATH)



    finally:



        try:os.unlink(name)



        except FileNotFoundError:pass











def resolve_path(value):



    path = Path(value).expanduser()



    if path.is_absolute():



        return path.resolve()



    candidate = (APP_DIR / path).resolve()



    if candidate.exists():



        return candidate



    for folder in ("Application", "Offline GPT"):



        alternative = (APP_DIR.parent / folder / path).resolve()



        if alternative.exists():



            return alternative



    # Only exact bare resource names and the historical Whisper-model spelling



    # may use the central Models layout; never discard arbitrary user subpaths.



    bare = len(path.parts) == 1



    whisper_model = len(path.parts) == 3 and tuple(p.casefold() for p in path.parts[:2]) == ("whisper", "models")



    if bare:



        server = (APP_DIR.parent / "Application" / "whisper" / path.name).resolve()



        if path.name.casefold() == "whisper-server.exe" and server.is_file():



            return server



    if (bare or whisper_model) and path.suffix.casefold() in {".gguf", ".safetensors", ".pth", ".onnx", ".bin"}:



        for group in ("Chat", "Vision", "Image", "Whisper"):



            model = (APP_DIR.parent / "Models" / group / path.name).resolve()



            if model.is_file():



                return model



    return candidate











def physical_memory_status():



    if os.name != "nt":



        return {"total": None, "available": None, "pagefile_total": None, "pagefile_available": None, "load_percent": None}







    class _MemoryStatus(ctypes.Structure):



        _fields_ = [



            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),



            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),



            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),



            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),



            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),



        ]







    status = _MemoryStatus()



    status.dwLength = ctypes.sizeof(status)



    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):



        return {"total": None, "available": None, "pagefile_total": None, "pagefile_available": None, "load_percent": None}



    return {



        "total": int(status.ullTotalPhys),



        "available": int(status.ullAvailPhys),



        "pagefile_total": int(status.ullTotalPageFile),



        "pagefile_available": int(status.ullAvailPageFile),



        "load_percent": int(status.dwMemoryLoad),



    }











def _local_memory_profile(memory, requested_context, hardware_profile='balanced', custom_options=None):



    """Choose context, batch, threads and commit that leave room for the local runtime."""



    gib = 1024 ** 3



    mib = 1024 ** 2



    available_ram = memory.get("available")



    available_commit = memory.get("pagefile_available")



    if available_ram is None:



        raise RuntimeError("Windows could not report free physical memory, so local model loading was stopped safely.")



    if available_ram < 256 * mib:



        free = available_ram / gib



        raise RuntimeError(



            f"Windows has only {free:.1f} GB of free physical RAM. The local model needs at least 256 MB to start its local runtime; "



            "free some memory, then retry."



        )







    hw_profile = str(hardware_profile or 'balanced').strip().lower()



    if hw_profile not in {'eco', 'balanced', 'performance', 'custom'}:



        hw_profile = 'balanced'







    requested_context = max(512, min(32768, int(requested_context)))



    total_ram = memory.get('total')



    cpu_cores = os.cpu_count() or 4







    if hw_profile == 'eco':



        context = min(requested_context, 2048)



        batch = 32



        threads = max(1, min(2, cpu_cores - 1))



    elif hw_profile == 'performance':



        context = min(requested_context, 8192)



        batch = 128



        threads = max(1, min(8, max(2, cpu_cores - 1)))



    elif hw_profile == 'custom' and isinstance(custom_options, dict):



        context = min(32768, max(512, int(custom_options.get('context', requested_context))))



        batch = min(512, max(16, int(custom_options.get('batch', 64))))



        threads = min(16, max(1, int(custom_options.get('threads', 4))))



    else:  # balanced



        if available_ram < int(1.5 * gib):



            context, batch, threads = min(requested_context, 2048), 32, 2



        elif available_ram < int(3.5 * gib):



            context, batch, threads = min(requested_context, 3072), 64, 3



        elif available_ram < int(6 * gib):



            context, batch, threads = min(requested_context, 4096), 64, 4



        else:



            context, batch, threads = min(requested_context, 4096), 64, min(4, max(2, cpu_cores - 2))







    # Constrained profile bounds for machines with total_ram <= 18 GiB



    if total_ram is not None and total_ram <= 18 * gib and available_ram < 9 * gib:



        if hw_profile == 'eco':



            context = min(context, 2048); batch = min(batch, 32); threads = min(threads, 2)



        elif hw_profile == 'balanced':



            # Context follows the free-RAM tiers above (2048 below 1.5 GiB, 3072



            # below 3.5 GiB). A blanket 2048 clamp here silently halved the



            # 4096 shown in Settings and truncated answers and history.



            batch = min(batch, 64); threads = min(threads, 4)







    runtime_commit = int((1.25 + 0.5 * context / 4096) * gib)



    if available_commit is not None and available_commit < runtime_commit:



        current = f"{available_commit / gib:.1f} GB"



        raise RuntimeError(



            f"The selected local model profile needs about {runtime_commit / gib:.1f} GB of Windows memory-commit headroom "



            f"for the selected context; {current} is available. Increase the Windows paging-file limit or free memory, then retry."



        )







    load_mode = "none" if total_ram is not None and total_ram <= 18 * gib else "mmap"



    return {



        "context": context, "batch": batch, "threads": threads,



        "commit": runtime_commit, "load_mode": load_mode,



        "hardware_profile": hw_profile,



    }











def available_cuda_memory():



    """Return the largest free CUDA device memory amount reported by the driver."""



    executable = shutil.which("nvidia-smi")



    if not executable:



        return None



    try:



        result = subprocess.run(



            [executable, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],



            capture_output=True, text=True, timeout=3,



            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),



        )



        if result.returncode:



            return None



        values = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]



        return int(max(values) * 1024**2) if values else None



    except (OSError, ValueError, subprocess.TimeoutExpired):



        return None











_HARMONY_TERMINATORS = ("<|return|>", "<|end|>", "<|fim_suffix|>", "<|ghissue|>", "<|call|>", "<|calls|>")



_CHANNEL_MESSAGE = re.compile(r"<\|channel\|>\s*([^<\s]+)\s*<\|message\|>", re.I)



_ROLE_MESSAGE = re.compile(r"<\|start\|>assistant(?:<\|channel\|>([A-Za-z_-]+))?<\|message\|>", re.I)











def _clean_model_text(value):



    text = str(value or "")



    # Drop only recognized Harmony control tags after channel selection.



    text = re.sub(r"<\|(?:return|end|fim_suffix|ghissue|im_end|eos)\|>", "", text, flags=re.I)



    text = re.sub(r"<\|[^|]+\|>", "", text)



    return text.strip()











def _segment_text(raw, start, next_header=None):



    boundaries = [len(raw)]



    if next_header is not None:



        boundaries.append(next_header)



    for token in _HARMONY_TERMINATORS:



        index = raw.find(token, start)



        if index >= 0:



            boundaries.append(index)



    other_start = raw.find("<|start|>", start)



    if other_start >= 0:



        boundaries.append(other_start)



    return _clean_model_text(raw[start:min(boundaries)])











_SELF_PREFACES=('we need to recall','we need to answer','we need to analyze','we need to analyse','we need to reason','we need to respond','we need to determine','we need to solve','we need to check','we should answer','we should respond',"let's think","let's analyze","let's analyse")







def _self_instructional_output(text):



    value=str(text).lstrip().lower()



    return any(value.startswith(prefix) for prefix in _SELF_PREFACES) and bool(re.search(r"\b(?:let.s (?:produce|write|output)|final answer|we need to keep|we should answer|the user (?:asks|wants))\b",value))







def parse_visible_assistant_output(value):



    """Select final or safe assistant text without ever falling back to reasoning."""



    raw = str(value or "")



    raw = re.sub(r"\s*<!--offlinegpt-image-plan:[A-Za-z0-9_-]+-->\s*$", "", raw)



    channel_matches = list(_CHANNEL_MESSAGE.finditer(raw))



    if channel_matches:



        sections = []



        for index, match in enumerate(channel_matches):



            next_header = channel_matches[index + 1].start() if index + 1 < len(channel_matches) else None



            content = _segment_text(raw, match.end(), next_header)



            sections.append((match.group(1).casefold(), content))



        finals = [content for channel, content in sections if channel == "final" and content]



        if finals:



            return {"text": finals[-1], "explicit_final": True, "reasoning_present": any(channel in {"analysis", "reasoning", "justify", "confidence"} for channel, _ in sections)}



        has_reasoning = any(channel in {"analysis", "reasoning", "justify", "confidence"} for channel, _ in sections)



        assistant_text = [content for channel, content in sections if channel == "assistant" and content]



        if assistant_text:



            return {"text": assistant_text[-1], "explicit_final": False, "reasoning_present": has_reasoning}



        if has_reasoning:



            return {"text": "", "explicit_final": False, "reasoning_present": True}



        # Unknown channel contents are never guessed to be user-facing.



        return {"text": "", "explicit_final": False, "reasoning_present": False}







    role_matches = list(_ROLE_MESSAGE.finditer(raw))



    if role_matches:



        allowed = []



        has_reasoning = False



        for index, match in enumerate(role_matches):



            channel = (match.group(1) or "").casefold()



            has_reasoning = has_reasoning or channel in {"analysis", "reasoning", "justify", "confidence"}



            next_header = role_matches[index + 1].start() if index + 1 < len(role_matches) else None



            content = _segment_text(raw, match.end(), next_header)



            if channel == "final" and content:



                return {"text": content, "explicit_final": True, "reasoning_present": has_reasoning}



            if not channel and content:



                allowed.append(content)



        if allowed:



            return {"text": allowed[-1], "explicit_final": False, "reasoning_present": has_reasoning}



        if has_reasoning:



            return {"text": "", "explicit_final": False, "reasoning_present": True}







    # A dangling channel marker is not plain text; failure must trigger recovery.



    if "<|channel|>" in raw.lower() or "<tool_call>" in raw.lower() or "<|recipient|>" in raw.lower():



        return {"text": "", "explicit_final": False, "reasoning_present": "<|channel|>analysis" in raw.lower()}



    if _self_instructional_output(raw):return {"text":"","explicit_final":False,"reasoning_present":True}



    return {"text": _clean_model_text(raw), "explicit_final": False, "reasoning_present": False}











class _HarmonyFinalStream:



    """Stream explicit final text; retain full raw envelope for safe end fallback."""







    marker = "<|channel|>final<|message|>"







    def __init__(self):



        self.raw = ""



        self.emitted = ""







    def feed(self, piece):



        if not piece:



            return ""



        self.raw += piece



        parsed = parse_visible_assistant_output(self.raw)



        if not parsed["explicit_final"]:



            return ""



        text = parsed["text"]



        if text.startswith(self.emitted):



            delta = text[len(self.emitted):]



            self.emitted = text



            return delta



        return ""







    def finish(self):



        parsed = parse_visible_assistant_output(self.raw)



        text = parsed["text"]



        if text.startswith(self.emitted):



            delta = text[len(self.emitted):]



            self.emitted = text



            return delta



        return ""











def visible_assistant_text(value, architecture=None):



    """Return final/safe assistant text, or an empty string for reasoning-only output."""



    if isinstance(architecture,str) and architecture and architecture!='gpt-oss':



        parser=TemplateContentStream();return parser.feed(str(value or ''))+parser.finish()



    return parse_visible_assistant_output(value)["text"]











_CACHED_LOCAL_TOOL_SCHEMAS = None











def _local_tool_schemas(allowed_tools=None):



    """Describe only the app's existing, locally executed tools to chat APIs.



    If allowed_tools is an empty list or set, return [].



    If allowed_tools is specified, filter to only those tool names.



    If allowed_tools is None, return all tools (cached).



    """



    global _CACHED_LOCAL_TOOL_SCHEMAS



    if allowed_tools is not None and len(allowed_tools) == 0:



        return []



    if _CACHED_LOCAL_TOOL_SCHEMAS is None:



        from tool_registry import ToolRegistry



        _CACHED_LOCAL_TOOL_SCHEMAS = [



            {



                "type": "function",



                "function": {



                    "name": item["name"],



                    "description": item["description"],



                    "parameters": item["parameters"],



                },



            }



            for item in ToolRegistry().describe_tools()



        ]



    if allowed_tools is None:



        return list(_CACHED_LOCAL_TOOL_SCHEMAS)



    allowed_set = set(allowed_tools)



    return [s for s in _CACHED_LOCAL_TOOL_SCHEMAS if s["function"]["name"] in allowed_set]











def _merge_tool_call_deltas(target, deltas):



    """Accumulate OpenAI-compatible streamed tool-call fields by index."""



    for item in deltas or []:



        if not isinstance(item, dict):



            continue



        index = item.get("index", 0)



        try:



            index = int(index)



        except (TypeError, ValueError):



            index = 0



        call = target.setdefault(index, {"id": "", "name": "", "arguments": ""})



        if item.get("id"):



            call["id"] = str(item["id"])



        function = item.get("function") or {}



        name = function.get("name") or item.get("name")



        if name:



            call["name"] += str(name)



        raw_args = function.get("arguments") if "arguments" in function else item.get("arguments")



        if raw_args is not None:



            if isinstance(raw_args, (dict, list)):



                call["arguments"] = json.dumps(raw_args)



            else:



                call["arguments"] += str(raw_args)











def _normalized_tool_calls(calls):



    """Validate streamed tool-call JSON before it reaches the local registry."""



    normalized = []



    for index, item in sorted((calls or {}).items()):



        name = str(item.get("name") or "").strip()



        if not name:



            continue



        raw_args = item.get("arguments")



        if isinstance(raw_args, dict):



            arguments = raw_args



        elif isinstance(raw_args, str):



            try:



                arguments = json.loads(raw_args)



            except (TypeError, ValueError):



                try:



                    import ast



                    arguments = ast.literal_eval(raw_args)



                except Exception:



                    arguments = {}



        else:



            arguments = {}



        if not isinstance(arguments, dict):



            arguments = {}



        normalized.append({



            "id": str(item.get("id") or f"offline-tool-{index + 1}"),



            "name": name,



            "arguments": arguments,



        })



    return normalized











_HARMONY_TAG_PREFIXES = ("<|channel", "<|start", "<|return", "<|end", "<|call", "<|calls", "<|im_end", "<|fim_suffix", "<|ghissue")











class _VisibleChatStream:



    """Pass normal completion text through and filter GPT-OSS Harmony channels."""







    def __init__(self):



        self.mode = "detect"



        self.pending = ""



        self.plain_tail = ""



        self.harmony = _HarmonyFinalStream()







    def _feed_plain(self, value, final=False):



        source = self.plain_tail + str(value or "")



        self.plain_tail = ""



        opening = source.rfind("<|")



        closing = source.rfind("|>")



        if not final and opening > closing:



            candidate = source[opening:].lower()



            if any(candidate.startswith(p) or p.startswith(candidate) for p in _HARMONY_TAG_PREFIXES):



                self.plain_tail = source[opening:]



                source = source[:opening]



        elif final and opening > closing:



            tail = source[opening:]



            if not any(token.startswith(tail) for token in _HARMONY_TERMINATORS):



                source = source[:opening] + tail



            else:



                source = source[:opening]



        return re.sub(r"<\|[^|]+\|>", "", source)







    def feed(self, value):



        if not value:



            return ""



        if self.mode == 'quarantine':



            self.pending += value



            if '<|channel|>' in self.pending or '<|start|>assistant' in self.pending:



                self.mode='harmony';pending,self.pending=self.pending,''



                return self.harmony.feed(pending)



            return ''



        if self.mode == "plain":



            return self._feed_plain(value)



        if self.mode == "harmony":



            return self.harmony.feed(value)



        self.pending += value



        if "<|channel|>" in self.pending.lower() or "<|start|>assistant" in self.pending.lower():



            self.mode = "harmony"



            pending, self.pending = self.pending, ""



            return self.harmony.feed(pending)



        lowered=self.pending.lstrip().lower()



        if not lowered:return ''



        if lowered and any(lowered.startswith(prefix) for prefix in _SELF_PREFACES):



            self.mode='quarantine';return ''



        if lowered and any(prefix.startswith(lowered) for prefix in _SELF_PREFACES):return ''



        # Keep a trailing '<' only if it could begin a Harmony tag.



        if self.pending.endswith("<"):



            result, self.pending = self.pending[:-1], "<"



            if result:



                self.mode = "plain"



                return self._feed_plain(result)



            return ""



        self.mode = "plain"



        result, self.pending = self.pending, ""



        return self._feed_plain(result)







    def finish(self):



        if self.mode == 'quarantine':return parse_visible_assistant_output(self.pending)['text']



        if self.mode == "harmony":



            return self.harmony.finish()



        result, self.pending = self.pending, ""



        return self._feed_plain(result, final=True)











# Live Voice keeps Whisper on the GPU: with the default 512 MiB fit target the 9B chat model left

# 300-460 MiB free on an 8 GB GPU, so Whisper ran on the CPU (12.5 s per turn vs 0.2-0.4 s).

VOICE_VRAM_RESERVE_MB = 1400



# Helper servers (chat, Whisper, image) must not outlive the app. A crash or a forced close left

# a 9B llama-server and Whisper servers running, holding ~5 GB of GPU memory, so the next launch

# ran Whisper on the CPU (12 s per spoken turn). Windows kill-on-close job + startup sweep.

HELPER_SERVER_NAMES = ('llama-server.exe', 'whisper-server.exe', 'sd-server.exe', 'sd-cli.exe')

_CHILD_JOB = None



def tie_child_to_app(process):

    """Put a helper process in a kill-on-close job object owned by this app (Windows). Returns True when tied."""

    global _CHILD_JOB

    if os.name != 'nt' or process is None or not getattr(process, '_handle', None):

        return False

    try:

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)

        k32.CreateJobObjectW.restype = ctypes.c_void_p; k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]

        k32.SetInformationJobObject.restype = ctypes.c_int; k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]

        k32.AssignProcessToJobObject.restype = ctypes.c_int; k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        k32.CloseHandle.argtypes = [ctypes.c_void_p]

        if _CHILD_JOB is None:

            class Basic(ctypes.Structure):

                _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', ctypes.c_uint32),

                            ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),

                            ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32), ('SchedulingClass', ctypes.c_uint32)]

            class Io(ctypes.Structure):

                _fields_ = [(name, ctypes.c_uint64) for name in ('Read', 'Write', 'Other', 'ReadBytes', 'WriteBytes', 'OtherBytes')]

            class Extended(ctypes.Structure):

                _fields_ = [('Basic', Basic), ('Io', Io), ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),

                            ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

            job = k32.CreateJobObjectW(None, None)

            if not job:

                return False

            info = Extended(); info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # JobObjectExtendedLimitInformation

                k32.CloseHandle(job); return False

            _CHILD_JOB = job

        return bool(k32.AssignProcessToJobObject(_CHILD_JOB, int(process._handle)))

    except Exception:

        return False



def stop_orphaned_helpers(app_dir, names=HELPER_SERVER_NAMES):

    """Terminate helper servers from this app folder whose parent app process is gone. Returns their PIDs.

    A parent PID can be reused by an unrelated process, so a parent that started after the child also counts as gone."""

    if os.name != 'nt':

        return []

    stopped = []

    try:

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)

        class Entry(ctypes.Structure):

            _fields_ = [('dwSize', ctypes.c_uint32), ('cntUsage', ctypes.c_uint32), ('th32ProcessID', ctypes.c_uint32), ('th32DefaultHeapID', ctypes.c_size_t),

                        ('th32ModuleID', ctypes.c_uint32), ('cntThreads', ctypes.c_uint32), ('th32ParentProcessID', ctypes.c_uint32),

                        ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_uint32), ('szExeFile', ctypes.c_wchar * 260)]

        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p; k32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

        k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]; k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        k32.OpenProcess.restype = ctypes.c_void_p; k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]

        k32.CloseHandle.argtypes = [ctypes.c_void_p]; k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

        k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]

        k32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_uint64)] * 4

        def started(pid):

            handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION

            if not handle:

                return None

            try:

                created, a, b, c = (ctypes.c_uint64() for _ in range(4))

                return created.value if k32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(a), ctypes.byref(b), ctypes.byref(c)) else None

            finally:

                k32.CloseHandle(handle)

        snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)

        if not snapshot or snapshot == ctypes.c_void_p(-1).value:

            return []

        entries = []

        try:

            entry = Entry(); entry.dwSize = ctypes.sizeof(Entry)

            ok = k32.Process32FirstW(snapshot, ctypes.byref(entry))

            while ok:

                entries.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))

                ok = k32.Process32NextW(snapshot, ctypes.byref(entry))

        finally:

            k32.CloseHandle(snapshot)

        root = os.path.normcase(str(Path(app_dir).resolve()))

        wanted = {name.lower() for name in names}

        for pid, parent, exe in entries:

            if exe.lower() not in wanted or pid == os.getpid():

                continue

            child_started = started(pid); parent_started = started(parent)

            if child_started is None or (parent_started is not None and parent_started <= child_started):

                continue

            handle = k32.OpenProcess(0x1000 | 0x0001, False, pid)  # query + PROCESS_TERMINATE

            if not handle:

                continue

            try:

                size = ctypes.c_uint32(1024); buffer = ctypes.create_unicode_buffer(1024)

                if not k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):

                    continue

                if not os.path.normcase(buffer.value).startswith(root + os.sep):

                    continue

                if k32.TerminateProcess(handle, 1):

                    stopped.append(pid)

            finally:

                k32.CloseHandle(handle)

    except Exception:

        return stopped

    return stopped



def chat_fit_target_mb(projector=False, reserve_mb=0):

    """MiB llama.cpp --fit leaves free on the GPU: the base margin plus any reservation (Live Voice)."""

    return (1024 if projector else 512) + max(0, int(reserve_mb or 0))



def _loaded_fit_target(runtime, projector=False):

    """Fit target the running server was started with (unknown: the default margin, no reservation)."""

    value = getattr(runtime, 'loaded_fit_target', None)

    return value if type(value) is int else chat_fit_target_mb(projector, 0)



class _LocalLlamaServer:



    """App-owned llama.cpp runtime with a loopback-only, hidden child process."""







    CONTEXT = 4096



    MAX_OUTPUT = 2400



    CPU_MOE_LAYERS = None







    def __init__(self, log_dir):



        self.log_dir = Path(log_dir)



        self.process = None



        self.model_path = ""



        self.projector_path = ""



        self.log_filename = "llama-server.log"



        self.context = self.CONTEXT



        self.port = None



        self.api_key = ""



        self.log_handle = None



        self._request_lock = threading.Lock()



        self.last_generation_diagnostics = {}



        self.behavior=ModelBehavior()



        self._behavior_observation=None



        # Private model transport must never inherit a system or environment



        # proxy. It is restricted to the app-owned loopback endpoint.



        self._local_opener=urllib.request.OpenerDirector()



        for handler in (urllib.request.HTTPHandler(),urllib.request.HTTPDefaultErrorHandler(),urllib.request.HTTPErrorProcessor()):



            self._local_opener.add_handler(handler)



        if os.environ.get('OFFLINE_GPT_THREAD_DIAGNOSTICS')=='1':



            try:urllib.request.build_opener(urllib.request.ProxyHandler({}))



            except OSError:_runtime_logger.exception('Default urllib opener initialization failed; private HTTP-only transport is isolated from it')



        self.last_health_error=''







    def inspect_behavior(self,path):



        """Bind format to observed metadata, not to a model's filename.







        Legacy configurations remain usable when static inspection cannot run;



        that fallback is explicitly not new-model compatibility evidence.



        """



        import model_inspection



        try:



            _,info=model_inspection.ordinary_file(path);observation=model_inspection.identity(info)



            key=(str(path),observation)



            if self._behavior_observation==key:return



            descriptor=ModelInfo.from_inspection(model_inspection.inspect_gguf(path))



            self.behavior=ModelBehavior.from_model(descriptor)



            self.model_descriptor=descriptor



            self._behavior_observation=key



            self.behavior_inspection_error=''



        except (OSError,ValueError) as exc:



            # A failed inspection cannot authorize Harmony formatting or



            # attribute another selected model to the legacy GPT-OSS adapter.



            self.behavior=ModelBehavior(Family.OTHER,Path(path).stem,'inspection_failed')



            self.model_descriptor=None



            self._behavior_observation=None



            self.behavior_inspection_error=str(exc)[:300]







    def _log_generation_diagnostics(self, details):



        """Write local diagnostics without persisting hidden reasoning text."""



        self.last_generation_diagnostics = dict(details or {})



        self.log_dir.mkdir(exist_ok=True)



        path = self.log_dir / "intelligence.log"



        try:



            with path.open("a", encoding="utf-8", errors="replace") as stream:



                stream.write(json.dumps({"event": "chat_generation", **self.last_generation_diagnostics}, ensure_ascii=False) + "\n")



        except OSError as exc:



            _runtime_logger.warning("Could not append chat generation diagnostics: %s", exc)







    @staticmethod



    def _server_binary():



        for candidate in (APP_DIR / "llama-server.exe", APP_DIR / "_internal" / "llama-server.exe"):



            if candidate.is_file():



                return candidate



        raise RuntimeError("Offline GPT's bundled local inference engine is missing. Repair the app package and keep its runtime files together.")







    @staticmethod



    def _port():



        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:



            probe.bind(("127.0.0.1", 0))



            return int(probe.getsockname()[1])







    @staticmethod



    def _runtime_dependencies():



        return (



            "llama-server-impl.dll", "mtmd.dll", "llama.dll", "llama-common.dll",



            "ggml-base.dll", "ggml-cpu.dll", "ggml-cuda.dll", "ggml_llamacpp.dll",



            "cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll",



            "libomp.dll", "MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll",



            "VCOMP140.dll",



        )







    def _check_runtime_files(self):



        missing = [name for name in self._runtime_dependencies() if not (APP_DIR / name).is_file()]



        if missing:



            raise RuntimeError("Offline GPT's local inference runtime is incomplete: " + ", ".join(missing))







    @property



    def ready(self):



        return bool(self.process and self.process.poll() is None and self.port)







    def _url(self, path):



        return f"http://127.0.0.1:{self.port}{path}"







    @staticmethod



    def _read_error(response):



        try:



            detail = response.read().decode("utf-8", "replace")



        except Exception:



            detail = ""



        return detail[-1800:]







    def _json_request(self, path, payload, timeout=30, cancel_event=None):



        """Bound one owned loopback request, including slow headers/body reads.







        The caller is an existing inference worker. Poll only this request's



        reads: Windows buffered socket reads are not reliably interrupted by



        another thread calling shutdown. No result escapes after cancellation.



        """



        EngineManager._raise_if_cancelled(cancel_event)



        if not 0 < timeout <= 30:



            raise ValueError('Prompt request timeout must be within 30 seconds.')



        headers = {"Content-Type": "application/json"}



        if self.api_key:



            headers["Authorization"] = "Bearer " + self.api_key



        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')



        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=min(timeout, .5))



        deadline = time.monotonic() + timeout







        def check_request():



            EngineManager._raise_if_cancelled(cancel_event)



            if time.monotonic() >= deadline:



                raise TimeoutError('Prompt request deadline exceeded.')







        class RequestReader(io.RawIOBase):



            def __init__(reader, owned_socket):



                reader.socket = owned_socket



                reader.socket.setblocking(False)



            def readable(reader): return True



            def readinto(reader, buffer):



                while True:



                    check_request()



                    if select.select([reader.socket], [], [], min(.02, max(0, deadline-time.monotonic())))[0]:



                        try:



                            size = reader.socket.recv_into(buffer)



                        except BlockingIOError:



                            continue



                        check_request()



                        return size



            def close(reader):



                try: reader.socket.close()



                finally: super().close()







        class ResponseSocket:



            def __init__(wrapper, sock): wrapper.socket = sock



            def makefile(wrapper, mode):



                # HTTP/1.0 closes the connection before consuming its body.



                # The response owns its duplicate until its buffered reader closes.



                return io.BufferedReader(RequestReader(wrapper.socket.dup()))







        connection.response_class = lambda sock, **options: http.client.HTTPResponse(ResponseSocket(sock), **options)



        try:



            connection.connect()



            check_request()



            connection.request('POST', path, body=body, headers=headers)



            with connection.getresponse() as response:



                # Token arrays and rendered templates are bounded independently



                # of Content-Length, which an unhealthy server may omit/lie about.



                limit = 16 * 1024 * 1024



                data = response.read(limit + 1)



                check_request()



                if len(data) > limit:



                    raise ValueError('Prompt response exceeds 16 MiB.')



                if not 200 <= response.status < 300:



                    detail = data.decode('utf-8', 'replace')[-1800:]



                    raise RuntimeError(f'Local GPT-OSS preflight failed ({response.status}). {detail}'.strip())



                result = json.loads(data.decode('utf-8'))



                EngineManager._raise_if_cancelled(cancel_event)



                return result



        except (OSError, ValueError, http.client.HTTPException) as exc:



            EngineManager._raise_if_cancelled(cancel_event)



            raise RuntimeError(f"Could not check the local GPT-OSS prompt: {exc}") from exc



        finally:



            connection.close()







    def _is_healthy(self):



        if not self.ready:



            return False



        try:



            with self._local_opener.open(self._url("/health"), timeout=1.5) as response:



                return response.status == 200



        except Exception:



            return False







    def _log_tail(self):



        try:



            return "\n".join((self.log_dir / self.log_filename).read_text(encoding="utf-8", errors="replace").splitlines()[-12:])[-1600:]



        except OSError:



            return ""







    def start(self, model_path, context, gpu_layers, progress, cancel_event=None, memory_profile=None, projector_path=None):



        target = str(Path(model_path).resolve())



        projector = str(Path(projector_path).resolve()) if projector_path else ""



        layers=self.gpu_layer_argument(gpu_layers)



        observation=self.file_observation(target)



        projector_observation=self.file_observation(projector) if projector else None



        cached=getattr(self,'model_descriptor',None)



        if isinstance(cached,ModelInfo) and getattr(self,'model_file_observation',None)==observation and cached.context_limit:



            context=min(int(context),cached.context_limit)



        fit_target=chat_fit_target_mb(bool(projector),getattr(self,'vram_reserve_mb',0))

        if self.model_path == target and self.projector_path == projector and self.context == int(context) and getattr(self,'loaded_gpu_layers',None)==layers and _loaded_fit_target(self,bool(projector))>=fit_target and observation is not None and getattr(self,'model_file_observation',None)==observation and (not projector or projector_observation is not None and getattr(self,'projector_file_observation',None)==projector_observation) and self._is_healthy():



            return



        self.stop()



        server = self._server_binary()



        self._check_runtime_files()



        if not Path(target).is_file():



            raise RuntimeError(f"Local GGUF model was not found: {target}. Choose the model file in Settings.")



        if projector and not Path(projector).is_file():



            raise RuntimeError(f"Qwen3-VL projector was not found: {projector}. Choose the matching mmproj file in Settings.")



        self.inspect_behavior(target)



        descriptor=getattr(self,'model_descriptor',None)



        if not isinstance(descriptor,ModelInfo):



            raise RuntimeError('The selected model metadata could not be verified; no inference was started. '+str(getattr(self,'behavior_inspection_error','')))



        if projector:



            from model_inspection import inspect_gguf



            from model_runtime import vision_pair_conflict



            projector_metadata=inspect_gguf(projector)['metadata']



            conflict=vision_pair_conflict(descriptor.metadata,projector_metadata)



            if conflict:raise RuntimeError(conflict+' Choose the matching vision pair; no model was loaded.')



            if self.file_observation(projector)!=projector_observation:



                raise RuntimeError('Vision projector changed during verification; retry with stable local assets.')



        if isinstance(descriptor,ModelInfo) and descriptor.context_limit:



            context=min(int(context),descriptor.context_limit)



            if context<512:raise RuntimeError('The selected model declares a context below the supported 512-token application minimum.')



        self.port = self._port()



        self.context = int(context)



        self.model_path = target



        self.loaded_gpu_layers=layers

        self.loaded_fit_target=fit_target



        self.model_file_observation=observation



        self.projector_path = projector



        self.projector_file_observation = projector_observation



        self.log_filename = "llama-vision.log" if projector else "llama-server.log"



        self.api_key = secrets.token_urlsafe(32)



        self.session_id = secrets.token_hex(12)



        batch = 256 if projector else max(32, min(512, int((memory_profile or {}).get("batch", 256))))



        ubatch = 128 if projector else max(32, min(256, int((memory_profile or {}).get("ubatch", batch // 2))))



        self.log_dir.mkdir(exist_ok=True)



        log_path = self.log_dir / self.log_filename



        try:



            self.log_handle = log_path.open("w", encoding="utf-8", errors="replace")



            env = os.environ.copy()



            env["PATH"] = str(APP_DIR) + os.pathsep + env.get("PATH", "")



            command = [



                str(server), "-m", target, "-c", str(self.context),



                "-b", str(batch), "-ub", str(ubatch), "-np", "1", "-ngl", self.gpu_layer_argument(gpu_layers),



                "--fit", "on", "--fit-target", str(fit_target), "--load-mode",



                "mmap" if projector else (memory_profile or {}).get("load_mode", "mmap"), "--jinja",



                "--flash-attn", "on",



            ]



            threads=max(1,min(16,int((memory_profile or {}).get('threads',4))))



            command.extend(['-t',str(threads),'-tb',str(threads)])



            # The bundled server defaults to an 8 GiB host prompt cache. Keep



            # active-slot prompt reuse, but bound extra snapshots on laptops.



            cache_ram=max(0,min(512,int((memory_profile or {}).get('cache_ram_mb',128))))



            command.extend(['--cache-ram',str(cache_ram)])



            if projector:



                command.extend(["--mmproj", projector])



            elif self.behavior.harmony:



                command.extend(["--reasoning-effort", "low"])



            command.extend(["--no-ui", "--api-key", self.api_key,



                            "--host", "127.0.0.1", "--port", str(self.port)])



            progress("Starting Offline GPT's private local vision engine…" if projector else f"Starting the private local {self.behavior.model_alias} engine…")



            self.process = subprocess.Popen(



                command, cwd=str(APP_DIR), env=env, stdin=subprocess.DEVNULL,



                stdout=self.log_handle, stderr=subprocess.STDOUT,



                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),



            )



            tie_child_to_app(self.process)



            started = time.monotonic()



            deadline = started + 300



            next_update = started + 8



            critical_ram_ticks = 0



            while time.monotonic() < deadline:



                EngineManager._raise_if_cancelled(cancel_event)



                if self.process.poll() is not None:



                    detail = self._log_tail()



                    raise RuntimeError("Offline GPT's local model engine stopped during load." + (f"\n{detail}" if detail else ""))



                memory = physical_memory_status()



                avail = memory.get("available")



                page_avail = memory.get("pagefile_available")



                if avail is not None and avail < 256 * 1024 * 1024:



                    critical_ram_ticks += 1



                    if critical_ram_ticks >= 6:



                        self.stop()



                        target_name = Path(target).name if target else "Local model"



                        raise RuntimeError(f"{target_name} loading was stopped because less than 256 MiB of physical RAM remained. The model and chats are unchanged; release other memory or use a smaller context before retrying.")



                else:



                    critical_ram_ticks = 0



                try:



                    with self._local_opener.open(self._url("/health"), timeout=1.0) as response:



                        if response.status == 200:



                            if self.file_observation(target)!=self.model_file_observation:



                                raise RuntimeError('The selected model changed while loading. Stop editing it and retry; no prior allocation may be reused.')



                            return



                except urllib.error.HTTPError as exc:



                    if exc.code not in (503, 502):



                        detail = self._read_error(exc)



                        raise RuntimeError(f"The local model engine returned HTTP {exc.code}. {detail}".strip()) from exc



                except (OSError, TimeoutError) as exc:



                    detail=f'{type(exc).__name__}: {exc}'[:300]



                    if detail!=self.last_health_error:



                        self.last_health_error=detail



                        _runtime_logger.warning('Private model health transport: %s',detail)



                if time.monotonic() >= next_update:



                    elapsed = int(time.monotonic() - started)



                    progress(f"Loading selected model locally · {elapsed // 60}m {elapsed % 60}s elapsed…"+(f" Health transport: {self.last_health_error}" if self.last_health_error else ""))



                    next_update = time.monotonic() + 8



                time.sleep(0.25)



            detail = self._log_tail()



            raise RuntimeError("The local GPT-OSS engine did not finish loading within five minutes." + (f"\n{detail}" if detail else ""))



        except Exception:



            self.stop()



            raise







    @staticmethod



    def file_observation(path):



        try:



            info=Path(path).stat()



            return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)



        except OSError:return None







    @staticmethod



    def gpu_layer_argument(value):



        if value=='auto' or type(value) is int and value==-1:return 'auto'



        if type(value) is int and 0<=value<=1024:return str(value)



        raise ValueError('GPU layers must be auto or a bounded nonnegative integer.')







    @staticmethod



    def _copy_messages(messages):



        copied = []



        for message in messages:



            item = {"role": str(message.get("role", "user"))}



            if "content" in message:



                item["content"] = message.get("content")



            for key in ("name", "tool_calls", "tool_call_id"):



                if key in message:



                    item[key] = message[key]



            copied.append(item)



        return copied







    @staticmethod



    def _document_excerpt(content, target_chars):



        match = re.search(r"\n(?:\s*)document text\s*:\s*\n", content, re.IGNORECASE)



        if not match:



            return None



        header, body = content[:match.end()], content[match.end():]



        body = re.sub(r"^\[Relevant excerpts selected from a longer local document; the source file was not changed\.\]\s*", "", body)



        target_chars = min(int(target_chars), max(64, len(body) - 180))



        if len(body) <= target_chars:



            return None



        query = set(re.findall(r"[a-z0-9]{4,}", header.lower()))



        chunks = []



        for paragraph in re.split(r"\n\s*\n", body):



            paragraph = paragraph.strip()



            if not paragraph:



                continue



            max_piece = max(500, min(1600, target_chars // 3))



            for offset in range(0, len(paragraph), max_piece):



                part = paragraph[offset:offset + max_piece].strip()



                words = re.findall(r"[a-z0-9]{4,}", part.lower())



                overlap = sum(1 for word in words if word in query)



                chunks.append((overlap, len(chunks), part))



        if not chunks:



            return None



        selected = []



        used = 0



        for score, index, part in sorted(chunks, key=lambda item: (-item[0], item[1])):



            if selected and used + len(part) + 2 > target_chars:



                continue



            if len(part) > target_chars and not selected:



                part = part[:target_chars]



            if used + len(part) <= target_chars:



                selected.append((index, part))



                used += len(part) + 2



        if not selected:



            selected = [(chunks[0][1], chunks[0][2][:target_chars])]



        chosen = "\n\n".join(part for _, part in sorted(selected))



        return header + "[Relevant excerpts selected from a longer local document; the source file was not changed.]\n" + chosen







    def _prompt_tokens(self, messages, cancel_event=None):



        EngineManager._raise_if_cancelled(cancel_event)



        request_options = {'cancel_event': cancel_event} if cancel_event is not None else {}



        template_request={"messages":messages}



        kwargs=self.behavior.template_kwargs(getattr(self,'_active_template_effort','low'))



        if kwargs:template_request['chat_template_kwargs']=kwargs



        if getattr(self,'_active_template_tools',None):template_request['tools']=self._active_template_tools



        templated = self._json_request("/apply-template", template_request, timeout=30, **request_options)



        prompt = templated.get("prompt") if isinstance(templated, dict) else None



        if not isinstance(prompt, str):



            raise RuntimeError("The local GPT-OSS runtime could not apply the model's chat template.")



        tokenized = self._json_request("/tokenize", {"content": prompt, "add_special": False, "parse_special": True}, timeout=30, **request_options)



        tokens = tokenized.get("tokens") if isinstance(tokenized, dict) else None



        if not isinstance(tokens, list):



            raise RuntimeError("The local GPT-OSS runtime could not count prompt tokens.")



        return len(tokens)







    def _fit_messages(self, messages, max_tokens, progress, cancel_event):



        working = self._copy_messages(messages)



        original = self._copy_messages(messages)



        self.last_prompt_fit = {}



        transformations=[]



        def finish(count,output,shortened):



            def ids(items):



                return sorted(set(re.findall(r'"id"\s*:\s*"(M\d+)"','\n'.join(m.get('content','') for m in items if isinstance(m.get('content'),str)))))[:128]



            encoded=json.dumps(working,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')



            self.last_prompt_fit={'context_shortened':shortened,'context_limit':self.context,



                'prompt_tokens':count,'output_tokens':output,'original_message_count':len(original),



                'fitted_message_count':len(working),'fitted_messages_sha256':hashlib.sha256(encoded).hexdigest(),



                'source_json_ids_before':ids(original),'source_json_ids_after':ids(working),



                'source_ids_are_presence_only':True,'transformations':transformations[:24]}



            return working,count,output,shortened



        if not working:



            raise RuntimeError("There is no message to send to the local model.")



        min_output_reserve = 128



        target_output = min(self.MAX_OUTPUT, max(min_output_reserve, int(max_tokens)))



        # Preserve the requested completion budget. The old fixed 128-token



        # reserve admitted oversized prompts and then clipped otherwise valid



        # answers at generation time, especially for multi-part requests.



        prompt_budget = self.context - target_output - 16



        impossible_reservation = target_output > self.context - min_output_reserve - 16



        shortened = False



        while True:



            EngineManager._raise_if_cancelled(cancel_event)



            count = self._prompt_tokens(working, cancel_event=cancel_event) if cancel_event is not None else self._prompt_tokens(working)



            if impossible_reservation and count <= self.context - min_output_reserve - 16:



                # A 2400-token export request cannot reserve 2400 tokens in a



                # 2048-token runtime. Preserve the entire fitting prompt and



                # use its actual remaining capacity instead of stripping the



                # instructions and rejecting even a 143-token prompt.



                actual_output = min(target_output, self.context - count - 16)



                progress(f'Using {actual_output:,} answer tokens within the local {self.context:,}-token context.')



                return finish(count,actual_output,shortened)



            if count <= prompt_budget:



                actual_output = max(min_output_reserve, min(target_output, self.context - count - 16))



                return finish(count,actual_output,shortened)



            first_history = 1 if working[0]["role"] == "system" else 0



            user_positions = [index for index, item in enumerate(working) if item.get("role") == "user"]



            current_user = user_positions[-1] if user_positions else len(working) - 1



            if first_history < current_user:



                # Drop a complete old turn, including any attached tool result



                # messages, while preserving the latest user request and its



                # tool-call continuation context.



                end = first_history + 1



                while end < current_user and working[end].get("role") != "user":



                    end += 1



                transformations.append({'kind':'older_turns_dropped','message_count':end-first_history})



                del working[first_history:end]



                shortened = True



                continue



            last_tool = next((index for index in range(len(working) - 1, current_user, -1)



                              if working[index].get("role") == "tool" and isinstance(working[index].get("content"), str)), None)



            if last_tool is not None and len(working[last_tool]["content"]) > 512:



                content = working[last_tool]["content"]



                keep = max(256, int(len(content) * 0.65))



                working[last_tool]["content"] = content[:keep // 2] + "\n[…local tool output shortened…]\n" + content[-(keep - keep // 2):]



                transformations.append({'kind':'tool_output_shortened','original_chars':len(content),'fitted_chars':len(working[last_tool]['content'])})



                shortened = True



                continue



            last = working[current_user] if current_user < len(working) else working[-1]



            content = last.get("content")



            if not isinstance(content, str):



                content = ""



            excerpt = self._document_excerpt(content, max(500, int(len(content) * 0.65)))



            if excerpt:



                last["content"] = excerpt



                transformations.append({'kind':'document_excerpt_selected','original_chars':len(content),'fitted_chars':len(excerpt)})



                shortened = True



                continue



            if working[0]["role"] == "system" and isinstance(working[0].get("content"), str) and len(working[0]["content"]) > 200:



                content = working[0]["content"]



                marker = "\n[Older system context shortened to fit the local model window.]\n"



                keep = max(96, int((len(content) - len(marker) - 24) * 0.72))



                head = keep * 2 // 3



                tail = max(0, keep - head)



                working[0]["content"] = content[:head] + marker + (content[-tail:] if tail else "")



                transformations.append({'kind':'system_shortened','original_chars':len(content),'fitted_chars':len(working[0]['content'])})



                shortened = True



                continue



            if count <= self.context - min_output_reserve - 16:



                actual_output = max(min_output_reserve, min(target_output, self.context - count - 16))



                return finish(count, actual_output, shortened)



            raise RuntimeError(



                f"This message needs {count:,} prompt tokens; the local model context is {self.context:,} "



                f"with {min_output_reserve:,} tokens reserved for the answer. Shorten this one message or attached document and retry."



            )







    def _capture_fitted_prompt(self,messages):



        """Explicit diagnostic opt-in, restricted to an external data profile.







        Raw text is never captured by default. This bounded local trace is for



        isolated engineering reproductions; it contains no request headers/key.



        """



        if os.environ.get('OFFLINE_GPT_CAPTURE_FITTED_PROMPTS')!='1':return



        location=os.environ.get('OFFLINE_GPT_DATA_DIR')



        if not location:return



        try:



            profile=Path(location).resolve(strict=True)



            if not profile.is_dir() or profile==APP_DIR.resolve():return



            folder=profile/'logs'



            if folder.is_symlink():return



            folder.mkdir(exist_ok=True)



            path=folder/'fitted-prompts.jsonl'



            if path.is_symlink() or not path.resolve().is_relative_to(profile):return



            size=path.stat().st_size if path.exists() else 0



            row=json.dumps({'time':time.time(),'fit':self.last_prompt_fit,'messages':messages},ensure_ascii=False)+'\n'



            data=row.encode('utf-8')



            if len(data)>64*1024 or size+len(data)>2*1024**2:return



            with path.open('ab') as stream:stream.write(data)



        except (OSError,ValueError,TypeError):



            _runtime_logger.warning('Optional fitted-prompt capture unavailable; inference continues.')







    def complete(self, messages, context, max_tokens, temperature, cancel_event, on_token, progress, memory_profile=None, connection_callback=None, top_p=None, allowed_tools=None, reasoning_effort=None, response_schema=None):



        self.last_generation_diagnostics = {}



        if not self._is_healthy():



            raise RuntimeError("The selected local model engine is not running. Send the message again to restart it.")



        with self._request_lock:



            tools = _local_tool_schemas(allowed_tools)



            response_format=structured_agent_format(response_schema,self.behavior,tools)



            self._active_template_tools=tools;self._active_template_effort=reasoning_effort if reasoning_effort in {'low','medium','high'} else 'low'



            fitted, prompt_tokens, output_tokens, shortened = self._fit_messages(messages, max_tokens, progress, cancel_event)



            self._capture_fitted_prompt(fitted)



            if shortened:



                progress("Keeping recent turns and selecting only the document context that fits; saved chat and source files stay intact…")



            output_tokens = max(1, min(self.MAX_OUTPUT, int(output_tokens)))



            tools = _local_tool_schemas(allowed_tools)



            payload = {



                "model": self.behavior.model_alias, "messages": fitted, "stream": True,



                "max_tokens": output_tokens, "temperature": float(temperature),



                "top_p": float(0.92 if top_p is None else top_p),



                "stream_options": {"include_usage": True},



                "cache_prompt": True,



                "timings_per_token": True,



            }



            payload.update(self.behavior.generation_options(reasoning_effort,output_tokens))



            if response_format is not None:payload['response_format']=response_format



            if tools:



                payload["tools"] = tools



                payload["tool_choice"] = "auto"



            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")



            events = queue.Queue()



            state = {"connection": None}







            def read_stream():



                connection = None



                diagnostics = {



                    "finish_reason": None,



                    "stop_reason": None,



                    "generated_token_count": None,



                    "generated_token_count_source": "not_reported_by_runtime",



                    "raw_output_parts": [],



                    "content_chunk_lengths": [],



                    "reasoning_present": False,



                    "final_present": False,



                    "tool_call_present": False,



                    "tool_calls_by_index": {},



                    "prompt_token_count": prompt_tokens,



                    "context_limit": self.context,



                    "requested_output_tokens": output_tokens,



                    "context_shortened":shortened,"prompt_fit":dict(self.last_prompt_fit),"reasoning_effort":self._active_template_effort,"advertised_tools":[t["function"]["name"] for t in tools],



                }



                try:



                    connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=900)



                    state["connection"] = connection



                    if connection_callback:



                        connection_callback(connection)



                    connection.request("POST", "/v1/chat/completions", body=body, headers={



                        "Content-Type": "application/json", "Authorization": "Bearer " + self.api_key,



                    })



                    response = connection.getresponse()



                    if response.status < 200 or response.status >= 300:



                        events.put(("error", response.read().decode("utf-8", "replace")[-1800:] or f"HTTP {response.status}"))



                        return



                    for raw in response:



                        line = raw.decode("utf-8", "replace").strip()



                        if not line.startswith("data:"):



                            continue



                        data = line[5:].strip()



                        if data == "[DONE]":



                            break



                        try:



                            item = json.loads(data)



                        except json.JSONDecodeError:



                            continue



                        if item.get("error"):



                            events.put(("error", str(item["error"])))



                            return



                        if isinstance(item.get("timings"), dict):



                            diagnostics["timings"]=item["timings"]



                            if diagnostics.get("cached_tokens") in (None, 0) and "cache_n" in item["timings"]:



                                diagnostics["cached_tokens"] = item["timings"]["cache_n"]



                        usage = item.get("usage")



                        if isinstance(usage, dict):



                            if isinstance(usage.get("completion_tokens"), int):



                                diagnostics["generated_token_count"] = usage["completion_tokens"]



                                diagnostics["generated_token_count_source"] = "stream_usage"



                            if isinstance(usage.get("prompt_tokens"), int):



                                diagnostics["prompt_token_count"] = usage["prompt_tokens"]



                            details=usage.get("completion_tokens_details") or {}



                            if isinstance(details.get("reasoning_tokens"),int):diagnostics["reasoning_tokens"]=details["reasoning_tokens"]



                            prompt_tokens_details = usage.get("prompt_tokens_details") or {}



                            if isinstance(prompt_tokens_details, dict) and "cached_tokens" in prompt_tokens_details:



                                diagnostics["cached_tokens"] = prompt_tokens_details["cached_tokens"]



                        choices = item.get("choices") or []



                        if not choices:



                            continue



                        choice = choices[0]



                        if choice.get("finish_reason") is not None:



                            diagnostics["finish_reason"] = choice.get("finish_reason")



                        if choice.get("stop_reason") is not None:



                            diagnostics["stop_reason"] = choice.get("stop_reason")



                        delta = choice.get("delta") or {}



                        if isinstance(delta.get("reasoning"), str) and delta["reasoning"].strip():



                            diagnostics["reasoning_present"] = True



                        if isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"].strip():



                            diagnostics["reasoning_present"] = True



                        if delta.get("tool_calls"):



                            diagnostics["tool_call_present"] = True



                            _merge_tool_call_deltas(diagnostics["tool_calls_by_index"], delta.get("tool_calls"))



                        content = delta.get("content")



                        if isinstance(content, str) and content:



                            diagnostics["raw_output_parts"].append(content)



                            diagnostics["content_chunk_lengths"].append(len(content))



                            if "<|channel|>analysis" in content.lower() or "<|channel|>reasoning" in content.lower():



                                diagnostics["reasoning_present"] = True



                            if _HarmonyFinalStream.marker in content:



                                diagnostics["final_present"] = True



                            if "<tool_call>" in content.lower() or "<|call|>" in content.lower():



                                diagnostics["tool_call_present"] = True



                            events.put(("content", content))



                except Exception as exc:



                    diagnostics["stream_error"] = str(exc)[:400]



                finally:



                    diagnostics["tool_calls"] = _normalized_tool_calls(diagnostics.pop("tool_calls_by_index", {}))



                    diagnostics["raw_output"] = "".join(diagnostics.pop("raw_output_parts", []))



                    events.put(("done", diagnostics))



                    if connection:



                        connection.close()



                    if connection_callback:



                        connection_callback(None)







            reader = threading.Thread(target=read_stream, name="OfflineGPT-local-stream", daemon=True)



            reader.start()



            visible = _VisibleChatStream() if self.behavior.harmony else TemplateContentStream()



            parts = []



            generation_diagnostics = {}



            stream_error = ""



            try:



                progress(f"Reading {prompt_tokens:,} local prompt tokens · reserving {output_tokens:,} answer tokens…")



                while True:



                    EngineManager._raise_if_cancelled(cancel_event)



                    try:



                        kind, value = events.get(timeout=0.25)



                    except queue.Empty:



                        continue



                    if kind == "error":



                        # Older reader events may still use this form. Keep



                        # draining until diagnostics arrive so a partial safe



                        # answer can be preserved and logged.



                        stream_error = str(value)



                        continue



                    if kind == "done":



                        generation_diagnostics = value if isinstance(value, dict) else {}



                        stream_error = stream_error or str(generation_diagnostics.get("stream_error") or "")



                        break



                    text = visible.feed(value)



                    if text:



                        parts.append(text)



                        on_token(text)



                tail = visible.finish()



                if tail:



                    parts.append(tail)



                    on_token(tail)



            except Exception:



                # Stop the app-owned runtime before closing a buffered reader.



                # Socket shutdown releases an outstanding read during prefill.



                if cancel_event is not None and cancel_event.is_set():



                    # This server is app-owned and its request is explicitly



                    # cancelled. Hidden Windows console servers cannot answer



                    # taskkill's polite window-close path; waiting three seconds



                    # there delayed every voice interruption. Still wait for



                    # actual managed-process death before releasing ownership.



                    self.stop(graceful=False)



                    self._log_generation_diagnostics({'finish_reason':'cancelled','prompt_token_count':prompt_tokens,



                        'requested_output_tokens':output_tokens,'generated_token_count':None,



                        'partial_visible_characters':sum(len(p) for p in parts),'timings':{},



                        'prompt_fit':dict(self.last_prompt_fit)})



                connection = state.get("connection")



                if connection:



                    try:



                        if connection.sock:connection.sock.shutdown(socket.SHUT_RDWR)



                    except OSError:



                        pass



                    try:



                        connection.close()



                    except OSError:



                        pass



                raise



            finally:



                reader.join(timeout=1)



            raw_output = str(generation_diagnostics.get("raw_output", ""))



            generation_diagnostics.pop("raw_output", None)



            if self.behavior.harmony:parsed = parse_visible_assistant_output(raw_output)



            else:



                parser=TemplateContentStream();plain=parser.feed(raw_output)+parser.finish()



                parsed={'text':plain,'reasoning_present':parser.hidden,'explicit_final':False}



            answer = "".join(parts).strip() or parsed["text"].strip()



            generation_diagnostics.update({



                "raw_output_length": len(raw_output),



                # Preview only content already classified as user-visible; never store reasoning text.



                "raw_output_preview": parsed["text"][:240],



                "reasoning_present": bool(generation_diagnostics.get("reasoning_present") or parsed["reasoning_present"]),



                "final_present": bool(generation_diagnostics.get("final_present") or parsed["explicit_final"]),



                "stream_buffer_length": len(raw_output),



                "visible_response_length": len(answer),



                "termination_marker_reported": generation_diagnostics.get("stop_reason") or generation_diagnostics.get("finish_reason"),



                "validated_text_length": 0,



                "retry_output_length": 0,



            })



            if stream_error:



                generation_diagnostics["stream_error"] = stream_error[:400]



            tool_calls = generation_diagnostics.pop("tool_calls", []) or []



            if not tool_calls and allowed_tools:



                from tool_registry import ToolRegistry



                extracted = ToolRegistry().parse_tool_calls(raw_output)



                if extracted:



                    allowed_set = set(allowed_tools) if allowed_tools is not None else None



                    matching = [c for c in extracted if allowed_set is None or c.get("name") in allowed_set]



                    if matching:



                        tool_calls = matching



                        generation_diagnostics["tool_call_present"] = True



            self._log_generation_diagnostics(generation_diagnostics)



            if tool_calls:



                print(f"[TOOL_CALL] Intercepted {len(tool_calls)} tool call(s) from local model output: {[c.get('name') for c in tool_calls]}")



                return ToolCallCompletion(tool_calls)



            if not answer:



                raise EmptyVisibleResponseError(f"{self.behavior.model_alias} finished without a visible final answer. A safe recovery attempt is required.")



            if stream_error:



                _runtime_logger.warning("Local GPT-OSS stream ended after producing %d safe visible characters: %s", len(answer), stream_error[:240])



            return answer







    def complete_vision(self, messages, max_tokens, cancel_event=None):



        """Send image content to the app-owned Qwen3-VL server, never to a text-only model."""



        if not self.projector_path or not self._is_healthy():



            raise RuntimeError("Offline GPT's local Qwen3-VL vision engine is not ready.")



        payload = {



            "model": Path(self.model_path).stem,



            "messages": messages,



            "stream": False,



            "max_tokens": max(1, min(1600, int(max_tokens))),



            "temperature": 0.0,



        }



        result_queue = queue.Queue(maxsize=1)







        def request():



            try:



                result_queue.put((True, self._json_request("/v1/chat/completions", payload, timeout=900)))



            except Exception as exc:



                result_queue.put((False, exc))







        with self._request_lock:



            reader = threading.Thread(target=request, name="OfflineGPT-vision-request", daemon=True)



            reader.start()



            while True:



                if cancel_event is not None and cancel_event.is_set():



                    self.stop()



                    raise RuntimeError("Cancelled")



                try:



                    success, value = result_queue.get(timeout=0.25)



                    break



                except queue.Empty:



                    if not self.ready:



                        raise RuntimeError("The local Qwen3-VL engine stopped during image analysis. " + self._log_tail())



            if not success:



                raise RuntimeError(f"Local Qwen3-VL image analysis failed: {value}") from value



            choices = value.get("choices") if isinstance(value, dict) else None



            message = (choices or [{}])[0].get("message", {})



            content = message.get("content", "")



            if isinstance(content, list):



                content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))



            answer = str(content).strip()



            if not answer:



                raise RuntimeError("Qwen3-VL returned no visible analysis. Check the local vision log.")



            return answer







    def stop(self, graceful=True):



        process, self.process = self.process, None



        self.port = None



        self.api_key = ""



        self.model_path = ""



        self.projector_path = ""



        self.projector_file_observation = None



        if process and process.poll() is None:



            try:



                if os.name == "nt":



                    if graceful:



                        try:



                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T"], stdout=subprocess.DEVNULL,



                                           stderr=subprocess.DEVNULL, timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))



                            process.wait(timeout=3)



                        except Exception:



                            pass



                    if process.poll() is None:



                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,



                                       stderr=subprocess.DEVNULL, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))



                else:



                    process.terminate()



                process.wait(timeout=5)



            except Exception:



                try:



                    process.kill()



                    process.wait(timeout=5)



                except Exception:



                    pass



        if self.log_handle:



            try:



                self.log_handle.close()



            except OSError:



                pass



            self.log_handle = None











class _LMStudioRuntime:



    """Manage Bionic/LM Studio and stream through its loopback OpenAI API."""







    MODEL_TTL = 600



    REQUEST_TIMEOUT = 900







    def __init__(self, cfg, log_dir):



        self.cfg = cfg



        self.log_dir = Path(log_dir)



        self.loaded_model = ""



        self.last_activity = 0.0



        # Keep the same content-free generation receipt used by the bundled



        # runtime.  Without this, the supported loopback adapter could only



        # report a model label and callers could not distinguish a complete



        # local response from a truncated stream.



        self.last_generation_diagnostics = {}



        self.started_bionic = False



        self.started_server = False



        self.bionic_process = None



        self.lock = threading.RLock()







    def reload(self, cfg):



        self.cfg = cfg







    @property



    def base(self):



        return str(self.cfg.get("chat_url", "http://127.0.0.1:1234/v1")).rstrip("/")







    def _url(self, path):



        parsed = urllib.parse.urlsplit(self.base)



        if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:



            raise RuntimeError("LM Studio must use a loopback address so chat stays on this PC.")



        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + path, "", ""))







    def _server_ready(self):



        try:



            request = urllib.request.Request(self._url("/models"))



            with urllib.request.urlopen(request, timeout=2) as response:



                return response.status == 200



        except Exception:



            return False







    def _models(self):



        request = urllib.request.Request(self._url("/models"))



        try:



            with urllib.request.urlopen(request, timeout=8) as response:



                return json.loads(response.read().decode("utf-8", "replace")).get("data", [])



        except Exception as exc:



            raise RuntimeError(f"Bionic/LM Studio local API is not ready: {exc}") from exc







    def _lms_path(self):



        value = str(self.cfg.get("lms_exe", "")).strip()



        exe = resolve_path(value) if value else Path.home() / ".lmstudio" / "bin" / "lms.exe"



        if not exe.is_file():



            raise RuntimeError(f"LM Studio's local CLI was not found: {exe}. Select lms.exe in Settings.")



        return exe







    @staticmethod



    def _bionic_path():



        profile = Path(os.environ.get("USERPROFILE", str(Path.home())))



        location_file = profile / ".lmstudio" / ".internal" / "app-install-location.json"



        try:



            install = json.loads(location_file.read_text(encoding="utf-8"))



            candidate = Path(str(install.get("path", ""))).expanduser()



            if candidate.is_file():



                return candidate



        except (OSError, ValueError, TypeError):



            pass



        return profile / "AppData" / "Local" / "Programs" / "Bionic" / "Bionic.exe"







    def _run_lms(self, args, timeout=180, check=True, cancel_event=None, progress=lambda _s: None):



        exe = self._lms_path()



        command = [str(exe), *[str(arg) for arg in args]]



        process = subprocess.Popen(



            command, cwd=str(exe.parent), stdin=subprocess.DEVNULL,



            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,



            encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),



        )



        started = time.monotonic()



        next_update = started + 10



        while True:



            if cancel_event is not None and cancel_event.is_set():



                process.terminate()



                try:



                    process.wait(timeout=3)



                except subprocess.TimeoutExpired:



                    process.kill()



                raise RuntimeError("Cancelled")



            try:



                stdout, _ = process.communicate(timeout=0.25)



                break



            except subprocess.TimeoutExpired:



                elapsed = time.monotonic() - started



                if elapsed >= timeout:



                    process.terminate()



                    try:



                        process.wait(timeout=3)



                    except subprocess.TimeoutExpired:



                        process.kill()



                    raise RuntimeError(f"LM Studio command timed out after {timeout} seconds: {' '.join(args)}")



                if elapsed >= next_update:



                    model_label = str(args[1]) if len(args) > 1 and args[0] == "load" else "the local model service"



                    progress(f"Bionic/LM Studio is still preparing {model_label} · {int(elapsed)}s elapsed…")



                    next_update = elapsed + 10



        clean = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", (stdout or "")).replace("\r", "\n").strip()



        result = subprocess.CompletedProcess(command, process.returncode, clean, "")



        if check and result.returncode:



            raise RuntimeError(f"LM Studio command failed: {' '.join(args)}\n{clean[-2200:] or 'No details returned.'}")



        return result







    def _launch_bionic(self, progress, cancel_event=None):



        exe = self._bionic_path()



        if not exe.is_file():



            raise RuntimeError(f"Bionic/LM Studio was not found: {exe}. Install it or select its local CLI in Settings.")



        progress("Starting Bionic/LM Studio's local model service…")



        self.bionic_process = subprocess.Popen(



            [str(exe)], cwd=str(exe.parent), stdin=subprocess.DEVNULL,



            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,



            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),



        )



        self.started_bionic = True



        started = time.monotonic()



        next_update = started + 8



        while time.monotonic() - started < 90:



            EngineManager._raise_if_cancelled(cancel_event)



            if self._server_ready():



                self.started_server = True



                return



            if time.monotonic() >= next_update:



                progress(f"Waiting for Bionic/LM Studio's local API · {int(time.monotonic() - started)}s elapsed…")



                next_update = time.monotonic() + 8



            time.sleep(0.4)



        # Bionic can start without its API server enabled. Start the API on



        # loopback only through the official CLI, then wait for readiness.



        self._run_lms(["server", "start", "--port", urllib.parse.urlsplit(self.base).port or 1234,



                       "--bind", "127.0.0.1"], timeout=90, progress=progress)



        self.started_server = True



        started = time.monotonic()



        while time.monotonic() - started < 45:



            if self._server_ready():



                return



            time.sleep(0.4)



        raise RuntimeError("Bionic/LM Studio started, but its local chat API did not become ready on 127.0.0.1:1234.")







    def ensure_chat(self, progress=lambda _s: None, model=None, cancel_event=None, context=None):



        with self.lock:



            EngineManager._raise_if_cancelled(cancel_event)



            if not self._server_ready():



                daemon_running = False



                try:



                    status = self._run_lms(["daemon", "status", "--json"], timeout=12, check=False, cancel_event=cancel_event, progress=progress).stdout



                    daemon_running = json.loads(status).get("status") == "running"



                except Exception:



                    daemon_running = False



                if daemon_running:



                    port = urllib.parse.urlsplit(self.base).port or 1234



                    self._run_lms(["server", "start", "--port", str(port), "--bind", "127.0.0.1"], timeout=60, cancel_event=cancel_event, progress=progress)



                    self.started_server = True



                    started = time.monotonic()



                    while time.monotonic() - started < 30 and not self._server_ready():



                        EngineManager._raise_if_cancelled(cancel_event)



                        time.sleep(0.35)



                if not self._server_ready():



                    self._launch_bionic(progress, cancel_event)



            model = str(model or self.cfg.get("chat_model", "openai/gpt-oss-20b")).strip()



            if model == "gpt-oss-20b-local":



                model = "openai/gpt-oss-20b"



            if self.loaded_model == model and time.monotonic() - self.last_activity < self.MODEL_TTL - 30:



                return model



            if self.loaded_model != model:



                progress(f"Releasing any previously loaded local model before loading {model}…")



                self._run_lms(["unload", "--all"], timeout=180, check=True, cancel_event=cancel_event, progress=progress)



                self.loaded_model = ""



            loaded = self._run_lms(["ps"], timeout=20, check=False, cancel_event=cancel_event, progress=progress).stdout.lower()



            if model.lower() not in loaded:



                context = max(2048, min(8192, int(context or self.cfg.get("chat_context", 4096))))



                progress(f"Loading {model} with Bionic/LM Studio's automatic GPU placement…")



                self._run_lms(



                    ["load", model, "--context-length", str(context), "--ttl", str(self.MODEL_TTL)],



                    timeout=900, cancel_event=cancel_event, progress=progress,



                )



            self.loaded_model = model



            self.last_activity = time.monotonic()



            return model







    def model_is_loaded(self):



        if not self.loaded_model:



            return False



        if time.monotonic() - self.last_activity < self.MODEL_TTL - 5:



            return True



        try:



            output = self._run_lms(["ps"], timeout=12, check=False).stdout.lower()



            if self.loaded_model.lower() in output:



                self.last_activity = time.monotonic()



                return True



        except Exception:



            pass



        self.loaded_model = ""



        return False







    @staticmethod



    def _estimated_tokens(messages):



        # Image data URLs are transport payloads, not prompt text. Counting the



        # base64 bytes as tokens incorrectly makes a single small image appear



        # to exceed the model's text context by orders of magnitude.



        chars = 0



        for message in messages:



            content = message.get("content", "")



            if isinstance(content, str):



                chars += len(content)



            elif isinstance(content, list):



                for part in content:



                    if not isinstance(part, dict):



                        continue



                    if part.get("type") == "text":



                        chars += len(str(part.get("text", "")))



                    elif part.get("type") in {"image_url", "image"}:



                        chars += 2400  # conservative allowance for visual tokens



        return max(1, (chars + 2) // 3)







    def _fit_messages(self, messages, output_tokens, progress, context=None):



        context = max(2048, min(8192, int(context or self.cfg.get("chat_context", 4096))))



        min_reserve = 128



        budget = max(512, context - min_reserve - 48)



        fitted = [dict(message) for message in messages]



        changed = False



        while len(fitted) > 2 and self._estimated_tokens(fitted) > budget:



            index = 1 if fitted[0].get("role") == "system" else 0



            user_positions = [position for position, item in enumerate(fitted) if item.get("role") == "user"]



            current_user = user_positions[-1] if user_positions else len(fitted) - 1



            if index >= current_user:



                break



            # Keep the active user request and its assistant/tool exchange



            # intact while removing one complete older conversation turn.



            end = index + 1



            while end < current_user and fitted[end].get("role") != "user":



                end += 1



            del fitted[index:end]



            changed = True



        if self._estimated_tokens(fitted) > budget and len(fitted) >= 2:



            user_positions = [position for position, item in enumerate(fitted) if item.get("role") == "user"]



            current_user = user_positions[-1] if user_positions else len(fitted) - 1



            latest_tool = next((position for position in range(len(fitted) - 1, current_user, -1)



                                if fitted[position].get("role") == "tool" and isinstance(fitted[position].get("content"), str)), None)



            if latest_tool is not None and len(fitted[latest_tool]["content"]) > 512:



                content = fitted[latest_tool]["content"]



                keep = max(256, int(len(content) * 0.65))



                fitted[latest_tool]["content"] = content[:keep // 2] + "\n[…local tool output shortened…]\n" + content[-(keep - keep // 2):]



                changed = True



            message = fitted[current_user] if current_user < len(fitted) else fitted[-1]



            content = message.get("content")



            if isinstance(content, str):



                keep_chars = max(1800, budget * 3 - 1200)



                if len(content) > keep_chars:



                    # Retain the user request at the front and the most recent



                    # document material at the end; stored files are untouched.



                    head = min(2400, keep_chars // 3)



                    message["content"] = content[:head] + "\n[…middle omitted for context…]\n" + content[-(keep_chars - head):]



                    changed = True



        if changed:



            progress("Keeping recent chat context within LM Studio's selected context window…")



        return fitted







    def complete(self, messages, max_tokens, temperature, cancel_event, on_token, progress,



                 connection_callback=None, context=None, reasoning_effort="low", top_p=None, allowed_tools=None):



        diagnostics = {



            "finish_reason": None,



            "stop_reason": None,



            "generated_token_count": None,



            "generated_token_count_source": "not_reported_by_runtime",



            "prompt_token_count": None,



            "content_chunk_lengths": [],



            "content_characters": 0,



            "reasoning_present": False,



            "tool_call_present": False,



            "stream_terminated": False,



            "advertised_tools": [t["function"]["name"] for t in _local_tool_schemas(allowed_tools)],



        }



        self.last_generation_diagnostics = diagnostics



        if not self._server_ready():



            raise RuntimeError("Bionic/LM Studio's local chat API stopped. Send the message again to restart it.")



        output_tokens = max(1, min(1200, int(max_tokens)))



        fitted = self._fit_messages(messages, output_tokens, progress, context)



        tools = _local_tool_schemas(allowed_tools)



        payload = {



            "model": self.loaded_model or self.cfg.get("chat_model", "openai/gpt-oss-20b"),



            "messages": fitted, "stream": True, "max_tokens": output_tokens,



            "temperature": float(temperature), "top_p": float(0.92 if top_p is None else top_p),



        }



        if tools:



            payload["tools"] = tools



            payload["tool_choice"] = "auto"



        if reasoning_effort:



            payload["reasoning_effort"] = reasoning_effort



        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")



        parsed = urllib.parse.urlsplit(self.base)



        port = parsed.port or (443 if parsed.scheme == "https" else 80)



        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection



        connection = connection_type(parsed.hostname, port, timeout=self.REQUEST_TIMEOUT)



        if connection_callback:



            connection_callback(connection)



        visible = _VisibleChatStream()



        parts = []



        tool_calls_by_index = {}



        try:



            progress("Streaming from the local Bionic/LM Studio model…")



            path = urllib.parse.urlunsplit(("", "", parsed.path.rstrip("/") + "/chat/completions", parsed.query, ""))



            connection.request("POST", path, body=body, headers={"Content-Type": "application/json"})



            EngineManager._raise_if_cancelled(cancel_event)



            response = connection.getresponse()



            if response.status < 200 or response.status >= 300:



                detail = response.read().decode("utf-8", "replace")[-1800:]



                raise RuntimeError(f"Bionic/LM Studio returned HTTP {response.status}: {detail or response.reason}")



            for raw in response:



                EngineManager._raise_if_cancelled(cancel_event)



                line = raw.decode("utf-8", "replace").strip()



                if not line.startswith("data:"):



                    continue



                data = line[5:].strip()



                if data == "[DONE]":



                    diagnostics["stream_terminated"] = True



                    break



                try:



                    item = json.loads(data)



                except json.JSONDecodeError:



                    continue



                if item.get("error"):



                    raise RuntimeError(str(item["error"]))



                usage = item.get("usage")



                if isinstance(usage, dict):



                    if isinstance(usage.get("completion_tokens"), int):



                        diagnostics["generated_token_count"] = usage["completion_tokens"]



                        diagnostics["generated_token_count_source"] = "stream_usage"



                    if isinstance(usage.get("prompt_tokens"), int):



                        diagnostics["prompt_token_count"] = usage["prompt_tokens"]



                    details = usage.get("completion_tokens_details") or {}



                    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):



                        diagnostics["reasoning_tokens"] = details["reasoning_tokens"]



                choices = item.get("choices") or []



                if not choices:



                    continue



                delta = choices[0].get("delta") or {}



                choice = choices[0]



                if choice.get("finish_reason") is not None:



                    diagnostics["finish_reason"] = choice.get("finish_reason")



                if choice.get("stop_reason") is not None:



                    diagnostics["stop_reason"] = choice.get("stop_reason")



                if isinstance(delta.get("reasoning"), str) and delta["reasoning"].strip():



                    diagnostics["reasoning_present"] = True



                if isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"].strip():



                    diagnostics["reasoning_present"] = True



                if delta.get("tool_calls"):



                    diagnostics["tool_call_present"] = True



                    _merge_tool_call_deltas(tool_calls_by_index, delta.get("tool_calls"))



                content = delta.get("content")



                if isinstance(content, str) and content:



                    diagnostics["content_chunk_lengths"].append(len(content))



                    diagnostics["content_characters"] += len(content)



                    text = visible.feed(content)



                    if text:



                        parts.append(text)



                        on_token(text)



            tail = visible.finish()



            if tail:



                parts.append(tail)



                on_token(tail)



        except Exception as exc:



            diagnostics["stream_error"] = str(exc)[:400]



            if diagnostics.get("finish_reason") is None:



                diagnostics["finish_reason"] = "cancelled" if cancel_event is not None and cancel_event.is_set() else "error"



            raise



        finally:



            connection.close()



            if connection_callback:



                connection_callback(None)



            # Assign a new mapping so consumers can reliably tell this



            # completion's receipt from a previous request's receipt.



            self.last_generation_diagnostics = dict(diagnostics)



        tool_calls = _normalized_tool_calls(tool_calls_by_index)



        if not tool_calls and allowed_tools:



            from tool_registry import ToolRegistry



            streamed_text = "".join(parts)



            extracted = ToolRegistry().parse_tool_calls(streamed_text)



            if extracted:



                allowed_set = set(allowed_tools) if allowed_tools is not None else None



                matching = [c for c in extracted if allowed_set is None or c.get("name") in allowed_set]



                if matching:



                    tool_calls = matching



        if tool_calls:



            print(f"[TOOL_CALL] Intercepted {len(tool_calls)} tool call(s) from local model output: {[c.get('name') for c in tool_calls]}")



            self.last_activity = time.monotonic()



            return ToolCallCompletion(tool_calls)



        streamed = "".join(parts).strip()



        answer = visible_assistant_text(streamed).strip() or streamed



        if not answer:



            raise EmptyVisibleResponseError("Bionic/LM Studio finished without a visible answer. A safe recovery attempt is required.")



        self.last_activity = time.monotonic()



        return answer







    def unload(self, progress=lambda _s: None, cancel_event=None, stop_server=False):



        with self.lock:



            EngineManager._raise_if_cancelled(cancel_event)



            if self.loaded_model:



                model = self.loaded_model



                progress(f"Releasing {model} from Bionic/LM Studio…")



                self._run_lms(["unload", model], timeout=180, check=False, cancel_event=cancel_event, progress=progress)



                self.loaded_model = ""



                self.last_activity = 0.0



            if stop_server and self.started_server:



                EngineManager._raise_if_cancelled(cancel_event)



                self._run_lms(["server", "stop"], timeout=45, check=False, cancel_event=cancel_event, progress=progress)



                self.started_server = False







    def unload_all(self, progress=lambda _s: None, cancel_event=None):



        """Release LM Studio models not tracked by this process after a prior app exit."""



        with self.lock:



            EngineManager._raise_if_cancelled(cancel_event)



            progress("Releasing stale local model allocations…")



            self._run_lms(["unload", "--all"], timeout=180, check=True, cancel_event=cancel_event, progress=progress)



            self.loaded_model = ""



            self.last_activity = 0.0











class EngineManager:



    """Manage the private local GPT-OSS engine and one-shot image CLI."""







    def __init__(self):



        self.cfg = load_config()



        self.loaded_model = ""



        self.runtime = None



        self.lm_runtime = _LMStudioRuntime(self.cfg, CONFIG_PATH.parent / "logs")



        self.active_chat_backend = ""



        self.image_process = None



        self.shutting_down = False



        self.lock = threading.RLock()



        self.log_dir = CONFIG_PATH.parent / "logs"



        self.log_dir.mkdir(parents=True,exist_ok=True)



        self.chat_load_state = "not-loaded"



        self.chat_last_error = ""



        self.chat_test_state = "not-tested"



        self.chat_test_message = "Run a response test to verify local inference."



        self.chat_test_answer = ""



        self.chat_test_time = ""



        self.vision_test_state = "not-tested"



        self.vision_test_message = "Use the bundled Qwen3-VL GGUF and matching projector for local image understanding and OCR."



        self.vision_test_answer = ""



        self.vision_test_time = ""



        self._vision_catalog_cache = (0.0, [], "")



        self.resource_lock = threading.RLock()



        self._image_resource_owner = None



        self.active_gpu_layers = None



        self.requested_gpu_layers = None



        self.chat_memory_profile = None



        self.model_lifecycle_mode = self.cfg.get("model_lifecycle_mode", "balanced")



        self.model_keepalive_seconds = self.cfg.get("model_keepalive_seconds", 90)



        self.emergency_ram_threshold_mb = self.cfg.get("emergency_ram_threshold_mb", 192)



        self.last_unload_reason = ""



        self.last_reload_reason = "Application startup"



        self._active_inference_count = 0



        self._last_request_time = 0.0



        self._idle_timer = None



        self._current_generation_id = 0



        self._model_inspection_cache = {}



        self.text_runtime=EngineTextRuntime(self)



        self.last_completion_identity={}







    def reload(self):



        previous = resolve_path(self.cfg.get("gpt_oss_gguf", "")) if self.cfg.get("gpt_oss_gguf") else None



        previous_backend = self.cfg.get("chat_backend", "bundled")



        previous_context = self.cfg.get("chat_context")



        previous_external_model = self.cfg.get("chat_model", "")



        previous_gpu=(self.cfg.get('chat_gpu','auto'),self.cfg.get('chat_gpu_layers',-1))



        self.cfg = load_config()



        self.model_lifecycle_mode = self.cfg.get("model_lifecycle_mode", "balanced")



        self.model_keepalive_seconds = self.cfg.get("model_keepalive_seconds", 90)



        self.emergency_ram_threshold_mb = self.cfg.get("emergency_ram_threshold_mb", 192)



        self.lm_runtime.reload(self.cfg)



        self._vision_catalog_cache = (0.0, [], "")



        current = resolve_path(self.cfg.get("gpt_oss_gguf", "")) if self.cfg.get("gpt_oss_gguf") else None



        current_backend = self.cfg.get("chat_backend", "bundled")



        external_changed = (current_backend == "lmstudio" and previous_external_model != self.cfg.get("chat_model", ""))



        selection_changed = previous != current or previous_backend != current_backend or previous_context != self.cfg.get("chat_context") or previous_gpu!=(self.cfg.get('chat_gpu','auto'),self.cfg.get('chat_gpu_layers',-1)) or external_changed



        if selection_changed:



            self._model_inspection_cache.clear()



            self.chat_test_state = "not-tested"



            self.chat_test_message = "Run a response test to verify the selected model."



            self.chat_test_answer = ""



            self.chat_test_time = ""



            self.chat_last_error = ""



            self.chat_load_state = "not-loaded"



        if selection_changed and self.runtime:



            self.last_unload_reason = "Model, backend or context settings changed"



            self.runtime.stop()



            self.loaded_model = ""



            self.active_chat_backend = ""



            self.chat_load_state = "not-loaded"



            self.chat_last_error = ""



            self.active_gpu_layers = None



            self.requested_gpu_layers = None



            self.chat_memory_profile = None



        if previous_backend != current_backend or external_changed:



            try:



                self.lm_runtime.unload(stop_server=True)



            except Exception:



                pass



            self.loaded_model = ""



            self.active_chat_backend = ""



            self.chat_load_state = "not-loaded"







    @staticmethod



    def _hidden_flags():



        return getattr(subprocess, "CREATE_NO_WINDOW", 0)







    def resolve_model_path(self, model_target=None):



        from pathlib import Path



        if not model_target or str(model_target).strip() in ("", "default", "gpt-oss-20b-local", "openai/gpt-oss-20b"):



            # The default key is an explicit GPT-OSS selection. A previously



            # loaded Qwen path must never redefine what that selection means.



            return self.image_path("gpt_oss_gguf")



        target_str = str(model_target).strip()



        if target_str == str(self.cfg.get("chat_model", "")).strip():



            return self.image_path("gpt_oss_gguf")



        try:



            p = resolve_path(target_str)



            if p and p.is_file():



                return p



        except Exception:



            pass



        try:



            configured_gguf = self.image_path("gpt_oss_gguf", optional=True)



            if configured_gguf and configured_gguf.name.lower() == target_str.lower():



                return configured_gguf



        except Exception:



            pass



        try:



            import sqlite3



            from pathlib import Path



            data_dir = self.log_dir.parent if hasattr(self, 'log_dir') else Path('.')



            db_file = data_dir / 'offline_gpt.sqlite3'



            if db_file.is_file():



                with sqlite3.connect(db_file) as con:



                    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_model_references'").fetchone():



                        row = con.execute("SELECT path FROM local_model_references WHERE id=? OR path=? COLLATE NOCASE", (target_str, target_str)).fetchone()



                        if row and Path(row[0]).is_file():



                            return Path(row[0]).resolve()



                        rows = con.execute("SELECT path, details FROM local_model_references").fetchall()



                        for r_path, r_details in rows:



                            if Path(r_path).is_file():



                                if Path(r_path).name.lower() == target_str.lower():



                                    return Path(r_path).resolve()



                                try:



                                    import json



                                    d = json.loads(r_details)



                                    if d.get("name", "").strip().lower() == target_str.lower() or d.get("declared", {}).get("name", "").strip().lower() == target_str.lower():



                                        return Path(r_path).resolve()



                                except Exception:



                                    pass



        except Exception:



            pass



        if target_str in self.cfg:



            try:



                return self.image_path(target_str)



            except Exception:



                pass



        raise RuntimeError("The selected local model is unavailable. Re-import or reselect its exact GGUF file; no other model was loaded.")







    def ensure_chat(self, progress=lambda _s: None, model=None, cancel_event=None):



        with self.resource_lock, self.lock:



            self._raise_if_cancelled(cancel_event)



            if self.cfg.get("chat_backend", "bundled") == "lmstudio":



                if getattr(self,'secondary_release',None):self.secondary_release()



                self.chat_load_state = "loading"



                try:



                    selected_model = self.lm_runtime.ensure_chat(progress, model, cancel_event)



                    self.loaded_model = selected_model



                    self.active_chat_backend = "lmstudio"



                    self.chat_load_state = "ready"



                    self.chat_last_error = ""



                    self.active_gpu_layers = None



                    self.requested_gpu_layers = None



                    self.chat_memory_profile = None



                    progress("GPT-OSS is ready through Bionic/LM Studio on this PC.")



                    return selected_model



                except Exception as exc:



                    self.chat_load_state = "error"



                    self.chat_last_error = str(exc)



                    self.loaded_model = ""



                    self.active_chat_backend = ""



                    try:self.lm_runtime.unload_all(progress,None)



                    except Exception:pass



                    raise



            model_path = self.resolve_model_path(model)



            model_file = Path(model_path)



            if not model_file.is_file():



                raise RuntimeError(f"Local GGUF model was not found: {model_path}. Choose the model file in Settings.")



            if self.runtime is None:



                self.runtime = _LocalLlamaServer(self.log_dir)



            gpu_layers=0 if self.cfg.get('chat_gpu')=='cpu' or self.cfg.get('chat_gpu_layers')==0 else 'auto'

            reserve=getattr(self,'voice_vram_reserve_mb',0)

            if self.runtime is not None:self.runtime.vram_reserve_mb=reserve

            if (self.runtime and self.runtime.model_path == str(model_file.resolve())

                    and _loaded_fit_target(self.runtime)>=chat_fit_target_mb(False,reserve)



                    and not self.runtime.projector_path and getattr(self.runtime,'loaded_gpu_layers',None)==str(gpu_layers)



                    and getattr(self.runtime,'model_file_observation',None)==_LocalLlamaServer.file_observation(model_file)



                    and self.runtime._is_healthy()):



                self.active_gpu_layers = gpu_layers



                self.requested_gpu_layers = gpu_layers



                self.loaded_model = self.cfg.get("chat_model", "gpt-oss-20b-local")



                self.active_chat_backend = "bundled"



                if isinstance(getattr(self.runtime,'model_descriptor',None),ModelInfo):self.loaded_model=self.runtime.model_descriptor.display_name



                elif model_file.stem != 'gpt-oss-20b':self.loaded_model=model_file.name



                self.chat_load_state = "ready"



                self.chat_last_error = ""



                return self.loaded_model



            self.requested_gpu_layers = gpu_layers



            if getattr(self,'secondary_release',None):self.secondary_release(purpose='chat')



            self.chat_load_state = "loading"



            self.last_reload_reason = self.last_unload_reason or f"Starting model {model_file.name}"



            try:



                memory = physical_memory_status()



                context = int(self.cfg.get("chat_context", _LocalLlamaServer.CONTEXT))



                hw_profile = self.cfg.get("hardware_profile", self.cfg.get("model_lifecycle_mode", "balanced"))



                profile = _local_memory_profile(memory, context, hardware_profile=hw_profile)



                context = int(profile["context"])



                profile.update({



                    "batch": min(128, int(profile["batch"])),



                    "ubatch": min(64, max(16, int(profile["batch"]) // 2)), "gpu_layers": gpu_layers,



                    "cpu_moe_layers": None,



                    "memory_mapped": profile.get("load_mode", "mmap") == "mmap",



                })



                self.chat_memory_profile = profile



                self.runtime.start(model_path, context, gpu_layers, progress, cancel_event, profile)



                if type(getattr(self.runtime,'context',None)) is int:profile['context']=self.runtime.context



                self.active_gpu_layers = gpu_layers



                self.loaded_model = self.cfg.get("chat_model", "gpt-oss-20b-local")



                if getattr(self.runtime,'model_descriptor',None):self.loaded_model=self.runtime.model_descriptor.display_name



                elif model_file.stem != 'gpt-oss-20b':self.loaded_model=model_file.name



                self.active_chat_backend = "bundled"



                self.chat_load_state = "ready"



                self.chat_last_error = ""



                progress(f"{self.loaded_model} is ready in Offline GPT's private hybrid engine.")



                return self.loaded_model



            except Exception as exc:



                self.chat_load_state = "error"



                self.chat_last_error = str(exc)



                self.active_gpu_layers = None



                if self.runtime and not self.runtime.ready:



                    self.loaded_model = ""



                raise







    @staticmethod



    def _is_qwen_vision_family(item):



        if not isinstance(item, dict):



            return False



        identity = " ".join(str(item.get(key, "")) for key in ("modelKey", "displayName", "path", "indexedModelIdentifier", "architecture")).lower()



        architecture = str(item.get("architecture", "")).lower().replace("_", "").replace("-", "")



        return "qwen3vl" in architecture or "qwen3-vl" in identity







    @classmethod



    def _is_qwen_vision_model(cls, item):



        # LM Studio's catalog explicitly marks a text-only Qwen3-VL GGUF as



        # vision=false when its matching mmproj file is absent. Do not infer



        # image support from the architecture name alone: that sends image



        # payloads to a text-only model and produces an HTTP 400 at runtime.



        if not cls._is_qwen_vision_family(item):



            return False



        return item.get("vision") is not False







    def _vision_catalog(self, refresh=False):



        now = time.monotonic()



        cached_at, cached, cached_error = self._vision_catalog_cache



        if not refresh and now - cached_at < 20:



            return cached, cached_error



        try:



            output = self.lm_runtime._run_lms(["ls", "--json"], timeout=30).stdout



            models = json.loads(output or "[]")



            if isinstance(models, dict):



                models = models.get("models", [])



            if not isinstance(models, list):



                raise ValueError("LM Studio returned an unexpected local model list.")



            rows = [item for item in models if isinstance(item, dict)]



            error = ""



        except Exception as exc:



            rows, error = [], str(exc)



        self._vision_catalog_cache = (now, rows, error)



        return rows, error







    def _vision_pair_review(self, model, projector):



        """Bounded header review, cached by file identity; never native acceptance."""



        from model_inspection import ordinary_file,identity,inspect_gguf



        from model_runtime import vision_pair_conflict



        key=None



        try:



            _,model_stat=ordinary_file(model);_,projector_stat=ordinary_file(projector)



            key=(str(model),identity(model_stat),str(projector),identity(projector_stat))



            cached=getattr(self,'_vision_pair_review_cache',None)



            if cached and cached[0]==key:return {**cached[1],'identity':dict(cached[1]['identity'])}



            model_info=inspect_gguf(model);projector_info=inspect_gguf(projector)



            # A changed input must never reuse the earlier metadata review.



            if tuple(model_info['fileObservation'])!=key[1] or tuple(projector_info['fileObservation'])!=key[3]:



                raise ValueError('Vision inputs changed during header review; retry.')



            result={'architecture':str(model_info['metadata'].get('general.architecture','unknown')),



                'conflict':vision_pair_conflict(model_info['metadata'],projector_info['metadata']),



                'identity':{'modelObservation':key[1],'projectorObservation':key[3],



                    'modelHeaderSha256':model_info['headerMetadataSha256'],'projectorHeaderSha256':projector_info['headerMetadataSha256']},'error':''}



            self._vision_pair_review_cache=(key,{**result,'identity':dict(result['identity'])})



            return result



        except (OSError,ValueError) as exc:



            result={'architecture':'unknown','conflict':'','identity':{},'error':str(exc)}



            if key is not None:self._vision_pair_review_cache=(key,dict(result))



            return result







    def _matching_projector(self, model, projector):

        """Configured projector, or a matching mmproj beside the model when the configured one is the wrong family.



        Measured 2026-11-09: settings paired Qwen3VL-8B with the Qwen3.5 mmproj-F16.gguf, so every image edit stopped

        at 'Choose the matching vision pair' although mmproj-Qwen3VL-8B-Instruct-F16.gguf was installed beside it.

        Only a file whose header review shows no conflict is used; the choice is kept in cfg."""

        try:

            if not (model.is_file() and projector.is_file()):return projector

            if not self._vision_pair_review(model,projector).get('conflict'):return projector

            stem=re.sub(r'[^a-z0-9]','',model.stem.lower().split('-q')[0])

            found=sorted({c for folder in {model.parent,projector.parent} for c in folder.glob('mmproj*.gguf') if c.is_file() and c.resolve()!=projector.resolve()},

                         key=lambda c:(stem not in re.sub(r'[^a-z0-9]','',c.stem.lower()),c.name.lower()))

            for candidate in found:

                review=self._vision_pair_review(model,candidate)

                if not review.get('conflict') and not review.get('error'):

                    logging.getLogger(__name__).warning('Vision projector %s does not match %s; using %s',projector.name,model.name,candidate.name)

                    self.cfg['vision_projector']=str(candidate)

                    return candidate

        except (OSError,ValueError):pass

        return projector

    def vision_model_status(self, refresh=False):



        model = resolve_path(str(self.cfg.get("vision_model") or "Qwen3VL-8B-Instruct-Q4_K_M.gguf"))



        projector = resolve_path(str(self.cfg.get("vision_projector") or "mmproj-Qwen3VL-8B-Instruct-F16.gguf"))

        projector = self._matching_projector(model, projector)



        model_exists = model.is_file()



        projector_exists = projector.is_file()



        runtime_exists = (APP_DIR / "llama-server.exe").is_file()



        available = model_exists and projector_exists and runtime_exists



        review=self._vision_pair_review(model,projector) if available else {}



        if not model_exists:



            state = "missing"



            message = f"Local Qwen3-VL model is missing: {model}. Select its GGUF in Settings."



        elif not projector_exists:



            state = "missing-projector"



            message = f"The matching Qwen3-VL projector is missing: {projector}. Select its mmproj GGUF in Settings."



        elif not runtime_exists:



            state = "runtime-unavailable"



            message = "Offline GPT's bundled llama.cpp vision runtime is missing. Repair the app package."



        elif review.get('error'):



            available=False;state='invalid-configuration'



            message='Local vision inputs could not be verified: '+review['error']+' No image was analyzed.'



        elif review.get('conflict'):



            available=False;state='incompatible-projector'



            message=review['conflict']+' Choose the matching model/projector pair in Vision settings. No image was analyzed and no model was loaded.'



        else:



            state = "available"



            message = "Local vision model and projector headers were inspected. Native compatibility remains unverified until a real visual response test."



        return {



            "visionAvailable": available,



            "visionState": state,



            "visionMessage": message,



            "visionModel": model.name,



            "visionModelKey": str(model),



            "visionProjectorPath": str(projector),



            "visionModelSizeBytes": model.stat().st_size if model_exists else 0,



            "visionArchitecture": review.get('architecture','unknown'),



            "visionPairIdentity": review.get('identity',{}),



            "visionNativeVerified": False,



            "visionTestState": self.vision_test_state,



            "visionTestMessage": self.vision_test_message,



            "visionTestAnswer": self.vision_test_answer,



            "visionTestTime": self.vision_test_time,



        }







    def _resolve_vision_model(self, refresh=True):



        status = self.vision_model_status(refresh)



        if not status["visionAvailable"]:



            raise RuntimeError(status["visionMessage"])



        return status["visionModelKey"], status["visionProjectorPath"]







    def vision_completions(self, requests, progress=lambda _s: None, cancel_event=None,



                           max_tokens=900, context=None):



        """Run local visual/OCR requests sequentially with one model loaded at a time."""



        with self.resource_lock, self.lock:



            self.last_vision_identity={}



            if self.shutting_down:



                raise RuntimeError("Offline GPT is closing and cannot start a vision job.")



            if getattr(self,'secondary_release',None):self.secondary_release()



            model, projector = self._resolve_vision_model(refresh=True)



            vision_context = max(2048, min(8192, int(context or self.cfg.get("vision_context", 4096))))



            self._unload_chat_cancellable(progress, cancel_event)



            # A measured 8B + projector load exhausted host staging RAM even



            # after text-model release. Check the actual installed input sizes



            # before another allocation, retaining the separate emergency stop.



            model_bytes = Path(model).stat().st_size



            projector_bytes = Path(projector).stat().st_size



            # Driver-reported VRAM is useful diagnostics, but actual Qwen3.5



            # staging exhausted host RAM even with projector offload disabled.



            # Reserve full input staging until a measured compatible allocator



            # contract establishes a lower safe envelope for this exact pair.



            vram_avail=available_cuda_memory()



            required_ram=model_bytes+projector_bytes+512*1024**2



            available_ram = physical_memory_status().get('available')



            if available_ram is None or available_ram<required_ram:



                raise RuntimeError('VISION_RESOURCE_BLOCKED: the supplied image remains available. '



                    f'Vision load needs conservative host headroom of {required_ram/1024**3:.2f} GiB for these model/projector inputs; '



                    f'available RAM is {(available_ram or 0)/1024**3:.2f} GiB after releasing text inference. '



                    'Close unused memory-heavy apps and retry. No image was analyzed or changed.')



            self.last_vision_profile={'model':str(model),'projector':str(projector),



                'projectorPlacement':'auto',



                'availableCudaBytes':vram_avail,'requiredHostBytes':required_ram,'availableHostBytes':available_ram}



            outputs = []



            loaded = False



            load_attempted = False



            failure = None



            cleanup_error = None



            try:



                self._raise_if_cancelled(cancel_event)



                progress("Loading Qwen3-VL locally for image understanding and OCR…")



                load_attempted = True



                if self.runtime is None:



                    self.runtime = _LocalLlamaServer(self.log_dir)



                self.runtime.start(model, vision_context, "auto", progress, cancel_event,



                                   projector_path=projector)



                loaded = True



                descriptor=getattr(self.runtime,'model_descriptor',None)



                self.last_vision_identity={'modelName':descriptor.display_name if isinstance(descriptor,ModelInfo) else Path(model).name,



                    'modelPath':str(model),'projectorPath':str(projector),



                    'modelObservation':_LocalLlamaServer.file_observation(model),'projectorObservation':_LocalLlamaServer.file_observation(projector),



                    'nativeReady':self.runtime.ready is True,'identityScope':'loaded local vision runtime; file observations, not full tensor verification',



                    'completionState':'GENERATING','completedImageCount':0}



                for index, messages in enumerate(requests, start=1):



                    self._raise_if_cancelled(cancel_event)



                    progress(f"Qwen3-VL analyzing attachment{f' · page {index}' if index > 1 else ''}…")



                    outputs.append(self.runtime.complete_vision(messages, int(max_tokens), cancel_event))



                    self.last_vision_identity['completedImageCount']=len(outputs)



                self.last_vision_identity['completionState']='COMPLETED'



            except Exception as exc:



                if self.last_vision_identity:self.last_vision_identity['completionState']='FAILED'



                failure = exc



            finally:



                if load_attempted:



                    try:



                        if self.runtime:



                            progress("Releasing Qwen3-VL before GPT-OSS or image generation…")



                            self.runtime.stop()



                    except Exception as exc:



                        cleanup_error = exc



                self.loaded_model = ""



                self.active_chat_backend = ""



                self.chat_load_state = "unloaded" if self.chat_load_state in ("loading", "ready", "unloaded") else self.chat_load_state



            if failure:



                if cleanup_error:



                    raise RuntimeError(f"{failure}\nThe Qwen3-VL model also could not be released cleanly: {cleanup_error}") from failure



                raise failure



            if cleanup_error:



                raise RuntimeError(f"Qwen3-VL completed, but the local engine could not release it: {cleanup_error}") from cleanup_error



            return outputs







    def record_vision_test(self, state, message="", answer=""):



        self.vision_test_state = str(state)



        self.vision_test_message = str(message)



        self.vision_test_answer = str(answer)[:240]



        self.vision_test_time = time.strftime("%Y-%m-%d %H:%M:%S")







    def chat_status(self):



        backend = self.cfg.get("chat_backend", "bundled")



        try:



            model_path = resolve_path(self.cfg.get("gpt_oss_gguf", "")) if backend == "bundled" and self.cfg.get("gpt_oss_gguf") else None



            model_exists = bool(model_path and model_path.is_file())



            model_size = model_path.stat().st_size if model_exists else 0



        except OSError:



            model_path, model_exists, model_size = None, False, 0



        inspection = None



        inspection_error = ""



        if model_exists and model_path and str(model_path).lower().endswith(".gguf"):



            try:



                import model_inspection



                _, info = model_inspection.ordinary_file(model_path)



                observation = model_inspection.identity(info)



                cached = getattr(self, "_model_inspection_cache", {}).get(str(model_path))



                if cached and cached[0] == observation:



                    inspection = cached[1]



                else:



                    res = model_inspection.inspect_gguf(model_path)



                    meta = res.get("metadata", {})



                    arch = meta.get("general.architecture", "unknown")



                    ctx = meta.get(f"{arch}.context_length", meta.get("general.context_length", 4096))



                    inspection = {



                        "name": model_display_name(meta.get("general.name", ""), meta.get("general.file_type")),



                        "declaredName": str(meta.get("general.name", ""))[:160],



                        "architecture": str(arch),



                        "contextLength": int(ctx) if str(ctx).isdigit() or isinstance(ctx, (int, float)) else 4096,



                        "tensorCount": int(res.get("tensorCount", 0)),



                        "warnings": list(res.get("warnings", [])),



                        "headerMetadataSha256": res.get("headerMetadataSha256"),



                        "nativeCompatible": False,



                        "identitySource": "untrusted_gguf_metadata",



                    }



                    if hasattr(self, "_model_inspection_cache"):



                        self._model_inspection_cache[str(model_path)] = (observation, inspection)



            except Exception as exc:



                inspection = None



                inspection_error = str(exc)



        memory = physical_memory_status()



        try:



            lm_cli_present = self.lm_runtime._lms_path().is_file()



        except Exception:



            lm_cli_present = False



        try:



            bionic_present = self.lm_runtime._bionic_path().is_file()



        except OSError:



            bionic_present = False



        lm_server_running = self.lm_runtime._server_ready() if backend == "lmstudio" else False



        bionic_present = bionic_present or lm_server_running



        runtime_files = _LocalLlamaServer._runtime_dependencies()



        bundled_present = (APP_DIR / "llama-server.exe").is_file() and all((APP_DIR / name).is_file() for name in runtime_files)



        runtime_present = ((lm_cli_present and bionic_present) or lm_server_running) if backend == "lmstudio" else bundled_present



        bundled_server_running = bool(self.runtime and self.runtime._is_healthy()) if backend == "bundled" else False



        runtime_loaded = self.lm_runtime.model_is_loaded() if backend == "lmstudio" else bool(self.runtime and self.runtime.ready and bundled_server_running and not getattr(self.runtime,"projector_path",""))



        loaded = runtime_loaded and self.chat_load_state == "ready"



        runtime_path = str(getattr(self.runtime,"model_path","")) if runtime_loaded and backend == "bundled" else ""



        runtime_descriptor = getattr(self.runtime,"model_descriptor",None) if runtime_loaded and backend == "bundled" else None



        runtime_name = (str(self.lm_runtime.loaded_model) if backend == "lmstudio" else runtime_descriptor.display_name if isinstance(runtime_descriptor,ModelInfo) else Path(runtime_path).name) if runtime_loaded else ""



        if backend == "bundled" and loaded:



            loaded = bool(model_exists and str(model_path.resolve()) == str(getattr(self.runtime, "model_path", "")) and not getattr(self.runtime, "projector_path", ""))



        load_state = self.chat_load_state



        if load_state == "ready" and not loaded:



            load_state = "not-loaded"



        if backend == "lmstudio":



            model_name = str(self.lm_runtime.loaded_model if loaded else self.cfg.get("chat_model", "")).strip()



            model_exists = bool(model_name)



            selection_state = "external-selected" if model_exists else "missing-model"



            identity_source = "external_runtime" if loaded else "external_configuration"



        else:



            model_name = inspection.get("name", "") if inspection else ""



            if not model_name and model_path:



                model_name = "".join(c for c in model_path.name if c.isprintable())[:160]



            selection_state = "inspected" if inspection else "unverified-file" if model_exists else "missing-model"



            identity_source = "untrusted_gguf_metadata" if inspection and inspection.get("name") else "selected_filename_unverified"



        if not model_exists:



            load_state = "missing-model"



        guidance = ("Choose an existing local GGUF in Settings → Chat, then save and run a response test."



                    if backend == "bundled" and not model_exists else



                    "Select the external backend's model ID in Settings → Chat." if not model_exists else



                    "Metadata inspection does not establish model compatibility. Run a response test.")



        context = max(2048, min(8192, int(self.cfg.get("chat_context", 4096)))) if backend == "lmstudio" else (self.runtime.context if loaded and self.runtime else max(2048, min(4096, int(self.cfg.get("chat_context", 4096)))))



        try:



            bionic_pid = self.lm_runtime.bionic_process.pid if self.lm_runtime.bionic_process and self.lm_runtime.bionic_process.poll() is None else None



        except Exception:



            bionic_pid = None



        # Never describe a stopped/previous bundled model as the selected or



        # external runtime. These fields describe the actual loaded adapter.



        behavior=getattr(self.runtime,'behavior',None) if loaded and backend=='bundled' else None



        descriptor=getattr(self.runtime,'model_descriptor',None) if loaded and backend=='bundled' else None



        requested_gpu=0 if self.cfg.get('chat_gpu')=='cpu' or self.cfg.get('chat_gpu_layers')==0 else 'auto'



        memory_profile=self.chat_memory_profile if loaded and backend=='bundled' and isinstance(self.chat_memory_profile,dict) else {}



        return {



            "modelName": model_name or "No model selected",



            "modelRuntime": {



                "adapter":"existing-engine-manager",



                "responseFormat":behavior.family.value if isinstance(behavior,ModelBehavior) else 'not-loaded',



                "metadataCapabilities":descriptor.capability_report() if isinstance(descriptor,ModelInfo) else None,



                "nativeCapabilityAcceptance":"NOT_ESTABLISHED_BY_METADATA",



            },



            "modelIdentitySource": identity_source,



            "modelSelectionState": selection_state,



            "modelSelectionMessage": guidance,



            "modelInspectionError": inspection_error,



            "externalModelId": str(self.cfg.get("chat_model", "")) if backend == "lmstudio" else "",



            "modelPath": str(model_path) if model_path else "",



            "modelExists": model_exists,



            "modelSizeBytes": model_size,



            "loadState": load_state,



            "loaded": loaded,



            "runtimeLoaded": bool(runtime_loaded),



            "runtimeModelName": runtime_name,



            "runtimeModelPath": runtime_path,



            "lastError": self.chat_last_error,



            "lastUnloadReason": getattr(self, "last_unload_reason", ""),



            "lastReloadReason": getattr(self, "last_reload_reason", ""),



            "lifecycleMode": str(self.cfg.get("model_lifecycle_mode", self.model_lifecycle_mode)).strip().lower(),



            "keepaliveSeconds": float(self.cfg.get("model_keepalive_seconds", self.model_keepalive_seconds)),



            "testState": self.chat_test_state,



            "testMessage": self.chat_test_message,



            "testAnswer": self.chat_test_answer,



            "testTime": self.chat_test_time,



            "freeRamBytes": memory["available"],



            "totalRamBytes": memory["total"],



            "pagefileAvailableBytes": memory["pagefile_available"],



            "freeGpuBytes": available_cuda_memory(),



            "gpuLayers": requested_gpu if backend == "bundled" else None,



            "activeGpuLayers": self.active_gpu_layers if loaded and backend == "bundled" else None,



            "requestedGpuLayers": requested_gpu if backend=='bundled' else None,



            "gpuPlacementEvidence": "launch arguments; actual tensor placement not independently measured" if loaded and backend=='bundled' else 'not-measured',



            "inferenceMode": ("Offline GPT · CPU inference" if requested_gpu==0 else "Offline GPT · automatic GPU placement") if backend == "bundled" else "LM Studio · external runtime placement",



            "maxOutputTokens": _LocalLlamaServer.MAX_OUTPUT if backend == "bundled" else 1200,



            "cpuMoeLayers": _LocalLlamaServer.CPU_MOE_LAYERS if backend == "bundled" else None,



            "memoryMappedModel": memory_profile.get('memory_mapped') if type(memory_profile.get('memory_mapped')) is bool else None,



            "mmapSupported": True,



            "effectiveContext": context,



            "context": context,



            "runtimePresent": runtime_present,



            "gpuBackendPresent": runtime_present if backend == "lmstudio" else all((APP_DIR / name).is_file() for name in ("ggml-cuda.dll", "cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll")),



            "serverRunning": lm_server_running if backend == "lmstudio" else bundled_server_running,



            "backend": backend,



            "engineName": "Bionic/LM Studio" if backend == "lmstudio" else "Bundled Offline GPT engine",



            "lmStudioCliPresent": lm_cli_present,



            "bionicPresent": bionic_present,



            "backendProcessId": bionic_pid if backend == "lmstudio" else getattr(getattr(self.runtime, "process", None), "pid", None) if runtime_loaded and self.runtime else None,



            "modelInspection": inspection,



            **self.vision_model_status(),



        }







    def chat_identity_context(self, model_path=None):



        """Return the truthful identity of the model selected for the next reply.







        Prompt construction happens before the model process is started, so the



        selected file/metadata identity is authoritative for attribution.  Once a



        runtime exists, its actually loaded path wins.  Never return a hardcoded



        product name: callers must render whatever this method reports.



        """



        try:



            status = self.chat_status()



        except Exception:



            return {"displayName": "", "loaded": False, "loadState": "unknown",



                    "backend": str(self.cfg.get("chat_backend", "bundled")),



                    "identitySource": "unavailable"}



        loaded = bool(status.get("loaded") or status.get("runtimeLoaded"))

        display = (status.get("runtimeModelName") if loaded and status.get("runtimeModelName")

                   else status.get("modelName")) or ""

        path = (status.get("runtimeModelPath") if loaded and status.get("runtimeModelPath")

                else status.get("modelPath")) or ""

        # This prompt describes the next request, not a leftover loaded runtime.

        # Conversation overrides can differ from both the default and old runtime.

        if model_path and status.get('backend', self.cfg.get('chat_backend','bundled'))=='bundled':

            target=Path(self.resolve_model_path(model_path))

            same=lambda left,right: bool(left and right) and os.path.normcase(str(resolve_path(str(left))))==os.path.normcase(str(resolve_path(str(right))))

            target_loaded=loaded and same(target,status.get('runtimeModelPath') or path)

            if not same(target,path):

                display=target.name

                source='selected_filename_unverified'

                if same(target,status.get('modelPath')):

                    display=status.get('modelName') or display

                    source=status.get('modelIdentitySource') or source

                elif target.is_file():

                    try:

                        import model_inspection

                        meta=model_inspection.inspect_gguf(target).get('metadata',{})

                        display=model_display_name(meta.get('general.name',''),meta.get('general.file_type')) or display

                        source='untrusted_gguf_metadata'

                    except Exception:

                        pass

                status=dict(status,modelIdentitySource=source)

            path=str(target);loaded=target_loaded

            status=dict(status,loadState='ready' if loaded else 'not-loaded',modelName=display)



        return {



            "displayName": str(display)[:200],



            "modelPath": str(path)[:1000],



            "backend": str(status.get("backend") or self.cfg.get("chat_backend", "bundled")),



            "engineName": str(status.get("engineName") or ""),



            "loaded": loaded,



            "loadState": str(status.get("loadState") or "unknown"),



            "identitySource": str(status.get("modelIdentitySource") or "unknown"),



            "selectedModel": str(status.get("modelName") or "")[:200],



            "contextLength": status.get("effectiveContext"),



        }







    def record_chat_test(self, state, message="", answer=""):



        self.chat_test_state = str(state)



        self.chat_test_message = str(message)



        self.chat_test_answer = str(answer)[:240]



        self.chat_test_time = time.strftime("%Y-%m-%d %H:%M:%S")







    def _cancel_idle_timer(self):



        if self._idle_timer:



            try:



                self._idle_timer.cancel()



            except Exception:



                pass



            self._idle_timer = None







    def _schedule_idle_unload(self):



        """Schedule asynchronous idle unload that does NOT block response finalization."""



        self._cancel_idle_timer()



        mode = str(self.cfg.get("model_lifecycle_mode", self.model_lifecycle_mode)).strip().lower()



        if mode == "fast":



            return







        if mode == "low_ram":



            delay = 0.5  # Minimal async delay to avoid blocking response path



        else:



            # balanced mode



            try:



                delay = float(self.cfg.get("model_keepalive_seconds", self.model_keepalive_seconds))



            except (TypeError, ValueError):



                delay = 90.0







        gen_id = self._current_generation_id







        def timer_callback():



            self._check_and_idle_unload(gen_id)







        self._idle_timer = threading.Timer(delay, timer_callback)



        self._idle_timer.daemon = True



        self._idle_timer.start()







    def _check_and_idle_unload(self, generation_id):



        with self.lock:



            if self._current_generation_id != generation_id:



                return



            if self._active_inference_count > 0:



                return



            if not self.loaded_model:



                return



            mode = str(self.cfg.get("model_lifecycle_mode", self.model_lifecycle_mode)).strip().lower()



            if mode == "fast":



                return



            now = time.monotonic()



            keepalive = 0.5 if mode == "low_ram" else float(self.cfg.get("model_keepalive_seconds", self.model_keepalive_seconds))



            if now - self._last_request_time >= (keepalive - 0.2):



                reason = f"Keepalive expired ({mode} mode, {keepalive:.1f}s idle)"



                _runtime_logger.info("%s. Releasing local model engine asynchronously.", reason)



                self._unload_chat(reason=reason)







    def check_emergency_memory(self):



        """Emergency unload check: if no inference is active and available RAM is critical, unload."""



        with self.lock:



            if not self.loaded_model or self._active_inference_count > 0:



                return False



            memory = physical_memory_status()



            avail = memory.get("available")



            page_avail = memory.get("pagefile_available")



            try:



                threshold_mb = float(self.cfg.get("emergency_ram_threshold_mb", self.emergency_ram_threshold_mb))



            except (TypeError, ValueError):



                threshold_mb = 192.0



            threshold_bytes = threshold_mb * 1024 * 1024



            if (avail is not None and avail < threshold_bytes) or (page_avail is not None and page_avail < 256 * 1024 * 1024):



                reason = f"Emergency RAM threshold ({round((avail or 0) / (1024**2), 1)} MB < {threshold_mb} MB threshold)"



                _runtime_logger.warning("%s. Unloading idle model to protect system memory.", reason)



                self._unload_chat(reason=reason)



                return True



            return False







    @contextmanager



    def resource_lease(self,cancel_event=None):



        """Waiting for another local model must remain cancellable."""



        self._raise_if_cancelled(cancel_event)



        while not self.resource_lock.acquire(timeout=.2):



            self._raise_if_cancelled(cancel_event)



        try:



            self._raise_if_cancelled(cancel_event)



            yield



        finally:self.resource_lock.release()







    def chat_completion(self, messages, progress=lambda _s: None, on_token=lambda _t: None,



                        cancel_event=None, max_tokens=1200, temperature=0.2, connection_callback=None, top_p=None, allowed_tools=None, reasoning_effort=None, model=None, response_schema=None):



        with self.resource_lease(cancel_event):



            with self.lock:



                self._cancel_idle_timer()



                self._active_inference_count += 1



                self._current_generation_id += 1



            try:



                self.last_completion_identity={}



                self.ensure_chat(progress, model=model, cancel_event=cancel_event)



                backend = self.cfg.get('chat_backend','bundled')



                if backend=='bundled':



                    descriptor=getattr(self.runtime,'model_descriptor',None)



                    self.last_completion_identity={'backend':'bundled','modelName':self.loaded_model,



                        'modelPath':getattr(self.runtime,'model_path',None),



                        'architecture':descriptor.architecture if isinstance(descriptor,ModelInfo) else None,



                        'headerMetadataSha256':descriptor.header_sha256 if isinstance(descriptor,ModelInfo) else None,



                        'fileObservation':getattr(self.runtime,'model_file_observation',None),



                        'context':self.runtime.context,'identityScope':'file observation and inspected metadata; not full tensor verification',



                        'selectedModel':str(model or self.runtime.model_path),



                        'requestedModel':str(model or self.cfg.get('gpt_oss_gguf','')),



                        'configurationDefaultModel':str(self.cfg.get('gpt_oss_gguf','')),



                        'sessionId':getattr(self.runtime,'session_id',None),



                        'nativeReady':self.runtime.ready is True,'outputSource':'local_model',



                        'completionState':'GENERATING'}



                else:



                    # LM Studio remains a local loopback route, but its



                    # process/model is not owned by OfflineGPT. Preserve that



                    # distinction while exposing the same provenance contract



                    # as the bundled runtime.



                    selected = self.lm_runtime.loaded_model or self.cfg.get('chat_model','')



                    self.last_completion_identity={



                        'backend':'lmstudio',



                        'modelName':str(selected),



                        'selectedModel':str(selected),



                        'requestedModel':str(model or self.cfg.get('chat_model','')),



                        'configurationDefaultModel':str(self.cfg.get('chat_model','')),



                        'identityScope':'loopback runtime reported model identity; process and weights are externally managed',



                        'nativeAcceptance':'not_established',



                        'runtimeReady':True,



                        'outputSource':'local_model',



                        'completionState':'GENERATING',



                    }



                adapter = ExistingTextAdapter(self, self.cfg.get("chat_backend", "bundled"))



                generation_started=time.monotonic()



                first_visible=[]



                def attributed_token(text):



                    if text and not first_visible:



                        first_visible.append(time.monotonic())



                        self.last_completion_identity['firstVisibleTokenMs']=round((first_visible[0]-generation_started)*1000,2)



                    on_token(text)



                structured_options={'response_schema':response_schema} if response_schema is not None else {}



                result = adapter.complete(



                    messages, max_tokens=max_tokens, temperature=temperature,



                    cancel_event=cancel_event, on_token=attributed_token, progress=progress,



                    connection_callback=connection_callback, top_p=top_p,



                    allowed_tools=allowed_tools, reasoning_effort=reasoning_effort,**structured_options,



                )



                diagnostics=(getattr(self.runtime,'last_generation_diagnostics',{})



                             if backend=='bundled' else



                             getattr(self.lm_runtime,'last_generation_diagnostics',{}))



                partial=bool(diagnostics.get('stream_error')) or diagnostics.get('finish_reason') in {'length','cancelled','error'}



                if backend=='lmstudio' and diagnostics.get('stream_terminated') is False:



                    partial=True



                self.last_completion_identity.update({'completionState':'PARTIAL' if partial else 'COMPLETED','responseComplete':not partial,



                    'completionReason':diagnostics.get('finish_reason'),



                    'generatedTokens':diagnostics.get('generated_token_count'),



                    'promptTokens':diagnostics.get('prompt_token_count'),



                    'generationMs':round((time.monotonic()-generation_started)*1000,2),



                    'toolRequest':isinstance(result,ToolCallCompletion),



                    'streamTerminated':diagnostics.get('stream_terminated'),



                    'reasoningPresent':bool(diagnostics.get('reasoning_present')),



                    'reasoningTokens':diagnostics.get('reasoning_tokens')})



                self.record_chat_test("partial" if partial else "passed",



                    "The selected text engine returned partial text; review its completion reason." if partial else "The selected local text engine returned a complete response.", result)



                return result



            except Exception as exc:



                if getattr(self,'last_completion_identity',None):self.last_completion_identity['completionState']='FAILED'



                if str(exc).lower() == "cancelled":



                    self.record_chat_test("cancelled", "The response test was cancelled.")



                else:



                    self.record_chat_test("failed", str(exc))



                raise



            finally:



                with self.lock:



                    self._active_inference_count = max(0, self._active_inference_count - 1)



                    self._last_request_time = time.monotonic()



                    self._schedule_idle_unload()



                threading.Thread(target=self.check_emergency_memory, daemon=True).start()







    @staticmethod



    def _raise_if_cancelled(cancel_event):



        if cancel_event is not None and cancel_event.is_set():



            raise RuntimeError("Cancelled")







    def prepare_speech(self, cancel_event=None):



        """Reserve CPU memory for Kokoro without holding up the Qt GUI thread."""



        with self.resource_lease(cancel_event), self.lock:



            available = physical_memory_status().get('available')



            if available is not None and available < 2 * 1024**3:



                if getattr(self,'secondary_release',None):self.secondary_release(purpose='speech')



                self._unload_chat(reason='Memory reserved for local speech playback')



            self._raise_if_cancelled(cancel_event)



            available = physical_memory_status().get('available')



            if available is not None and available < 700 * 1024**2:



                raise RuntimeError('Not enough memory is available for local speech playback. Retry when more memory is available.')







    def _unload_chat(self, graceful=True, reason=""):



        if reason:



            self.last_unload_reason = reason



        self._cancel_idle_timer()



        was_loaded = bool(self.loaded_model)



        if self.runtime:



            self.runtime.stop(graceful=graceful)



        try:



            self.lm_runtime.unload(stop_server=True)



        except Exception:



            pass



        self.loaded_model = ""



        self.active_chat_backend = ""



        self.active_gpu_layers = None



        self.chat_memory_profile = None



        if was_loaded or self.chat_load_state in ("loading", "ready"):



            self.chat_load_state = "unloaded"



        # Tell the UI (status bar, model picker, Models page) about every unload.



        for listener in list(getattr(self, "state_listeners", None) or []):



            try:



                listener(reason)



            except Exception:



                _runtime_logger.debug("Model state listener failed", exc_info=True)







    def image_path(self, key, optional=False):



        value = str(self.cfg.get(key, "")).strip()



        if not value:



            if optional:



                return None



            raise RuntimeError(f"Choose the {key.replace('_', ' ')} path in Settings.")



        return resolve_path(value)







    def image_devices(self, cli, cancel_event=None, timeout=20):



        """Ask sd-cli which compute devices it can actually initialize."""



        command = [str(cli), "--list-devices"]



        process = subprocess.Popen(



            command, cwd=str(Path(cli).parent), stdout=subprocess.PIPE,



            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",



            creationflags=self._hidden_flags(),



        )



        tracked = cancel_event is not None



        if tracked:



            self.track_image_process(process)



        started = time.monotonic()



        try:



            while True:



                if cancel_event is not None and cancel_event.is_set():



                    self._terminate_process(process)



                    raise RuntimeError("Cancelled")



                try:



                    output, _ = process.communicate(timeout=0.2)



                    break



                except subprocess.TimeoutExpired:



                    if time.monotonic() - started >= timeout:



                        self._terminate_process(process)



                        raise RuntimeError("Checking the image engine's available devices timed out.")



            if process.returncode:



                detail=(output or "").strip()[-1200:]



                raise RuntimeError("Could not check the image engine's compute devices."+(f"\n{detail}" if detail else ""))



            devices=[]



            for line in (output or "").splitlines():



                name=line.strip().split("\t",1)[0].strip().lower()



                if name and (name == "cpu" or name.startswith(("cuda", "vulkan", "metal", "hip", "sycl", "opencl"))):



                    devices.append(name)



            return devices, output or ""



        finally:



            if tracked:



                self.track_image_process(None)







    def image_capabilities(self,cli):



        """Read installed flags once per executable version, never assume upstream flags."""



        cli=Path(cli);key=(str(cli.resolve()),cli.stat().st_size,cli.stat().st_mtime_ns)



        cached=getattr(self,'_image_capability_cache',None)



        if cached and cached[0]==key:return cached[1]



        try:



            result=subprocess.run([str(cli),'--help'],cwd=cli.parent,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10,creationflags=self._hidden_flags())



            text=result.stdout+result.stderr if result.returncode==0 else ''



        except (OSError,subprocess.TimeoutExpired):text=''



        flags={flag for flag in ('--auto-fit','--sage-attn','-r','--ref-image','--ip-adapter-image','--init-img') if flag in text}



        self._image_capability_cache=(key,flags);return flags







    def prepare_image_engine(self, progress=lambda _s: None, cancel_event=None):



        """Release GPT-OSS before a direct, one-shot image inference process."""



        owner = threading.get_ident()



        while not self.resource_lock.acquire(timeout=.2):



            self._raise_if_cancelled(cancel_event)



        self._image_resource_owner = owner

        from knowledge_engine import LocalEmbedding

        LocalEmbedding.clear_cache()



        try:



            with self.lock:



                if self.shutting_down:



                    raise RuntimeError("Offline GPT is closing and cannot start an image job.")



                if getattr(self,'secondary_release',None):self.secondary_release()



                self._unload_chat_cancellable(progress, cancel_event)



        except Exception:



            self._image_resource_owner = None



            self.resource_lock.release()



            raise







    def _unload_chat_cancellable(self, progress, cancel_event):



        self._raise_if_cancelled(cancel_event)



        self.last_unload_reason = "Resource handoff to local vision or image engine"



        if self.lm_runtime.loaded_model:



            self.lm_runtime.unload(progress, cancel_event, stop_server=False)



        elif self.cfg.get("chat_backend") == "lmstudio" and self.lm_runtime.started_server:



            self.lm_runtime.unload_all(progress,cancel_event)



        if self.runtime and self.runtime.ready:



            progress("Releasing the bundled GPT-OSS engine before image generation…")



            self.runtime.stop()



            time.sleep(0.5)



        self.loaded_model = ""



        self.active_chat_backend = ""



        self.active_gpu_layers = None



        self.chat_memory_profile = None



        if self.chat_load_state in ("ready", "loading"):



            self.chat_load_state = "unloaded"







    def track_image_process(self, process):



        with self.lock:



            self.image_process = process



            should_stop = self.shutting_down and process is not None



        if should_stop:



            self._terminate_process(process)







    def _terminate_process(self, process):



        if process and process.poll() is None:



            if sys.platform == "win32":



                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],



                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,



                               timeout=20, creationflags=self._hidden_flags())



            else:



                process.terminate()



            try:



                process.wait(timeout=10)



            except subprocess.TimeoutExpired:



                process.kill()



                process.wait(timeout=5)



        with self.lock:



            if self.image_process is process:



                self.image_process = None







    def stop_image_process(self):



        with self.lock:



            process = self.image_process



        if process:



            self._terminate_process(process)







    def release_image_engine(self):



        # sd-cli is a one-shot process; it exits and releases its model weights itself.



        if self._image_resource_owner == threading.get_ident():



            self._image_resource_owner = None



            self.resource_lock.release()







    def shutdown(self):



        if getattr(self,'secondary_release',None):self.secondary_release()



        with self.lock:



            self.shutting_down = True



            process = self.image_process



        if process:



            self._terminate_process(process)



        with self.lock:



            self._unload_chat()



