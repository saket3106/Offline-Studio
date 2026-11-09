"""Local assistant actions: launch installed apps/games, switch power/gaming mode,
compose + schedule + send email. Deterministic, allowlisted, approval-gated.

Safety: there is no shell or general command runner. Apps come only from what is
installed on this PC (Start menu shortcuts, Steam and Epic manifests). Power plans come
only from `powercfg /list`. Email goes only through the user's configured SMTP account.
Every action is previewed first and runs only after the user confirms it (UI click or
spoken "yes"); text found in documents or web pages never triggers an action.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import json
import os
import re
import smtplib
import ssl
import subprocess
import threading
import time
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

# ---------------------------------------------------------------- app discovery

ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x"}
ALIASES = {
    "gta": "grand theft auto v", "gta 5": "grand theft auto v", "gta v": "grand theft auto v", "gtav": "grand theft auto v",
    "gta 4": "grand theft auto iv", "rdr2": "red dead redemption 2", "rdr 2": "red dead redemption 2",
    "cs2": "counter-strike 2", "csgo": "counter-strike 2", "cod": "call of duty", "valo": "valorant",
    "lol": "league of legends", "vs code": "visual studio code", "vscode": "visual studio code",
    "chrome": "google chrome", "word": "word", "excel": "excel", "files": "file explorer", "explorer": "file explorer",
    "settings": "settings", "calculator": "calculator", "notepad": "notepad",
}
SKIP_SHORTCUT = re.compile(r"\b(uninstall|readme|help|manual|website|license|release notes|documentation|support|eula)\b", re.I)
BUILTIN_APPS = [
    {"name": "Notepad", "source": "windows", "target": "notepad.exe"},
    {"name": "Calculator", "source": "windows", "target": "calc.exe"},
    {"name": "File Explorer", "source": "windows", "target": "explorer.exe"},
    {"name": "Settings", "source": "windows", "target": "ms-settings:"},
    {"name": "Task Manager", "source": "windows", "target": "taskmgr.exe"},
]


def _norm(text: str) -> str:
    text = re.sub(r"[™®©:'’\-_.]", " ", str(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def _romanize(text: str) -> str:
    return " ".join(ROMAN.get(tok, tok) for tok in _norm(text).split())


def _acronym(text: str) -> str:
    toks = _romanize(text).split()
    return "".join(t if t in ROMAN.values() or t.isdigit() else t[0] for t in toks if t)


def _read_vdf_paths(text: str) -> list[str]:
    return [m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"([^"]+)"', text)]


def steam_root() -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except Exception:
        for guess in (Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",):
            if guess.is_dir():
                return guess
    return None


def steam_games(root: Path | None = None) -> list[dict]:
    root = root or steam_root()
    if not root:
        return []
    libraries = {Path(root) / "steamapps"}
    vdf = Path(root) / "steamapps" / "libraryfolders.vdf"
    try:
        libraries |= {Path(p) / "steamapps" for p in _read_vdf_paths(vdf.read_text(encoding="utf-8", errors="replace"))}
    except OSError:
        pass
    games = []
    for library in libraries:
        for acf in library.glob("appmanifest_*.acf") if library.is_dir() else []:
            try:
                text = acf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            appid = re.search(r'"appid"\s+"(\d+)"', text); name = re.search(r'"name"\s+"([^"]+)"', text)
            if appid and name and not re.search(r"redistributable|steamworks|proton|runtime", name.group(1), re.I):
                games.append({"name": name.group(1), "source": "steam", "target": f"steam://rungameid/{appid.group(1)}"})
    return games


def epic_games(manifests: Path | None = None) -> list[dict]:
    manifests = manifests or Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    games = []
    for item in manifests.glob("*.item") if manifests.is_dir() else []:
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        name, ns, cid, app = data.get("DisplayName"), data.get("CatalogNamespace"), data.get("CatalogItemId"), data.get("AppName")
        if name and ns and cid and app:
            games.append({"name": name, "source": "epic", "target": f"com.epicgames.launcher://apps/{ns}%3A{cid}%3A{app}?action=launch&silent=true"})
    return games


def start_menu_apps(folders: list[Path] | None = None) -> list[dict]:
    if folders is None:
        folders = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
                   Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"]
    apps = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for link in folder.rglob("*"):
            if link.suffix.lower() in {".lnk", ".url"} and not SKIP_SHORTCUT.search(link.stem):
                apps.append({"name": link.stem, "source": "start menu", "target": str(link)})
    return apps


class AppIndex:
    """Cached index of launchable apps. Refreshes at most every `ttl` seconds."""

    def __init__(self, providers=None, ttl=300):
        self.providers = providers or [start_menu_apps, steam_games, epic_games, lambda: list(BUILTIN_APPS)]
        self.ttl, self._apps, self._at, self._lock = ttl, [], 0.0, threading.Lock()

    def apps(self) -> list[dict]:
        with self._lock:
            if not self._apps or time.monotonic() - self._at > self.ttl:
                seen, apps = set(), []
                for provider in self.providers:
                    try:
                        found = provider()
                    except Exception:
                        found = []
                    for app in found:
                        key = _norm(app["name"])
                        if key and key not in seen:  # Steam/Epic before duplicate shortcuts is fine either way
                            seen.add(key); apps.append(app)
                self._apps, self._at = apps, time.monotonic()
            return list(self._apps)

    def resolve(self, query: str, limit: int = 5) -> list[dict]:
        q = _norm(query)
        q = _norm(ALIASES.get(q, q))
        qr, qa = _romanize(q), _acronym(q).replace(" ", "")
        compact = qr.replace(" ", "")
        scored = []
        for app in self.apps():
            name = _norm(app["name"]); nr = _romanize(name)
            score = difflib.SequenceMatcher(None, qr, nr).ratio()
            if qr == nr:
                score = 2.0
            elif qr and (nr.startswith(qr + " ") or f" {qr} " in f" {nr} "):
                score = max(score, 1.3 if len(qr) > 3 else 1.0)
            if compact and compact == _acronym(name):
                score = max(score, 1.5)
            if compact and compact == nr.replace(" ", ""):
                score = max(score, 1.8)
            if app["source"] in {"steam", "epic"}:
                score += 0.05
            if score >= 0.6:
                scored.append((score, app))
        scored.sort(key=lambda pair: -pair[0])
        return [dict(app, score=round(score, 3)) for score, app in scored[:limit]]


def launch_app(app: dict, starter=None) -> dict:
    starter = starter or getattr(os, "startfile", None)
    if starter is None:
        raise RuntimeError("Launching apps is only supported on Windows.")
    starter(app["target"])
    return {"ok": True, "launched": app["name"], "source": app["source"]}


# ---------------------------------------------------------------- power / gaming mode

HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE_PERFORMANCE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
_PLAN = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s+\(([^)]+)\)(\s*\*)?", re.I)


def _powercfg(*args, runner=None) -> str:
    runner = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
    result = runner(["powercfg", *args])
    if getattr(result, "returncode", 0) != 0:
        raise RuntimeError((getattr(result, "stderr", "") or getattr(result, "stdout", "") or "powercfg failed").strip())
    return getattr(result, "stdout", "") or ""


def power_plans(runner=None) -> list[dict]:
    return [{"guid": g.lower(), "name": n.strip(), "active": bool(star)} for g, n, star in _PLAN.findall(_powercfg("/list", runner=runner))]


def pick_plan(plans: list[dict], mode: str) -> dict | None:
    by = lambda *needles: next((p for p in plans for n in needles if n in p["name"].lower()), None)
    if mode == "gaming":
        return by("ultimate") or by("high performance") or by("performance") or next((p for p in plans if p["guid"] == HIGH_PERFORMANCE), None)
    if mode == "saver":
        return by("power saver", "saver", "battery")
    return next((p for p in plans if p["guid"] == BALANCED), None) or by("balanced")


def set_game_mode(enabled: bool, winreg_module=None) -> bool:
    try:
        winreg = winreg_module or __import__("winreg")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar") as key:
            winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        return True
    except Exception:
        return False


class PowerController:
    def __init__(self, runner=None, winreg_module=None):
        self.runner, self.winreg_module, self.previous = runner, winreg_module, None

    def preview(self, mode: str) -> dict:
        plans = power_plans(self.runner)
        target = pick_plan(plans, mode)
        if mode == "gaming" and target is None:
            target = {"guid": HIGH_PERFORMANCE, "name": "High performance (will be added)", "active": False, "create": True}
        if mode == "normal" and self.previous:
            target = next((p for p in plans if p["guid"] == self.previous), target)
        if target is None:
            raise RuntimeError(f"No {mode} power plan exists on this PC.")
        current = next((p for p in plans if p["active"]), None)
        return {"mode": mode, "target": target, "current": current, "gameMode": mode == "gaming"}

    def apply(self, preview: dict) -> dict:
        target = preview["target"]
        current = preview.get("current")
        if target.get("create"):
            out = _powercfg("-duplicatescheme", HIGH_PERFORMANCE, runner=self.runner)
            match = _PLAN.search(out) or re.search(r"([0-9a-f-]{36})", out, re.I)
            target = {"guid": match.group(1).lower(), "name": "High performance"}
        if current and preview["mode"] == "gaming":
            self.previous = current["guid"]
        _powercfg("/setactive", target["guid"], runner=self.runner)
        game_mode = set_game_mode(preview["mode"] == "gaming" or preview["mode"] != "saver", self.winreg_module) if preview["mode"] == "gaming" else None
        return {"ok": True, "plan": target["name"], "gameMode": game_mode}


# ---------------------------------------------------------------- email

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def valid_email(address: str) -> bool:
    name, addr = parseaddr(address or "")
    return bool(addr and EMAIL_RE.fullmatch(addr))


def email_recipients(text: str) -> str:
    """Every address in the request, in order, once each ("to a@x.com, b@y.com and c@z.com")."""
    return ", ".join(dict.fromkeys(m.group(0) for m in EMAIL_RE.finditer(text or "")))


def gmail_compose_url(to: str, subject: str, body: str) -> str:
    """Gmail's own compose window, prefilled. The user reviews it and presses Send (or Schedule send) in Gmail."""
    from urllib.parse import quote, urlencode
    return "https://mail.google.com/mail/?" + urlencode({"view": "cm", "fs": "1", "to": to or "", "su": subject or "", "body": body or ""}, quote_via=quote)


