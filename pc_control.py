"""Typed, allowlisted PC controls for the local assistant (Windows).

No shell or general command runner: every tool has fixed, validated arguments, and each one
declares a risk tier. "low" tools may run immediately when the user enables that; "confirm"
tools always need the user's approval first. Nothing here touches the network.
"""
from __future__ import annotations

import ctypes
import datetime as _dt
import os
import re
import subprocess
import threading
import time
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Virtual-key codes for media/volume keys (sent like a keyboard would).
VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2, "mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF}

SETTINGS_PAGES = {
    "wifi": "ms-settings:network-wifi", "network": "ms-settings:network", "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display", "night light": "ms-settings:nightlight", "sound": "ms-settings:sound",
    "battery": "ms-settings:batterysaver", "power": "ms-settings:powersleep", "update": "ms-settings:windowsupdate",
    "apps": "ms-settings:appsfeatures", "notifications": "ms-settings:notifications", "privacy": "ms-settings:privacy",
    "storage": "ms-settings:storagesense", "personalization": "ms-settings:personalization", "gaming": "ms-settings:gaming-gamemode",
    "mouse": "ms-settings:mousetouchpad", "keyboard": "ms-settings:typing", "date and time": "ms-settings:dateandtime",
    "accounts": "ms-settings:yourinfo", "default apps": "ms-settings:defaultapps", "settings": "ms-settings:",
}
SETTINGS_ALIASES = {"wi-fi": "wifi", "wireless": "wifi", "internet": "network", "brightness": "display", "volume": "sound",
                    "audio": "sound", "updates": "update", "windows update": "update", "game mode": "gaming", "time": "date and time"}


def _known_folders() -> dict:
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return {"downloads": home / "Downloads", "documents": home / "Documents", "desktop": home / "Desktop", "pictures": home / "Pictures",
            "music": home / "Music", "videos": home / "Videos", "home": home}


FOLDER_ALIASES = {"download": "downloads", "document": "documents", "my documents": "documents", "photos": "pictures",
                  "images": "pictures", "picture": "pictures", "video": "videos", "movies": "videos", "user folder": "home"}


class Tool:
    def __init__(self, name, risk, summary, params, fn):
        self.name, self.risk, self.summary, self.params, self.fn = name, risk, summary, params, fn


