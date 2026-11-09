"""Assistant action host: plan → preview card → user confirms → execute.

The model is the brain only for writing email drafts. Which app to launch, which power
plan to use and where mail goes are resolved deterministically from what exists on this
PC and what the user typed or said, so the model cannot invent paths or recipients.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

import assistant_actions as aa

CONFIRM_WORDS = {"yes", "yeah", "yep", "sure", "ok", "okay", "do it", "go ahead", "yes please", "please do", "confirm",
                 "send it", "launch it", "go", "yes do it", "sounds good", "perfect"}
CANCEL_WORDS = {"no", "nope", "cancel", "stop", "don't", "do not", "never mind", "nevermind", "no thanks", "forget it"}


def spoken_answer(text: str):
    t = re.sub(r"[.!?,]+", "", (text or "").strip().lower())
    if t in CONFIRM_WORDS or re.match(r"^(yes|yeah|yep|sure|ok|okay)\b", t):
        return "confirm"
    if t in CANCEL_WORDS or re.match(r"^(no|nope|cancel|don'?t)\b", t):
        return "cancel"
    return None


class AssistantHost:
    def __init__(self, data_dir, cfg_getter, emit, engine_getter=None, secret_store=None, app_index=None, power=None,
                 sender=aa.send_email, launcher=aa.launch_app, draft_fn=None, classify_fn=None, browser=aa.open_in_browser, messenger=aa.open_whatsapp):
        self.data_dir = Path(data_dir)
        self.cfg_getter, self.emit, self.engine_getter = cfg_getter, emit, engine_getter
        self.secret = secret_store
        self.index = app_index or aa.AppIndex()
        self.power = power or aa.PowerController()
        self.outbox = aa.Outbox(self.data_dir / "assistant_outbox.json")
        self.sender, self.launcher, self.draft_fn, self.classify_fn = sender, launcher, draft_fn, classify_fn
        self.browser, self.messenger = browser, messenger
        self.contacts = aa.Contacts(self.data_dir / "assistant_contacts.json")
        self.cards: dict[str, dict] = {}
        self.lock = threading.RLock()
        # Warm the app index in the background so the first "play X" is instant.
        threading.Thread(target=self._warm, name="assistant-app-index", daemon=True).start()

    def _warm(self):
        try:
            self.index.apps()
        except Exception:
            pass

    # ------------------------------------------------------------- config / secrets
    def cfg(self) -> dict:
        try:
            return dict(self.cfg_getter() or {})
        except Exception:
            return {}

    def enabled(self) -> bool:
        return bool(self.cfg().get("assistant_actions_enabled", True))

    def mail_password(self) -> str:
        try:
            return self.secret.read() if self.secret else ""
        except Exception:
            return ""

    def settings(self) -> dict:
        cfg = self.cfg()
        return {"enabled": self.enabled(), "autoLowRisk": bool(cfg.get("assistant_auto_low_risk", True)), "email": cfg.get("assistant_email", ""), "name": cfg.get("assistant_sender_name", ""),
                "smtpHost": cfg.get("assistant_smtp_host", ""), "smtpPort": int(cfg.get("assistant_smtp_port", 587) or 587),
                "smtpUser": cfg.get("assistant_smtp_user", ""), "passwordStored": bool(self.secret and self.secret.path.exists()),
                "outbox": [i for i in self.outbox.list() if i["status"] in {"scheduled", "sending", "failed"}][-20:]}

    # ------------------------------------------------------------- planning
    def plan(self, text: str, source: str = "chat") -> dict | None:
        if not self.enabled():
            return None
        intent = aa.detect(text)
        if not intent and aa.action_candidate(text):
            try:
                intent = aa.intent_from_model((self.classify_fn or self._model_classify)(text), text)
            except Exception:
                intent = None
        if not intent:
            return None
        card = {"id": uuid.uuid4().hex, "kind": intent["kind"], "request": text, "source": source, "status": "awaiting", "error": ""}
        try:
            if intent["kind"] == "launch":
                if intent.get("music"):
                    matches = next((m for q in aa.MUSIC_APPS for m in [self.index.resolve(q, limit=1)] if m and m[0]["score"] >= 1.0), [])
                else:
                    matches = self.index.resolve(intent["query"])
                if not matches:
                    # Nothing installed matches: treat it as conversation rather than guess
                    # ("start a story…", or a game that isn't installed).
                    return None
                else:
                    app = matches[0]
                    card.update(app=app, alternatives=matches[1:4], gaming=bool(intent.get("gaming")))
                    if card["gaming"]:
                        try:
                            card["power"] = self.power.preview("gaming")
                        except Exception as exc:
                            card["power"], card["powerError"] = None, str(exc)[:200]
                    plan_name = (card.get("power") or {}).get("target", {}).get("name")
                    extra = f" and switch to {plan_name} with Game Mode on" if plan_name else ""
                    card["summary"] = f"Launch {app['name']}{extra}."
                    card["spoken"] = f"Launch {app['name']}{extra}? Say yes to go, or no to cancel."
            elif intent["kind"] == "power":
                preview = self.power.preview(intent["mode"])
                card.update(power=preview)
                label = {"gaming": "gaming mode", "saver": "power saver", "normal": "normal mode"}[intent["mode"]]
                card["summary"] = f"Switch to {label}: {preview['target']['name']} power plan" + (" with Game Mode on." if intent["mode"] == "gaming" else ".")
                card["spoken"] = f"Switch to {label}, using the {preview['target']['name']} plan? Say yes or no."
            elif intent["kind"] == "whatsapp":
                phone = aa.phone_digits(intent["to"]) or self.contacts.lookup(intent["to"])
                card.update(to=intent["to"], phone=phone, text=intent["text"], sendAt=intent["sendAt"])
                who = intent["to"] if not aa.phone_digits(intent["to"]) else "+" + phone
                card["summary"] = f"WhatsApp to {who}" + (f": “{intent['text'][:80]}”" if intent["text"] else ". Type the message below.")
                card["spoken"] = (f"Message {who} on WhatsApp: {intent['text'][:160]}. Say yes to open it in WhatsApp, or no to cancel."
                                  if intent["text"] else f"What should the WhatsApp message to {who} say? Type it on screen.")
            elif intent["kind"] == "email":
                cfg = self.cfg()
                card.update(status="drafting", to=intent["to"], subject="", body="", sendAt=intent["sendAt"], topic=intent["topic"],
                            sender=cfg.get("assistant_email", ""), configured=bool(cfg.get("assistant_smtp_host") and self.mail_password()))
                card["summary"] = "Writing your email…"
                card["spoken"] = "Okay, I'm writing that email."
        except Exception as exc:
            card.update(status="error", error=str(exc)[:300], summary="That action isn't available right now.", spoken="Sorry, I couldn't prepare that.")
        with self.lock:
            self.cards[card["id"]] = card
            snapshot = dict(card)
        if snapshot["status"] == "drafting":  # registered before the draft thread can look it up
            threading.Thread(target=self._draft, args=(card["id"],), name="assistant-email-draft", daemon=True).start()
        return snapshot

    def _draft(self, card_id: str):
        auto = False
        card = self.cards.get(card_id)
        if not card:
            return
        cfg = self.cfg()
        name = cfg.get("assistant_sender_name", "") or ""
        try:
            draft = (self.draft_fn or self._model_draft)(card["request"], name)
        except Exception as exc:
            draft = {"subject": (card.get("topic") or "Hello").strip().capitalize()[:120], "body": "", "error": str(exc)[:200]}
        with self.lock:
            if card.get("status") != "drafting":
                return
            card.update(subject=draft.get("subject", ""), body=aa.fill_signature(draft.get("body", ""), name), status="awaiting")
            recipients = [a.strip() for a in str(card["to"] or "").split(",") if a.strip()]
            missing = "" if recipients and all(aa.valid_email(a) for a in recipients) else " Add the recipient's email address."
            who = recipients[0].split("@")[0] if len(recipients) == 1 else f"{len(recipients)} people"
            when = time.strftime("%a %d %b, %I:%M %p", time.localtime(card["sendAt"])) if card.get("sendAt") else ""
            card["summary"] = (f"Email to {card['to'] or 'recipient'}" + (f", scheduled for {when}" if when else "") + "." + missing)
            card["spoken"] = ("I've drafted the email" + (f" to {who}" if recipients else "") +
                              (f", to send {when}" if when else "") + ". Check it on screen and say send it, or tap Send." if not missing
                              else "I've drafted the email. Please type the recipient's address on screen.")
            cfg = self.cfg()
            auto = (not missing and when and float(card["sendAt"]) > time.time() + 30 and cfg.get("assistant_auto_schedule_email", True)
                    and cfg.get("assistant_smtp_host") and self.mail_password())
        self.emit({"type": "assistantAction", "card": dict(card)})
        if auto:
            # The owner gave a time and a connected account: queue it now; it stays cancellable until then.
            self.execute(card_id)

    def _model_classify(self, text: str) -> dict:
        """One short, schema-constrained call to the already loaded model; never loads a model."""
        engine = self.engine_getter() if self.engine_getter else None
        runtime = getattr(engine, "runtime", None)
        if engine is None or not getattr(runtime, "ready", False):
            return {"action": "none", "target": ""}
        system = ("Classify the user's message for a desktop assistant. action: open_app (open/launch/play an installed app or game; "
                  "target = its name), play_music, gaming_mode, normal_mode, power_saver, email (target = topic), or none for anything "
                  "else (questions, writing tasks, conversation). Reply with JSON only.")
        result = engine.chat_completion([{"role": "system", "content": system}, {"role": "user", "content": text}],
                                        max_tokens=40, temperature=0, allowed_tools=[], response_schema=aa.MODEL_INTENT_SCHEMA)
        try:
            from model_runtime import engine_visible_text
            raw = engine_visible_text(engine, result)
        except Exception:
            raw = result if isinstance(result, str) else str(result)
        match = re.search(r"\{.*\}", raw or "", re.S)
        return json.loads(match.group(0)) if match else {"action": "none", "target": ""}

    def _model_draft(self, request: str, name: str) -> dict:
        engine = self.engine_getter() if self.engine_getter else None
        if engine is None:
            raise RuntimeError("The local model is not available.")
        system = ("You write emails on behalf of the user. Reply with JSON only: "
                  '{"subject": "...", "body": "..."}. Write a complete, natural, well-structured email that does exactly what '
                  "the user asked, in their voice. No placeholders such as [Name] or [Date]; if a detail is unknown, write around it. "
                  "Do not include a To or Subject line in the body. "
                  + (f"Sign off as {name}." if name else "End with a short sign-off without a name."))
        messages = [{"role": "system", "content": system}, {"role": "user", "content": request}]
        schema = {"type": "object", "properties": {"subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["subject", "body"]}
        try:
            result = engine.chat_completion(messages, max_tokens=700, temperature=0.4, allowed_tools=[], response_schema=schema)
        except TypeError:
            result = engine.chat_completion(messages, max_tokens=700, temperature=0.4, allowed_tools=[])
        try:
            from model_runtime import engine_visible_text
            text = engine_visible_text(engine, result)
        except Exception:
            text = result if isinstance(result, str) else str(result)
        text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
        match = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(match.group(0)) if match else {}
        except ValueError:
            data = {}
        subject = str(data.get("subject") or "").strip()
        body = str(data.get("body") or "").strip() or text.strip()
        return {"subject": subject[:200], "body": body[:20000]}

    # ------------------------------------------------------------- execution
    def card(self, card_id):
        with self.lock:
            card = self.cards.get(card_id)
            return dict(card) if card else None

    def pending_voice_card(self):
        with self.lock:
            live = [c for c in self.cards.values() if c.get("source") == "voice" and c.get("status") in {"awaiting", "drafting"}]
            return dict(live[-1]) if live else None

    def cancel(self, card_id) -> dict:
        with self.lock:
            card = self.cards.get(card_id)
            if not card:
                return {"ok": False, "error": "This action expired."}
            if card["status"] in {"awaiting", "drafting", "not_found", "error"}:
                card.update(status="cancelled", summary="Cancelled.")
            out = dict(card)
        self.emit({"type": "assistantAction", "card": out})
        return {"ok": True, "card": out}

    def execute(self, card_id, overrides=None) -> dict:
        overrides = overrides or {}
        with self.lock:
            card = self.cards.get(card_id)
            if not card:
                return {"ok": False, "error": "This action expired. Ask again."}
            if card["status"] != "awaiting":
                return {"ok": False, "error": "This action is not waiting for confirmation.", "card": dict(card)}
            card["status"] = "running"
        try:
            if card["kind"] == "launch":
                app = card["app"]
                if overrides.get("appIndex") is not None:
                    choices = [card["app"], *card.get("alternatives", [])]
                    app = choices[int(overrides["appIndex"])]
                notes = []
                if card.get("power") and overrides.get("power", True):
                    result = self.power.apply(card["power"]); notes.append(f"{result['plan']} power plan on")
                self.launcher(app)
                card.update(status="done", app=app, summary=f"Launching {app['name']}" + (f" · {', '.join(notes)}" if notes else "") + ".",
                            spoken=f"Launching {app['name']}. Have fun!" if card.get("gaming") else f"Opening {app['name']}.")
            elif card["kind"] == "power":
                result = self.power.apply(card["power"])
                card.update(status="done", summary=f"{result['plan']} power plan is on" + (" · Game Mode on." if result.get("gameMode") else "."),
                            spoken=f"Done. {result['plan']} is on.")
            elif card["kind"] == "whatsapp":
                for key in ("to", "phone", "text"):
                    if key in overrides:
                        card[key] = str(overrides[key]).strip()
                if "sendAt" in overrides:
                    card["sendAt"] = overrides["sendAt"]
                if not str(card.get("text") or "").strip():
                    raise ValueError("Write the message first.")
                if card.get("phone") and not aa.phone_digits(card["phone"]):
                    raise ValueError("The phone number needs the country code, like +91 98765 43210.")
                self.contacts.remember(card.get("to", ""), card.get("phone", ""))
                who = card.get("to") or ("+" + aa.phone_digits(card.get("phone", "")))
                if card.get("sendAt") and float(card["sendAt"]) > time.time() + 30:
                    item = self.outbox.add(card.get("phone", ""), who, card["text"], float(card["sendAt"]), via="whatsapp")
                    when = time.strftime("%a %d %b, %I:%M %p", time.localtime(item["sendAt"]))
                    card.update(status="scheduled", outboxId=item["id"],
                                summary=f"At {when} Offline Studio opens WhatsApp with this message to {who} for you to send (keep the app running).",
                                spoken=f"Okay. At {when} I'll open it in WhatsApp for you to send.")
                else:
                    where = self.messenger(card.get("phone", ""), card["text"])
                    pick = "" if card.get("phone") else " Pick the chat,"
                    card.update(status="done", summary=f"Opened in {where} with your message to {who}.{pick} press Send.".replace(". press", ". Press"),
                                spoken=f"It's ready in WhatsApp.{pick} press send.".replace(". press", ". Press"))
            elif card["kind"] == "email":
                for key in ("to", "subject", "body"):
                    if key in overrides:
                        card[key] = str(overrides[key])
                if "sendAt" in overrides:
                    card["sendAt"] = overrides["sendAt"]
                cfg = self.cfg()
                via = overrides.get("via") or ("smtp" if cfg.get("assistant_smtp_host") and self.mail_password() else "gmail")
                later = bool(card.get("sendAt") and float(card["sendAt"]) > time.time() + 30)
                if via == "gmail":
                    # No mail password needed: Gmail opens in Chrome with the draft; the user presses Send there.
                    if card["to"] and not all(aa.valid_email(a.strip()) for a in str(card["to"]).split(",") if a.strip()):
                        raise ValueError("The recipient email address is not valid.")
                    if not str(card["body"]).strip():
                        raise ValueError("Write the message first.")
                    if later:
                        item = self.outbox.add(card["to"], card["subject"], card["body"], float(card["sendAt"]), via="gmail")
                        when = time.strftime("%a %d %b, %I:%M %p", time.localtime(item["sendAt"]))
                        card.update(status="scheduled", outboxId=item["id"], via="gmail",
                                    summary=f"At {when} Offline Studio opens this draft in Gmail for you to send (keep the app running).",
                                    spoken=f"Okay. At {when} I'll open it in Gmail for you to send.")
                    else:
                        where = self.browser(aa.gmail_compose_url(card["to"], card["subject"], card["body"]))
                        card.update(status="done", via="gmail", summary=f"Opened in Gmail in {where}. Check it and press Send.",
                                    spoken=f"It's open in Gmail. Check it and press send.")
                    out = dict(card)
                    self.emit({"type": "assistantAction", "card": out})
                    return {"ok": True, "card": out, "error": ""}
                message = aa.build_message(cfg.get("assistant_email", ""), card["to"], card["subject"], card["body"])
                if later:
                    item = self.outbox.add(card["to"], card["subject"], card["body"], float(card["sendAt"]))
                    when = time.strftime("%a %d %b, %I:%M %p", time.localtime(item["sendAt"]))
                    card.update(status="scheduled", outboxId=item["id"], summary=f"Scheduled for {when}. Offline Studio sends it then (keep the app running).",
                                spoken=f"Scheduled for {when}.")
                else:
                    self.sender(cfg, self.mail_password(), message)
                    card.update(status="done", summary=f"Sent to {message['To']}.", spoken="Sent.")
            else:
                raise RuntimeError("Unknown action.")
        except Exception as exc:
            card.update(status="awaiting" if card["kind"] in {"email", "whatsapp"} else "error", error=str(exc)[:300],
                        summary=str(exc)[:300], spoken="That didn't work. " + str(exc)[:160])
        out = dict(card)
        self.emit({"type": "assistantAction", "card": out})
        return {"ok": out["status"] in {"done", "scheduled"}, "card": out, "error": out.get("error", "")}

    # ------------------------------------------------------------- scheduled mail
    def poll_outbox(self):
        for item in self.outbox.due():
            if item.get("via") == "whatsapp":
                # Outbox fields: to = phone (may be empty), subject = who, body = message.
                try:
                    self.messenger(item["to"], item["body"])
                    self.outbox.mark(item["id"], "sent")
                    self.emit({"type": "assistantNotice", "message": f"Your scheduled WhatsApp message to {item['subject'] or 'your contact'} is open in WhatsApp. Press Send."})
                except Exception as exc:
                    self.outbox.mark(item["id"], "failed", str(exc)[:300])
                    self.emit({"type": "assistantNotice", "message": f"Could not open the scheduled WhatsApp message: {str(exc)[:200]}", "error": True})
                continue
            if item.get("via") == "gmail":
                try:
                    self.browser(aa.gmail_compose_url(item["to"], item["subject"], item["body"]))
                    self.outbox.mark(item["id"], "sent")
                    self.emit({"type": "assistantNotice", "message": f"Your scheduled email to {item['to'] or 'your recipient'} is open in Gmail. Press Send."})
                except Exception as exc:
                    self.outbox.mark(item["id"], "failed", str(exc)[:300])
                    self.emit({"type": "assistantNotice", "message": f"Could not open the scheduled Gmail draft: {str(exc)[:200]}", "error": True})
                continue
            try:
                cfg = self.cfg()
                self.sender(cfg, self.mail_password(), aa.build_message(cfg.get("assistant_email", ""), item["to"], item["subject"], item["body"]))
                self.outbox.mark(item["id"], "sent")
                self.emit({"type": "assistantNotice", "message": f"Scheduled email sent to {item['to']}."})
            except Exception as exc:
                self.outbox.mark(item["id"], "failed", str(exc)[:300])
                self.emit({"type": "assistantNotice", "message": f"Scheduled email to {item['to']} failed: {str(exc)[:200]}", "error": True})