def chrome_path() -> str | None:
    for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), os.environ.get("LOCALAPPDATA", "")):
        candidate = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if base and candidate.is_file():
            return str(candidate)
    return None


def open_in_browser(url: str) -> str:
    """Open a URL in Chrome when installed (the user's signed-in Gmail lives there), else the default browser."""
    if not str(url).startswith("https://"):
        raise ValueError("Only https links can be opened.")
    chrome = chrome_path()
    if chrome:
        subprocess.Popen([chrome, url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        return "Chrome"
    os.startfile(url)  # noqa: S606 - https URL only, checked above
    return "your browser"


def phone_digits(value: str) -> str:
    """'+91 98765-43210' -> '919876543210'. Empty unless it looks like a full phone number."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if 8 <= len(digits) <= 15 and not re.search(r"[A-Za-z]", str(value or "")) else ""


def whatsapp_url(phone: str, text: str) -> str:
    """WhatsApp's own send link: the chat opens with the message typed in; the user presses Send.
    Without a number WhatsApp asks which chat to send it to."""
    from urllib.parse import quote, urlencode
    query = {"phone": phone_digits(phone)} if phone_digits(phone) else {}
    query["text"] = text or ""
    return "whatsapp://send?" + urlencode(query, quote_via=quote)


def open_whatsapp(phone: str, text: str) -> str:
    """WhatsApp Desktop when installed (the whatsapp: link is registered), else WhatsApp Web in the browser."""
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp"))
        os.startfile(whatsapp_url(phone, text))  # noqa: S606 - fixed whatsapp: scheme built above
        return "WhatsApp"
    except OSError:
        from urllib.parse import quote, urlencode
        query = {"phone": phone_digits(phone)} if phone_digits(phone) else {}
        query["text"] = text or ""
        return "WhatsApp Web in " + open_in_browser("https://web.whatsapp.com/send?" + urlencode(query, quote_via=quote))


class Contacts:
    """Names the user has messaged before -> phone number, kept on this PC only."""

    def __init__(self, path: Path):
        self.path = Path(path); self.lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def lookup(self, name: str) -> str:
        return str(self._load().get(str(name or "").strip().casefold(), ""))

    def remember(self, name: str, phone: str):
        name = str(name or "").strip()
        if not name or not phone_digits(phone) or phone_digits(name):
            return
        with self.lock:
            data = self._load(); data[name.casefold()] = phone_digits(phone)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(data, indent=1), encoding="utf-8"); os.replace(tmp, self.path)


def build_message(sender: str, to: str, subject: str, body: str) -> EmailMessage:
    if not valid_email(sender):
        raise ValueError("Set your email address in Settings → Assistant first.")
    recipients = [a.strip() for a in re.split(r"[;,]", to or "") if a.strip()]
    if not recipients or not all(valid_email(a) for a in recipients):
        raise ValueError("The recipient email address is not valid.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, ", ".join(recipients), (subject or "").strip() or "(no subject)"
    msg["Date"], msg["Message-ID"] = formatdate(localtime=True), make_msgid()
    msg.set_content(body or "")
    return msg


def clean_app_password(value: str) -> str:
    """Gmail shows app passwords as 'abcd efgh ijkl mnop'; the spaces are not part of it."""
    return re.sub(r"\s+", "", str(value or ""))


def login_problem(exc: Exception, address: str) -> str:
    """A sign-in failure in words the user can act on, with the technical reason kept at the end."""
    text = str(exc)
    detail = f" ({type(exc).__name__}: {text[:160]})" if text else f" ({type(exc).__name__})"
    gmail = (address or "").lower().endswith(("@gmail.com", "@googlemail.com", "smtp.gmail.com"))
    if isinstance(exc, smtplib.SMTPAuthenticationError) or text.startswith(("(535", "(534")):
        if gmail:
            return ("Gmail did not accept that password. Gmail needs a 16-letter App Password, not your normal Gmail password: "
                    "Google Account > Security > 2-Step Verification > App passwords.")
        return "The mail server did not accept that email and password. Many providers need an app password."
    if isinstance(exc, ssl.SSLError):
        return "The secure connection to the mail server failed. Antivirus email scanning or a network filter may be interfering" + detail
    if isinstance(exc, smtplib.SMTPException) and not isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "The mail server refused the request" + detail
    if isinstance(exc, OSError):
        return "Could not reach the mail server. Check the internet connection, or whether a firewall or antivirus blocks email" + detail
    return "Sign-in failed" + detail


def _connect(host: str, port: int, timeout: int, smtp_factory=None):
    """Open an authenticated-ready SMTP session; if the port cannot be reached, try the other standard port (587 <-> 465)."""
    context = ssl.create_default_context()
    if smtp_factory is not None:
        smtp = smtp_factory()
        if port != 465:
            smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
        return smtp, port
    ports = [port] + [p for p in (587, 465) if p != port]
    last = None
    for candidate in ports:
        try:
            if candidate == 465:
                return smtplib.SMTP_SSL(host, candidate, context=context, timeout=timeout), candidate
            smtp = smtplib.SMTP(host, candidate, timeout=timeout)
            try:
                smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
            except Exception:
                smtp.close(); raise
            return smtp, candidate
        except (OSError, smtplib.SMTPException) as exc:
            if isinstance(exc, smtplib.SMTPAuthenticationError):
                raise
            last = exc
    raise last


def verify_login(cfg: dict, password: str, smtp_factory=None) -> int:
    """Sign in to the mail server and sign out again; nothing is sent. Returns the port that worked.
    Raises ValueError with a readable reason."""
    host, port = str(cfg.get("assistant_smtp_host", "")).strip(), int(cfg.get("assistant_smtp_port", 587) or 587)
    user = str(cfg.get("assistant_smtp_user", "") or cfg.get("assistant_email", "")).strip()
    if not host or not user or not password:
        raise ValueError("Enter your email address and app password.")
    try:
        smtp, used = _connect(host, port, 20, smtp_factory)
    except Exception as exc:
        raise ValueError(login_problem(exc, user).replace("the mail server.", f"the mail server {host}.", 1)) from exc
    try:
        with smtp:
            smtp.login(user, password)
        return used
    except smtplib.SMTPServerDisconnected as exc:
        # Reached the server, then it hung up on the password: that is a rejected sign-in, not a network fault.
        raise ValueError(login_problem(smtplib.SMTPAuthenticationError(535, str(exc)), host if host == "smtp.gmail.com" else user)) from exc
    except Exception as exc:
        problem = login_problem(exc, host if host == "smtp.gmail.com" else user)
        raise ValueError(problem.replace("the mail server.", f"the mail server {host}.", 1)) from exc


def fill_signature(body: str, name: str) -> str:
    """Models still write '[Your Name]': use the saved name, or drop the placeholder line."""
    pattern = r"\[(?:your\s+)?(?:full\s+)?name\]"
    if name:
        return re.sub(pattern, name, body or "", flags=re.I)
    return re.sub(r"\n?[ \t]*" + pattern + r"[ \t]*", "", body or "", flags=re.I).rstrip()


def send_email(cfg: dict, password: str, message: EmailMessage, smtp_factory=None) -> dict:
    host, port = str(cfg.get("assistant_smtp_host", "")).strip(), int(cfg.get("assistant_smtp_port", 587) or 587)
    user = str(cfg.get("assistant_smtp_user", "") or cfg.get("assistant_email", "")).strip()
    if not host or not user or not password:
        raise RuntimeError("Email is not set up. Add your mail server and app password in Settings → Assistant.")
    smtp, _ = _connect(host, port, 30, smtp_factory)
    with smtp:
        smtp.login(user, password)
        smtp.send_message(message)
    return {"ok": True, "to": message["To"], "subject": message["Subject"]}


SMTP_PRESETS = {"gmail.com": ("smtp.gmail.com", 587), "googlemail.com": ("smtp.gmail.com", 587),
                "outlook.com": ("smtp-mail.outlook.com", 587), "hotmail.com": ("smtp-mail.outlook.com", 587),
                "live.com": ("smtp-mail.outlook.com", 587), "yahoo.com": ("smtp.mail.yahoo.com", 465),
                "icloud.com": ("smtp.mail.me.com", 587), "zoho.com": ("smtp.zoho.com", 587)}


def smtp_preset(address: str):
    return SMTP_PRESETS.get((address or "").strip().rsplit("@", 1)[-1].lower())


# College and company addresses (e.g. @students.example.edu) are usually hosted by Google or Microsoft;
# the domain's MX records say which, so the user never has to know an SMTP host name.
MX_PROVIDERS = ((("google.com", "googlemail.com"), ("smtp.gmail.com", 587)),
                (("outlook.com", "office365.com"), ("smtp.office365.com", 587)),
                (("zoho.com", "zoho.in", "zoho.eu"), ("smtp.zoho.com", 587)),
                (("yahoodns.net",), ("smtp.mail.yahoo.com", 465)))


def mx_hosts(domain: str) -> list[str]:
    """Mail exchangers for a domain via Windows nslookup (no extra packages)."""
    import subprocess
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain or ""):
        return []
    try:
        out = subprocess.run(["nslookup", "-type=mx", domain], capture_output=True, text=True, timeout=8,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [h.strip().rstrip(".").lower() for h in re.findall(r"mail exchanger\s*=\s*(\S+)", out)]


SERVER_ALIASES = {"gmail": "gmail.com", "google": "gmail.com", "googlemail": "gmail.com", "gsuite": "gmail.com", "workspace": "gmail.com",
                  "outlook": "outlook.com", "hotmail": "outlook.com", "live": "outlook.com", "microsoft": "office365", "office365": "office365",
                  "office": "office365", "yahoo": "yahoo.com", "icloud": "icloud.com", "zoho": "zoho.com"}


def server_from_text(text: str):
    """What people type in a 'mail server' box ('gmail', 'gmail.com', 'smtp.gmail.com:465', 'https://…') → (host, port)."""
    raw = re.sub(r"^[a-z]+://", "", str(text or "").strip().lower()).strip("/ ")
    if not raw:
        return None
    host, _, port = raw.partition(":")
    key = re.sub(r"\.(com|net|in)$", "", host) if host.count(".") <= 1 else host
    alias = SERVER_ALIASES.get(key) or SERVER_ALIASES.get(host)
    if alias == "office365":
        return ("smtp.office365.com", 587)
    if alias or host in SMTP_PRESETS:
        return SMTP_PRESETS[alias or host]
    return (host, int(port) if port.isdigit() else 587)


def find_smtp(address: str, lookup=None):
    """Known provider by domain, else by the domain's MX records; None when unknown."""
    preset = smtp_preset(address)
    if preset:
        return preset
    domain = (address or "").strip().rsplit("@", 1)[-1].lower()
    for host in (lookup or mx_hosts)(domain):
        for suffixes, server in MX_PROVIDERS:
            if any(host == s or host.endswith("." + s) for s in suffixes):
                return server
    return None


class Outbox:
    """Scheduled emails persisted as JSON; `due()` returns messages whose time has come."""

    def __init__(self, path: Path):
        self.path, self.lock = Path(path), threading.Lock()

    def _load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save(self, items):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(items, indent=1), encoding="utf-8"); os.replace(tmp, self.path)

    def add(self, to, subject, body, send_at: float, via: str = "smtp") -> dict:
        item = {"id": uuid.uuid4().hex, "to": to, "subject": subject, "body": body, "sendAt": float(send_at), "status": "scheduled", "error": "", "via": via}
        with self.lock:
            items = self._load(); items.append(item); self._save(items)
        return item

    def list(self) -> list[dict]:
        with self.lock:
            return self._load()

    def cancel(self, item_id) -> bool:
        with self.lock:
            items = self._load(); hit = False
            for item in items:
                if item["id"] == item_id and item["status"] == "scheduled":
                    item["status"] = "cancelled"; hit = True
            self._save(items); return hit

    def due(self, now=None) -> list[dict]:
        now = time.time() if now is None else now
        with self.lock:
            items = self._load(); out = []
            for item in items:
                if item["status"] == "scheduled" and item["sendAt"] <= now:
                    item["status"] = "sending"; out.append(dict(item))
            if out:
                self._save(items)
            return out

    def mark(self, item_id, status, error=""):
        with self.lock:
            items = self._load()
            for item in items:
                if item["id"] == item_id:
                    item["status"], item["error"] = status, error
            self._save(items)


# ---------------------------------------------------------------- time parsing

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_when(text: str, now: _dt.datetime | None = None) -> _dt.datetime | None:
    """'in 10 minutes', 'at 5 pm', 'tomorrow at 9', 'tonight', 'on friday at 10:30am'. None = send now."""
    now = now or _dt.datetime.now()
    t = (text or "").lower()
    m = re.search(r"\bin\s+(\d+|an?|one|half an)\s*(minute|min|hour|hr|day)s?\b", t)
    if m:
        n = {"a": 1, "an": 1, "one": 1, "half an": 0.5}.get(m.group(1)) or float(m.group(1))
        unit = {"minute": 60, "min": 60, "hour": 3600, "hr": 3600, "day": 86400}[m.group(2)]
        return now + _dt.timedelta(seconds=n * unit)
    day = now.date(); explicit_day = False
    if "tomorrow" in t:
        day += _dt.timedelta(days=1); explicit_day = True
    else:
        for i, name in enumerate(_WEEKDAYS):
            if re.search(rf"\b(on\s+|next\s+)?{name}\b", t):
                delta = (i - now.weekday()) % 7 or 7
                day += _dt.timedelta(days=delta); explicit_day = True; break
    m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", t) or re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t)
    hour = minute = None
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm = (m.group(3) or "").replace(".", "")
        if ampm == "pm" and hour < 12: hour += 12
        if ampm == "am" and hour == 12: hour = 0
        if not ampm and hour < 8: hour += 12  # "at 5" means 5 pm in conversation
    elif "tonight" in t:
        hour, minute = 20, 0
    elif "this evening" in t:
        hour, minute = 18, 0
    elif "morning" in t and explicit_day:
        hour, minute = 9, 0
    if hour is None:
        return _dt.datetime.combine(day, _dt.time(9, 0)) if explicit_day else None
    when = _dt.datetime.combine(day, _dt.time(min(hour, 23), min(minute, 59)))
    if when <= now and not explicit_day:
        when += _dt.timedelta(days=1)
    return when


# ---------------------------------------------------------------- intent detection

_PLAY = re.compile(r"\b(?:i(?:'m| am)?\s+)?(?:feel(?:ing)?\s+like\s+playing|want\s+to\s+play|wanna\s+play|let'?s\s+play|play(?:ing)?|launch|open|start(?:\s+up)?|run|fire\s+up|boot\s+up)\s+(?:the\s+game\s+|the\s+app\s+|the\s+)?(?P<name>[a-z0-9][\w .:'&+\-]{0,60}?)(?=\s+(?:for\s+me|please|now|game|in\s+\w+\s+mode|with\b|and\b)|[.!?,]|$)", re.I)
_POWER = re.compile(r"\b(?P<mode>gaming|game|performance|high[- ]performance|ultimate|turbo|extreme|beast|balanced|normal|power[- ]?saver|battery[- ]?saver|saver|eco)\s+mode\b|\b(?:switch|set|turn|put)\b.*\b(?:power|performance)\s+(?:plan|mode)\b", re.I)
_REQUEST_PREFIX = r"^(?:(?:hey|ok|okay)\s+\w+[,!]?\s+)?(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+|i\s+(?:want|need|would\s+like)\s+(?:you\s+)?to\s+|help\s+me\s+|let'?s\s+|go\s+ahead\s+and\s+)?(?:please\s+)?"
_EMAIL = re.compile(_REQUEST_PREFIX + r"(?:(?:write|compose|draft|send|shoot|prepare)\b.*\b(?:e-?mail|mail)\b|(?:e-?mail|mail)\s+(?:to\s+)?\S+)", re.I)
_MUSIC = re.compile(_REQUEST_PREFIX + r"(?:play|put\s+on|start|open)\s+(?:some\s+|my\s+)?(?:music|songs?)(?:\s+(?:please|for\s+me|now))?[.!]?$|^(?:some\s+)?music(?:\s+please)?[.!]?$", re.I)
MUSIC_APPS = ["spotify", "apple music", "amazon music", "youtube music", "media player", "windows media player legacy", "vlc media player"]
_SCHEDULE = re.compile(r"\b(?:schedul(?:e|ed|ing)\b|send\s+(?:it|this|that|them|the\s+(?:e-?)?mail)\s+(?=at\b|on\b|tomorrow|tonight|in\s+(?:\d|an?\b|half)|next\b|this\s+(?:evening|afternoon|morning)|later\b))", re.I)
# Questions about how/what/why are conversation, not commands ("how do I write an email?").
_QUESTION = re.compile(r"^(?:how|what|why|when|where|who|which|is|are|was|were|does|do|did|should|explain|tell\s+me\s+(?:how|what|why|about))\b", re.I)
_NOT_APP = re.compile(r"^(?:a|an|the|some|with|music|song|video|it|this|that|again|game|games|over|around|chess with me|a game with me)$", re.I)


# Launch/mode verbs only: "write"/"get"/"set" are everyday chat and would add a model call to every turn.
_ACTION_VERB = re.compile(r"\b(?:open|launch|start|play|boot|fire\s+up|turn\s+(?:on|off)|switch\s+(?:to|on|off)|enable|activate|put\s+on)\b", re.I)


def action_candidate(text: str) -> bool:
    """Short imperative-looking requests the rules missed; worth one quick model check."""
    t = (text or "").strip()
    return bool(t) and len(t) <= 160 and not _QUESTION.match(t) and bool(_ACTION_VERB.search(t))


MODEL_INTENT_SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["open_app", "play_music", "gaming_mode", "normal_mode", "power_saver", "email", "none"]},
    "target": {"type": "string"}}, "required": ["action", "target"]}