class PCControl:
    """Holds the tool implementations. OS access is injectable for tests."""

    def __init__(self, keypress=None, starter=None, runner=None, screenshot=None, notify=None, app_index=None):
        self.keypress = keypress or self._send_key
        self.starter = starter or getattr(os, "startfile", None)
        self.runner = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=20, creationflags=CREATE_NO_WINDOW))
        self.screenshot_fn = screenshot
        self.notify = notify or (lambda message: None)
        self.app_index = app_index
        self.timers: dict[str, threading.Timer] = {}
        self.tools = {t.name: t for t in self._catalog()}

    # ------------------------------------------------------------------ OS primitives
    @staticmethod
    def _send_key(vk: int):
        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0); user32.keybd_event(vk, 0, 2, 0)

    def _start(self, target: str):
        if self.starter is None:
            raise RuntimeError("Opening items is only supported on Windows.")
        self.starter(target)

    # ------------------------------------------------------------------ tools
    def media(self, action: str):
        if action not in {"play_pause", "next", "previous", "stop"}:
            raise ValueError("Unknown media action.")
        self.keypress(VK[action])
        return {"ok": True, "message": {"play_pause": "Play/pause sent.", "next": "Next track.", "previous": "Previous track.", "stop": "Stopped playback."}[action]}

    def volume(self, change: str = "", level: int | None = None):
        if level is not None:
            level = max(0, min(100, int(level)))
            for _ in range(50): self.keypress(VK["volume_down"])  # each key step is 2%
            for _ in range(round(level / 2)): self.keypress(VK["volume_up"])
            return {"ok": True, "message": f"Volume set to about {level}%."}
        if change == "mute":
            self.keypress(VK["mute"]); return {"ok": True, "message": "Mute toggled."}
        steps = 5
        key = VK["volume_up"] if change == "up" else VK["volume_down"] if change == "down" else None
        if key is None:
            raise ValueError("Say volume up, down, mute or a level.")
        for _ in range(steps): self.keypress(key)
        return {"ok": True, "message": f"Volume {change} ~{steps * 2}%."}

    def brightness(self, level: int | None = None, change: str = ""):
        current = None
        out = self.runner(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                           "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop).CurrentBrightness"])
        try:
            current = int(str(getattr(out, "stdout", "")).strip().splitlines()[0])
        except (ValueError, IndexError):
            current = None
        if level is None:
            if current is None:
                raise RuntimeError("This display does not support brightness control from Windows (external monitors usually don't).")
            level = current + (20 if change == "up" else -20)
        level = max(0, min(100, int(level)))
        result = self.runner(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop) | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness={level}}}"])
        if getattr(result, "returncode", 0) != 0:
            raise RuntimeError("This display does not support brightness control from Windows (external monitors usually don't).")
        return {"ok": True, "message": f"Brightness {level}%."}

    def open_folder(self, name: str):
        key = FOLDER_ALIASES.get(name.strip().lower(), name.strip().lower())
        folder = _known_folders().get(key)
        if folder is None:
            raise ValueError("Known folders: downloads, documents, desktop, pictures, music, videos.")
        self._start(str(folder)); return {"ok": True, "message": f"Opened {key.capitalize()}."}

    def open_settings(self, page: str = "settings"):
        key = SETTINGS_ALIASES.get(page.strip().lower(), page.strip().lower())
        uri = SETTINGS_PAGES.get(key)
        if uri is None:
            raise ValueError("Settings pages: " + ", ".join(sorted(SETTINGS_PAGES)))
        self._start(uri); return {"ok": True, "message": f"Opened {key} settings."}

    def open_app(self, name: str):
        if not self.app_index:
            raise RuntimeError("App index unavailable.")
        matches = self.app_index.resolve(name)
        if not matches:
            raise RuntimeError(f"I couldn't find {name} installed on this PC.")
        self._start(matches[0]["target"]); return {"ok": True, "message": f"Opening {matches[0]['name']}."}

    def close_app(self, name: str):
        exe = re.sub(r"[^A-Za-z0-9 ._-]", "", name).strip()
        if not exe:
            raise ValueError("Which app should I close?")
        image = exe if exe.lower().endswith(".exe") else exe.replace(" ", "") + ".exe"
        if image.lower() in {"explorer.exe", "offline studio.exe", "offlinestudio.exe", "winlogon.exe", "csrss.exe", "svchost.exe", "lsass.exe"}:
            raise RuntimeError("I won't close a system process or Offline Studio itself.")
        # Graceful close request (no /F): the app may ask to save unsaved work.
        result = self.runner(["taskkill", "/IM", image])
        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError(f"{exe} doesn't seem to be running.")
        return {"ok": True, "message": f"Asked {exe} to close."}

    def screenshot(self):
        if not self.screenshot_fn:
            raise RuntimeError("Screenshots are unavailable.")
        folder = _known_folders()["pictures"] / "Offline Studio"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"Screenshot {_dt.datetime.now():%Y-%m-%d %H.%M.%S}.png"
        self.screenshot_fn(str(path))
        return {"ok": True, "message": f"Screenshot saved to {path}.", "path": str(path)}

    def timer(self, minutes: float, label: str = ""):
        minutes = float(minutes)
        if not 0 < minutes <= 24 * 60:
            raise ValueError("Timers can be 1 second to 24 hours.")
        tid = f"t{int(time.time() * 1000)}"
        text = label.strip() if label.strip().startswith("Reminder:") else (label.strip() or "Timer") + " is done."
        t = threading.Timer(minutes * 60, lambda: (self.timers.pop(tid, None), self.notify(text)))
        t.daemon = True; t.start(); self.timers[tid] = t
        if label.strip().startswith("Reminder:"):
            return {"ok": True, "message": f"Okay, I'll remind you in {self._fmt_minutes(minutes)}: {label.strip()[9:].strip()}.", "timerId": tid}
        return {"ok": True, "message": f"Timer set for {self._fmt_minutes(minutes)}" + (f" ({label.strip()})." if label.strip() else "."), "timerId": tid}

    @staticmethod
    def _fmt_minutes(minutes: float) -> str:
        if minutes < 1: return f"{round(minutes * 60)} seconds"
        if minutes < 60: return f"{minutes:g} minute" + ("" if minutes == 1 else "s")
        return f"{minutes / 60:g} hour" + ("" if minutes == 60 else "s")

    def system_status(self):
        info = {}
        try:
            class MEM(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong), ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong), ("ve", ctypes.c_ulonglong)]
            m = MEM(); m.len = ctypes.sizeof(MEM); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            info["memory"] = f"{m.load}% RAM used ({m.avail / 2**30:.1f} GB free of {m.total / 2**30:.0f} GB)"
            class PWR(ctypes.Structure):
                _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("pct", ctypes.c_byte), ("saver", ctypes.c_byte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
            p = PWR(); ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p))
            if 0 <= p.pct <= 100:
                info["battery"] = f"{p.pct}% battery" + (", charging" if p.ac == 1 else ", on battery")
        except Exception:
            pass
        info["time"] = _dt.datetime.now().strftime("%A %d %B, %I:%M %p")
        return {"ok": True, "message": "; ".join(info.values()), "status": info}

    def find_files(self, query: str, limit: int = 8):
        q = query.strip().lower()
        if len(q) < 2:
            raise ValueError("Tell me part of the file name.")
        words = [w for w in re.split(r"\W+", q) if w]
        hits, scanned, deadline = [], 0, time.monotonic() + 3.0
        for key in ("desktop", "documents", "downloads", "pictures", "music", "videos"):
            root = _known_folders()[key]
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in {"node_modules", "appdata", "$recycle.bin"}]
                for f in filenames:
                    scanned += 1
                    low = f.lower()
                    if all(w in low for w in words):
                        p = Path(dirpath) / f
                        try: mtime = p.stat().st_mtime
                        except OSError: mtime = 0
                        hits.append((mtime, str(p)))
                if time.monotonic() > deadline or scanned > 200000:
                    break
        hits.sort(reverse=True)
        files = [p for _, p in hits[:limit]]
        return {"ok": True, "message": (f"Found {len(files)} file(s)." if files else f"No files matching “{query}” in your folders."), "files": files}

    def open_file(self, path: str):
        p = Path(path)
        home = _known_folders()["home"].resolve()
        if not p.is_file() or home not in p.resolve().parents:
            raise RuntimeError("I can only open files from your user folders that were found by a search.")
        if p.suffix.lower() in {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".scr", ".com", ".lnk", ".reg"}:
            raise RuntimeError("I don't open programs or scripts from files; ask me to open the app by name instead.")
        self._start(str(p)); return {"ok": True, "message": f"Opened {p.name}."}

    def show_desktop(self):
        self.combo([0x5B, 0x44]); return {"ok": True, "message": "Showing the desktop."}  # Win+D

    def combo(self, keys):
        if self.keypress is not self._send_key:
            for k in keys: self.keypress(k)
            return
        user32 = ctypes.windll.user32
        for k in keys: user32.keybd_event(k, 0, 0, 0)
        for k in reversed(keys): user32.keybd_event(k, 0, 2, 0)

    def open_website(self, url: str):
        url = url.strip()
        if not re.match(r"^https?://", url, re.I):
            if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}(?:/\S*)?", url, re.I):
                raise ValueError("Give me a web address like youtube.com.")
            url = "https://" + url
        self._start(url); return {"ok": True, "message": f"Opened {url}."}

    def lock(self):
        ctypes.windll.user32.LockWorkStation(); return {"ok": True, "message": "PC locked."}

    def sleep(self):
        # SetSuspendState(hibernate=False, force=False, disableWake=False)
        threading.Timer(1.5, lambda: ctypes.windll.powrprof.SetSuspendState(0, 0, 0)).start()
        return {"ok": True, "message": "Going to sleep."}

    # ------------------------------------------------------------------ catalog
    def _catalog(self):
        return [
            Tool("open_app", "low", "Open an installed app or game", {"name": "app or game name"}, lambda a: self.open_app(a["name"])),
            Tool("close_app", "confirm", "Close a running app (it may ask to save)", {"name": "app name, e.g. spotify or chrome"}, lambda a: self.close_app(a["name"])),
            Tool("media", "low", "Media keys", {"action": "play_pause | next | previous | stop"}, lambda a: self.media(a["action"])),
            Tool("volume", "low", "Change or set the volume", {"change": "up | down | mute (optional)", "level": "0-100 (optional)"},
                 lambda a: self.volume(a.get("change", ""), int(a["level"]) if str(a.get("level", "")).strip() not in {"", "None"} else None)),
            Tool("brightness", "low", "Change or set screen brightness", {"change": "up | down (optional)", "level": "0-100 (optional)"},
                 lambda a: self.brightness(int(a["level"]) if str(a.get("level", "")).strip() not in {"", "None"} else None, a.get("change", ""))),
            Tool("open_folder", "low", "Open a user folder", {"name": "downloads | documents | desktop | pictures | music | videos"}, lambda a: self.open_folder(a["name"])),
            Tool("open_settings", "low", "Open a Windows Settings page", {"page": "wifi | bluetooth | display | sound | battery | update | ..."}, lambda a: self.open_settings(a.get("page", "settings"))),
            Tool("screenshot", "low", "Save a screenshot to Pictures\\Offline Studio", {}, lambda a: self.screenshot()),
            Tool("timer", "low", "Start a timer", {"minutes": "number", "label": "optional"}, lambda a: self.timer(float(a["minutes"]), a.get("label", ""))),
            Tool("system_status", "low", "Battery level and whether it is charging, memory use, date and time", {}, lambda a: self.system_status()),
            Tool("show_desktop", "low", "Minimize all windows / show the desktop", {}, lambda a: self.show_desktop()),
            Tool("open_website", "low", "Open a web page in the default browser", {"url": "https://... or a site like youtube.com"}, lambda a: self.open_website(a["url"])),
            Tool("find_files", "low", "Find files in your user folders by name", {"query": "part of the file name"}, lambda a: self.find_files(a["query"])),
            Tool("open_file", "confirm", "Open a file found by find_files", {"path": "full path from find_files"}, lambda a: self.open_file(a["path"])),
            Tool("lock_pc", "confirm", "Lock the PC", {}, lambda a: self.lock()),
            Tool("sleep_pc", "confirm", "Put the PC to sleep", {}, lambda a: self.sleep()),
        ]

    def run(self, name: str, args: dict | None = None) -> dict:
        tool = self.tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        return tool.fn(dict(args or {}))


