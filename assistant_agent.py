"""Assistant workspace runner ("Jarvis"): command → plan → steps → results.

Routes, fastest first:
  1. pc_control.quick_command — instant rules for common commands (volume, media, timers...)
  2. assistant_actions.detect — apps/games, music, power/gaming mode, email
  3. the loaded local model plans multi-step requests into allowlisted tool steps (JSON schema)
Each step runs under its risk tier: "low" runs immediately when auto-run is on; "confirm" waits
for the user's Allow. Emits {"type": "assistantRun", "run": {...}} events after every change.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid

import assistant_actions as aa
import pc_control as pc

ASSISTANT_TOOLS = {"power_mode": "confirm", "email": "confirm"}


class AssistantAgent:
    def __init__(self, host, control: pc.PCControl, emit, cfg_getter, engine_getter=None, planner=None):
        self.host, self.control, self.emit, self.cfg_getter = host, control, emit, cfg_getter
        self.engine_getter, self.planner = engine_getter, planner
        self.runs: dict[str, dict] = {}
        self.decisions: dict[tuple, threading.Event] = {}
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ helpers
    def risk(self, tool: str) -> str:
        if tool in ASSISTANT_TOOLS:
            return ASSISTANT_TOOLS[tool]
        t = self.control.tools.get(tool)
        return t.risk if t else "confirm"

    def auto_low(self) -> bool:
        try:
            return bool((self.cfg_getter() or {}).get("assistant_auto_low_risk", True))
        except Exception:
            return True

    def _publish(self, run):
        with self.lock:
            snapshot = json.loads(json.dumps(run))
        self.emit({"type": "assistantRun", "run": snapshot})

    def catalog(self) -> list[dict]:
        tools = [{"name": t.name, "risk": t.risk, "summary": t.summary, "params": t.params} for t in self.control.tools.values()]
        tools += [{"name": "power_mode", "risk": "confirm", "summary": "Switch power plan", "params": {"mode": "gaming | normal | saver"}},
                  {"name": "email", "risk": "confirm", "summary": "Write an email (opens a draft to review)", "params": {"request": "what to write and to whom"}}]
        return tools

    # ------------------------------------------------------------------ planning
    def plan(self, text: str) -> tuple[list[dict], str, str]:
        """Returns (steps, reply, route)."""
        # Compound commands ("open spotify and set volume to 30, then lock my pc"): when every
        # part is understood by the rules, run them all; otherwise let the model plan the whole.
        parts = [p for p in re.split(r"\s*(?:,\s*(?:and\s+|then\s+)?|\band\s+then\b|\bthen\b|\band\b|;)\s*", text.strip()) if p]
        if len(parts) > 1:
            combined = []
            for part in parts:
                sub = self._rule_steps(part)
                if not sub:
                    combined = None; break
                combined += sub
            if combined:
                return combined[:6], "", "rules"
            return self._planned(text)
        steps = self._rule_steps(text)
        if steps:
            return steps, "", "rules"
        return self._planned(text)

    def _planned(self, text):
        planned = (self.planner or self._model_plan)(text)
        steps = [s for s in (planned.get("steps") or []) if isinstance(s, dict) and (s.get("tool") in self.control.tools or s.get("tool") in ASSISTANT_TOOLS)][:6]
        return steps, str(planned.get("reply") or "").strip()[:400], "model"

    def _rule_steps(self, text: str) -> list[dict] | None:
        steps = pc.quick_command(text)
        if steps:
            return steps
        intent = aa.detect(text)
        if not intent:
            return None
        if intent["kind"] == "launch":
            # Only claim a launch when the app is actually installed; otherwise the model decides
            # (it may be conversation, e.g. "play me something on the radio about timers").
            if not intent.get("music") and not self.host.index.resolve(intent["query"], limit=1):
                return None
            steps = [{"tool": "power_mode", "args": {"mode": "gaming"}}] if intent.get("gaming") else []
            steps.append({"tool": "open_app", "args": {"name": "music" if intent.get("music") else intent["query"]}})
            return steps
        if intent["kind"] == "power":
            return [{"tool": "power_mode", "args": {"mode": intent["mode"]}}]
        if intent["kind"] == "email":
            return [{"tool": "email", "args": {"request": text}}]
        return None

    def _model_plan(self, text: str) -> dict:
        engine = self.engine_getter() if self.engine_getter else None
        if engine is None:
            return {"steps": [], "reply": "The local model isn't available right now."}
        lines = [f"- {t['name']}({', '.join(f'{k}: {v}' for k, v in t['params'].items())}) — {t['summary']}" for t in self.catalog()]
        system = ("You are the action planner of a local Windows desktop assistant. Turn the user's request into at most 6 tool steps "
                  "using ONLY these tools:\n" + "\n".join(lines) +
                  "\nArgument values are strings. Whenever a tool can answer or do it, use the tool (e.g. battery or charging questions → system_status). "
                  "If the request needs no PC action at all (general knowledge or chat), return no steps and answer in 'reply'. "
                  "'reply' is one or two short sentences for the user, spoken aloud; never claim a step already succeeded. Reply with JSON only.")
        names = [t["name"] for t in self.catalog()]
        schema = {"type": "object", "properties": {
            "steps": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
                "tool": {"type": "string", "enum": names}, "args": {"type": "object", "additionalProperties": {"type": "string"}}},
                "required": ["tool", "args"]}},
            "reply": {"type": "string"}}, "required": ["steps", "reply"]}
        result = engine.chat_completion([{"role": "system", "content": system}, {"role": "user", "content": text}],
                                        max_tokens=300, temperature=0, allowed_tools=[], response_schema=schema)
        try:
            from model_runtime import engine_visible_text
            raw = engine_visible_text(engine, result)
        except Exception:
            raw = result if isinstance(result, str) else str(result)
        match = re.search(r"\{.*\}", re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S), re.S)
        try:
            return json.loads(match.group(0)) if match else {"steps": [], "reply": (raw or "").strip()[:400]}
        except ValueError:
            return {"steps": [], "reply": ""}

    # ------------------------------------------------------------------ running
    def start(self, text: str, source: str = "assistant", planned=None) -> dict:
        """planned: optional (steps, reply, route) already computed by the caller."""
        run = {"id": uuid.uuid4().hex, "request": text.strip(), "source": source, "status": "planning", "steps": [], "reply": "",
               "route": "", "startedAt": time.time(), "error": ""}
        with self.lock:
            self.runs[run["id"]] = run
        self._publish(run)
        threading.Thread(target=self._run, args=(run, planned), name="assistant-run", daemon=True).start()
        return run

    def plan_in_background(self, text: str, on_done):
        """Plan without creating a run; on_done(steps, reply, route) is called from a worker thread."""
        def work():
            try:
                result = self.plan(text)
            except Exception:
                result = ([], "", "error")
            on_done(*result)
        threading.Thread(target=work, name="assistant-plan", daemon=True).start()

    def _run(self, run, planned=None):
        try:
            t0 = time.perf_counter()
            steps, reply, route = planned if planned is not None else self.plan(run["request"])
            run.update(route=route, planMs=round((time.perf_counter() - t0) * 1000), reply=reply,
                       steps=[{"tool": s["tool"], "args": dict(s.get("args") or {}), "risk": self.risk(s["tool"]), "status": "pending", "message": ""} for s in steps])
            if not run["steps"]:
                run["status"] = "done"
                run["reply"] = run["reply"] or "I didn't find a PC action in that. Try “open Spotify”, “volume 30” or “find my resume”."
                self._publish(run); return
            run["status"] = "running"; self._publish(run)
            for index, step in enumerate(run["steps"]):
                if run["status"] == "cancelled":
                    break
                if step["risk"] != "low" or not self.auto_low():
                    step["status"] = "awaiting"; run["status"] = "awaiting"; self._publish(run)
                    event = threading.Event()
                    with self.lock:
                        self.decisions[(run["id"], index)] = event
                    event.wait(timeout=300)
                    with self.lock:
                        self.decisions.pop((run["id"], index), None)
                    if step.get("decision") != "allow":
                        step["status"] = "skipped"; step["message"] = "Skipped."; run["status"] = "running"; self._publish(run); continue
                    run["status"] = "running"
                step["status"] = "running"; self._publish(run)
                started = time.perf_counter()
                try:
                    result = self._execute(step)
                    step.update(status="done", message=result.get("message", "Done."), ms=round((time.perf_counter() - started) * 1000))
                    if result.get("files"): step["files"] = result["files"]
                    if result.get("card"): step["card"] = result["card"]
                except Exception as exc:
                    step.update(status="error", message=str(exc)[:300])
                self._publish(run)
            if run["status"] != "cancelled":
                run["status"] = "done"
                if not run["reply"]:
                    done = [s["message"] for s in run["steps"] if s["status"] == "done" and s["message"]]
                    failed = [s["message"] for s in run["steps"] if s["status"] == "error"]
                    run["reply"] = " ".join(done[-2:] + failed[:1]) or "Done."
        except Exception as exc:
            run.update(status="error", error=str(exc)[:300], reply="Sorry, that didn't work.")
        run["totalMs"] = round((time.time() - run["startedAt"]) * 1000)
        self._publish(run)

    def _execute(self, step) -> dict:
        tool, args = step["tool"], step["args"]
        if tool == "power_mode":
            preview = self.host.power.preview(str(args.get("mode", "gaming")))
            result = self.host.power.apply(preview)
            return {"message": f"{result['plan']} power plan on" + (" · Game Mode on." if result.get("gameMode") else ".")}
        if tool == "open_app" and str(args.get("name", "")).lower() == "music":
            match = next((m for q in aa.MUSIC_APPS for m in [self.host.index.resolve(q, limit=1)] if m and m[0]["score"] >= 1.0), [])
            if not match:
                raise RuntimeError("No music app found on this PC.")
            self.host.launcher(match[0]); return {"message": f"Opening {match[0]['name']}."}
        if tool == "email":
            card = self.host.plan(str(args.get("request") or step.get("request") or ""), "assistant")
            if not card or card.get("kind") != "email":
                card = self.host.plan("write an email " + str(args.get("request", "")), "assistant")
            if not card:
                raise RuntimeError("I couldn't start that email.")
            self.emit({"type": "assistantAction", "card": card})
            return {"message": "Draft opened for review — check it and press Send.", "card": card["id"]}
        return self.control.run(tool, args)

    def voice_waiting(self):
        """(run_id, step_index) of the newest voice run waiting for a spoken yes/no, else None."""
        with self.lock:
            for run in reversed(list(self.runs.values())):
                if run.get("source") == "voice" and run.get("status") == "awaiting":
                    for i, step in enumerate(run["steps"]):
                        if step["status"] == "awaiting":
                            return run["id"], i
        return None

    def decide(self, run_id: str, index: int, allow: bool) -> dict:
        with self.lock:
            run = self.runs.get(run_id)
            event = self.decisions.get((run_id, int(index)))
            if not run or event is None:
                return {"ok": False, "error": "That step is no longer waiting."}
            run["steps"][int(index)]["decision"] = "allow" if allow else "skip"
        event.set()
        return {"ok": True}

    def cancel(self, run_id: str) -> dict:
        with self.lock:
            run = self.runs.get(run_id)
            if not run:
                return {"ok": False}
            run["status"] = "cancelled"
            for (rid, idx), event in list(self.decisions.items()):
                if rid == run_id:
                    run["steps"][idx]["decision"] = "skip"; event.set()
        self._publish(run)
        return {"ok": True}

    def quick(self, tool: str, args: dict | None = None) -> dict:
        """One-tap buttons on the Assistant page (low-risk tools only)."""
        if self.risk(tool) != "low":
            return {"ok": False, "error": "That action needs confirmation; ask for it in the command box."}
        try:
            return self.control.run(tool, args or {})
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}