def intent_from_model(choice: dict, text: str) -> dict | None:
    action = str((choice or {}).get("action") or "none"); target = str((choice or {}).get("target") or "").strip()[:80]
    if action == "open_app" and target:
        return {"kind": "launch", "query": target, "gaming": bool(re.search(r"\bplay|\bgame", text, re.I)), "request": text}
    if action == "play_music":
        return {"kind": "launch", "query": "music", "music": True, "gaming": False, "request": text}
    if action in {"gaming_mode", "normal_mode", "power_saver"}:
        return {"kind": "power", "mode": {"gaming_mode": "gaming", "normal_mode": "normal", "power_saver": "saver"}[action], "request": text}
    if action == "email":
        return {"kind": "email", "to": email_recipients(text), "topic": target, "sendAt": None, "request": text}
    return None


_WA = r"(?:whats\s?app|whatsapp|wa)"
_WA_SAY = r"(?:\s*[:,]\s*|\s+(?:saying|that\s+says|telling\s+(?:him|her|them)|to\s+say|and\s+say|and\s+tell\s+(?:him|her|them)|that)\s+)"
_WHATSAPP = [
    # "send a WhatsApp (message) to Mom saying I'll be late", "WhatsApp message to +91 98765 43210: on my way"
    re.compile(_REQUEST_PREFIX + r"(?:send|write|drop|shoot)?\s*(?:an?\s+)?" + _WA + r"\s+(?:message|msg|text)?\s*to\s+(?P<to>.+?)(?:" + _WA_SAY + r"(?P<text>.+))?[.!]?$", re.I),
    # "message Mom on WhatsApp saying …", "text John on WhatsApp that …", "send Mom a WhatsApp saying …"
    re.compile(_REQUEST_PREFIX + r"(?:send|message|text|ping|tell)\s+(?P<to>.+?)\s+(?:on|via|over|through|in)\s+" + _WA + _WA_SAY + r"?(?P<text>.+)$", re.I),
    re.compile(_REQUEST_PREFIX + r"send\s+(?P<to>.+?)\s+an?\s+" + _WA + r"(?:\s+(?:message|msg|text))?" + _WA_SAY + r"(?P<text>.+)$", re.I),
    # "WhatsApp Mom that I'll be late", "whatsapp Riya: see you at 6"
    re.compile(_REQUEST_PREFIX + _WA + r"\s+(?!message\b|msg\b|text\b|to\b)(?P<to>.+?)" + _WA_SAY + r"(?P<text>.+)$", re.I),
]