# ---------------------------------------------------------------------- fast command rules
_NUM = r"(\d{1,3})"
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty five": 45, "sixty": 60, "a": 1, "an": 1}


_CONTROL_HINT = re.compile(r"\b(?:timer|alarm|remind|countdown|volume|louder|quieter|mute|unmute|brightness|brighter|dimmer|screenshot|screen\s?shot|"
                           r"lock|sleep|shut\s?down|restart|pause|resume|skip|next|previous|song|track|music|play|open|launch|start|close|quit|"
                           r"folder|downloads|documents|desktop|settings|wi-?fi|bluetooth|battery|charging|find|search\s+for|file|minimi[sz]e|"
                           r"gaming|game\s+mode|power\s+mode|website)\b", re.I)


def action_candidate(text: str) -> bool:
    """Short utterances that look like PC control and deserve one planning pass by the local model."""
    t = (text or "").strip()
    return 0 < len(t) <= 160 and bool(_CONTROL_HINT.search(t)) and not re.match(r"^(?:how|why|what\s+is|what\s+are|explain|tell\s+me\s+about)\b", t, re.I)


def _reminder(t: str, unit_word: str) -> dict | None:
    """"remind me in 10 minutes to check the oven", "remind me to call mom at 5 pm", "set an alarm for 7:30 am",
    "wake me up in 20 minutes". Runs as a timer whose alert reads "Reminder: <what>"."""
    amount = r"(\d+(?:\.\d+)?|an?|one|two|three|five|ten|fifteen|twenty|thirty|forty five|sixty|half an)"
    rel = re.compile(r"in\s+" + amount + r"\s+" + unit_word + r"s?")
    m = re.fullmatch(r"(?:remind\s+me|set\s+(?:a\s+|an\s+)?(?:reminder|alarm)|wake\s+me(?:\s+up)?|alert\s+me|ping\s+me)\s*(?:for\s+|to\s+|about\s+|that\s+)?(.*)", t)
    if not m:
        return None
    rest = m.group(1).strip()
    minutes = None
    r = rel.search(rest)
    if r:
        n, unit = r.group(1), r.group(2)
        num = 0.5 if n == "half an" else float(n) if re.match(r"\d", n) else _WORD_NUM.get(n)
        if not num:
            return None
        minutes = num / 60 if unit.startswith("sec") else num * 60 if unit.startswith("h") else num
        rest = (rest[:r.start()] + " " + rest[r.end():]).strip()
    else:
        r = re.search(r"(?:\bat\s+|\bfor\s+)?\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\bat\s+\d{1,2}(?::\d{2})?\b|\b(?:tonight|this evening)\b", rest)
        if not r:
            return None
        import assistant_actions as aa
        when = aa.parse_when(r.group(0) if r.group(0).strip().startswith("at") else "at " + r.group(0).replace("for ", "").strip())
        if not when:
            return None
        minutes = (when - _dt.datetime.now()).total_seconds() / 60
        rest = (rest[:r.start()] + " " + rest[r.end():]).strip()
    rest = re.sub(r"^(?:to|that|about|for)\s+|\s+(?:to|that|about)$", "", re.sub(r"\s+", " ", rest)).strip(" ,")
    if not 0 < minutes <= 24 * 60:
        return None
    label = "Reminder: " + (rest[:1].upper() + rest[1:] if rest else ("Wake up" if t.startswith("wake") else "Alarm" if "alarm" in t else "Time's up"))
    return {"tool": "timer", "args": {"minutes": round(minutes, 3), "label": label}}


def quick_command(text: str) -> list[dict] | None:
    """Instant, model-free parsing of common single commands. Returns a list of steps or None."""
    t = re.sub(r"[.!?]+$", "", (text or "").strip().lower())
    t = re.sub(r"^(?:hey\s+\w+[,!]?\s+|ok(?:ay)?[,]?\s+|please\s+|can you\s+|could you\s+|would you\s+)+", "", t).strip()
    t = re.sub(r"\s+(?:please|for me|now)$", "", t)
    if not t or len(t) > 120:
        return None
    m = re.fullmatch(r"(?:set\s+(?:the\s+)?)?volume\s+(?:to\s+)?" + _NUM + r"\s*(?:%|percent)?|(?:set|turn)\s+(?:the\s+)?volume\s+(?:to\s+)?" + _NUM + r"\s*(?:%|percent)?", t)
    if m: return [{"tool": "volume", "args": {"level": int(m.group(1) or m.group(2))}}]
    if re.fullmatch(r"(?:turn\s+(?:the\s+)?)?volume\s+up|turn\s+(?:it|the\s+volume)\s+up|louder|increase\s+(?:the\s+)?volume", t): return [{"tool": "volume", "args": {"change": "up"}}]
    if re.fullmatch(r"(?:turn\s+(?:the\s+)?)?volume\s+down|turn\s+(?:it|the\s+volume)\s+down|quieter|lower\s+(?:the\s+)?volume|decrease\s+(?:the\s+)?volume", t): return [{"tool": "volume", "args": {"change": "down"}}]
    if re.fullmatch(r"(?:un)?mute(?:\s+(?:the\s+)?(?:volume|sound|audio|pc|computer))?", t): return [{"tool": "volume", "args": {"change": "mute"}}]
    if re.fullmatch(r"(?:pause|resume|play)(?:\s+(?:the\s+)?(?:music|song|video|media|playback))?", t): return [{"tool": "media", "args": {"action": "play_pause"}}]
    if re.fullmatch(r"(?:next|skip)(?:\s+(?:the\s+)?(?:song|track|one|video))?", t): return [{"tool": "media", "args": {"action": "next"}}]
    if re.fullmatch(r"(?:previous|go back|last)(?:\s+(?:song|track|one|video))?", t): return [{"tool": "media", "args": {"action": "previous"}}]
    m = re.fullmatch(r"(?:set\s+(?:the\s+)?)?brightness\s+(?:to\s+)?" + _NUM + r"\s*(?:%|percent)?", t)
    if m: return [{"tool": "brightness", "args": {"level": int(m.group(1))}}]
    if re.fullmatch(r"(?:turn\s+(?:the\s+)?)?brightness\s+up|brighter|increase\s+(?:the\s+)?brightness", t): return [{"tool": "brightness", "args": {"change": "up"}}]
    if re.fullmatch(r"(?:turn\s+(?:the\s+)?)?brightness\s+down|dimmer|dim\s+(?:the\s+)?screen|lower\s+(?:the\s+)?brightness|decrease\s+(?:the\s+)?brightness", t): return [{"tool": "brightness", "args": {"change": "down"}}]
    if re.fullmatch(r"(?:take\s+a\s+)?screen\s?shot|capture\s+(?:the\s+|my\s+)?screen", t): return [{"tool": "screenshot", "args": {}}]
    if re.fullmatch(r"lock(?:\s+(?:the|my))?\s+(?:pc|computer|laptop|screen)", t): return [{"tool": "lock_pc", "args": {}}]
    if re.fullmatch(r"(?:put\s+(?:the\s+|my\s+)?(?:pc|computer|laptop)\s+to\s+sleep|go\s+to\s+sleep|sleep\s+(?:mode|the\s+pc))", t): return [{"tool": "sleep_pc", "args": {}}]
    # Whisper often hears "minute" as "unit", "minit" or "minnit"; accept those only inside a timer phrase.
    unit_word = r"(second|sec|minute|min|minit|minnit|unit|hour|hr)"
    m = re.fullmatch(r"(?:set\s+(?:a\s+|the\s+)?|start\s+(?:a\s+|the\s+)?|put\s+(?:a\s+)?)?(?:timer\s+(?:for\s+|of\s+|to\s+)?(\d+|\w+(?:\s+five)?)\s+" + unit_word + r"s?(?:\s+(?:for|called)\s+(.+))?|(\d+|\w+)\s+" + unit_word + r"s?\s+timer(?:\s+(?:for|called)\s+(.+))?)", t)
    if m:
        n, unit, label = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        num = float(n) if n.isdigit() else _WORD_NUM.get(n)
        if num:
            minutes = num / 60 if unit.startswith("sec") else num * 60 if unit.startswith("h") else num
            return [{"tool": "timer", "args": {"minutes": minutes, "label": label or ""}}]
    reminder = _reminder(t, unit_word)
    if reminder: return [reminder]
    if re.fullmatch(r"show\s+(?:me\s+)?(?:the\s+)?desktop|minimi[sz]e\s+(?:all|everything)(?:\s+windows)?|hide\s+(?:all\s+)?(?:the\s+)?windows", t):
        return [{"tool": "show_desktop", "args": {}}]
    m = re.fullmatch(r"(?:open|show|go to)\s+(?:my\s+|the\s+)?(downloads?|documents?|desktop|pictures?|photos|images|music|videos?|movies)(?:\s+folder)?", t)
    if m: return [{"tool": "open_folder", "args": {"name": m.group(1)}}]
    m = re.fullmatch(r"(?:open\s+)?(?:the\s+)?(wi-?fi|wifi|bluetooth|display|sound|battery|update|windows update|notifications?|privacy|storage|night light|network|default apps|date and time)\s+settings|open\s+settings(?:\s+for\s+(.+))?", t)
    if m: return [{"tool": "open_settings", "args": {"page": (m.group(1) or m.group(2) or "settings").replace("notification", "notifications").replace("notificationss", "notifications")}}]
    m = re.fullmatch(r"(?:close|quit|exit|kill)\s+(?:the\s+)?(.+?)(?:\s+app)?", t)
    if m and not re.search(r"\b(?:voice|live|chat|session|conversation|this|window|tab)\b", m.group(1)):
        return [{"tool": "close_app", "args": {"name": m.group(1)}}]
    m = re.fullmatch(r"(?:open|go to|visit)\s+((?:https?://)?[a-z0-9.-]+\.(?:com|org|net|io|in|dev|ai|co|edu|gov|tv|me)(?:/\S*)?)", t)
    if m: return [{"tool": "open_website", "args": {"url": m.group(1)}}]
    if re.fullmatch(r"(?:what(?:'s| is)\s+(?:my\s+)?(?:battery|system status|pc status)|battery(?:\s+level)?|system status|how(?:'s| is)\s+my\s+(?:pc|computer|battery)|is\s+my\s+(?:laptop|pc|computer)\s+charging(?:\s+right)?(?:\s+now)?)", t):
        return [{"tool": "system_status", "args": {}}]
    m = re.fullmatch(r"(?:find|search for|look for|where is)\s+(?:my\s+|the\s+)?(?:file\s+(?:called\s+|named\s+)?)?(.+?)(?:\s+file)?", t)
    if m and len(m.group(1)) >= 2: return [{"tool": "find_files", "args": {"query": m.group(1)}}]
    return None