def detect_whatsapp(t: str) -> dict | None:
    for rx in _WHATSAPP:
        m = rx.match(t)
        if not m:
            continue
        to = re.sub(r"^(?:my\s+)", "", m.group("to").strip(" ,:'\"")).strip()
        body = (m.group("text") or "").strip().strip("\"'“”")
        if not to or (not body and rx is not _WHATSAPP[0]) or len(to) > 40 or len(to.split()) > 4 and not phone_digits(to):
            continue
        # A send time needs scheduling words ("…, send it at 5 pm", "schedule it for tomorrow 9 am");
        # times inside the message itself ("see you at 6") stay in the message.
        when = None
        sched = re.search(r"[,.\s]+(?:and\s+)?(?:send|schedule)\s+(?:it|this|that)\s+(?:for\s+)?(?P<when>.+)$", body, re.I)
        if sched:
            when = parse_when(sched.group("when"))
            if when:
                body = body[:sched.start()].strip()
        return {"kind": "whatsapp", "to": to, "text": body[:1000], "sendAt": when.timestamp() if when else None, "request": t}
    return None


def detect(text: str) -> dict | None:
    """Deterministic intent detection for direct user requests. Returns None for plain chat."""
    t = (text or "").strip()
    if not t or len(t) > 600 or _QUESTION.match(t):
        return None
    if re.search(r"\b" + _WA + r"\b", t, re.I):
        wa = detect_whatsapp(t)
        if wa:
            return wa
    if _EMAIL.search(t):
        # A send time comes only from explicit scheduling words; times inside the email's
        # content ("move tomorrow's meeting to 3 pm") are not a send time.
        sched = _SCHEDULE.search(t)
        when = parse_when(t[sched.start():]) if sched else None
        if not when:
            # "mail x@y.com 'Hello' at 6:50am": a clock time outside the quoted message is the send time.
            unquoted = re.sub(r"[\"“][^\"”]*[\"”]", " ", t)
            clock = re.search(r"\b(?:at|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b(?:\s+(?:today|tomorrow))?", unquoted, re.I)
            when = parse_when(clock.group(0)) if clock else None
        about = re.search(r"\b(?:about|regarding|saying|that says|telling (?:him|her|them))\s+(.+?)(?:\s+(?:at|on|tomorrow|tonight|in\s+\d)\b|[.?!]?$)", t, re.I)
        topic = re.sub(r"\s+and\s+(?:send|schedule|mail|email|deliver)\b.*$", "", about.group(1), flags=re.I) if about else ""
        return {"kind": "email", "to": email_recipients(t), "topic": topic, "sendAt": when.timestamp() if when else None, "request": t}
    if _MUSIC.search(t):
        return {"kind": "launch", "query": "music", "music": True, "gaming": False, "request": t}
    power = _POWER.search(t)
    play = _PLAY.search(t)
    if play:
        name = play.group("name").strip(" .'")
        # "open GTA 5 from Epic Games" — the store/launcher is where it lives, not part of the name.
        name = re.sub(r"\s+(?:from|on|in|via|using|through|with)\s+(?:the\s+)?(?:epic(?:\s+games)?|steam|rockstar(?:\s+games)?|xbox|ubisoft|ea|battle\.?net|gog|my\s+(?:pc|computer|laptop)|this\s+(?:pc|computer|laptop)|the\s+launcher|launcher)\b.*$", "", name, flags=re.I)
        name = re.sub(r"\s+(?:game|app|application)$", "", name, flags=re.I)
        if name and not _NOT_APP.match(name) and not re.match(r"^(?:mode|gaming mode|performance mode)$", name, re.I):
            gaming = bool(power and power.group("mode") and power.group("mode").lower() not in {"balanced", "normal", "saver", "power saver", "power-saver", "battery saver", "eco"}) or bool(re.search(r"\bplay(?:ing)?\b|feel(?:ing)? like playing|\bgame\b", t, re.I))
            return {"kind": "launch", "query": name, "gaming": gaming, "request": t}
    if power:
        word = (power.group("mode") or "").lower()
        mode = "saver" if re.search(r"saver|eco|battery", word) else "normal" if word in {"balanced", "normal"} else "gaming"
        return {"kind": "power", "mode": mode, "request": t}
    return None
