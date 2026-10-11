"""The local endpoint Handy's Custom post-processing provider calls.

Handy sends one OpenAI-style chat request per dictation. We read the screen,
add the dictionary, ask the configured model, and answer in the same shape.
Any failure answers with the raw transcript, so dictation is never lost.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from . import context as context_mod
from . import modes
from .config import Config
from .context import Context
from .dictionary import Dictionary
from .memory import Memory, normalize
from .prompt import extract_transcript

LOG_MAX_BYTES = 1_000_000
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}  # the Host names a request from this laptop's apps carries
PREFETCH_MAX_AGE_S = 10.0  # a screen read from the key release is used only this long after it
# Load the local model while the cloud quota runs low, so the fallback after a
# 429 does not also pay the cold load (10.2 s on the Framework, 2026-10-09).
# Groq's free plan: 8000 tokens a minute, 1000 requests a day.
WARM_TOKENS_LEFT = 0.25  # share of the per-minute token limit
WARM_REQUESTS_LEFT = 20
WARM_EVERY_S = 300.0


def call_upstream(cfg: Config, messages: list[dict], timeout: float,
                  on_headers: Callable | None = None) -> str:
    """One chat completion against the configured OpenAI-compatible endpoint."""
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": False,
        "temperature": 0,
    }
    if cfg.reasoning_effort:
        payload["reasoning_effort"] = cfg.reasoning_effort  # gpt-oss takes low/medium/high, qwen3 "none"
    if cfg.keep_alive and cfg.upstream_is_local:
        payload["keep_alive"] = cfg.keep_alive  # Ollama: keep the model loaded between dictations
    # Groq's front end answers 403 to urllib's default "Python-urllib" agent.
    headers = {"Content-Type": "application/json", "User-Agent": "handy-context"}
    if cfg.upstream_api_key:
        headers["Authorization"] = f"Bearer {cfg.upstream_api_key}"
    req = urllib.request.Request(
        cfg.upstream_base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        if on_headers is not None:
            on_headers(resp.headers)
    return body["choices"][0]["message"]["content"] or ""


def quota_low(headers) -> bool:
    """True when the cloud's rate-limit headers say a 429 is near."""
    def num(name):
        try:
            return float(headers.get(name))
        except (TypeError, ValueError):
            return None

    tokens, limit = num("x-ratelimit-remaining-tokens"), num("x-ratelimit-limit-tokens")
    requests = num("x-ratelimit-remaining-requests")
    if tokens is not None and limit and tokens < limit * WARM_TOKENS_LEFT:
        return True
    return requests is not None and requests < WARM_REQUESTS_LEFT


def warm_local(cfg: Config) -> None:
    """Ask Ollama to load the model and keep it; an empty prompt only loads."""
    req = urllib.request.Request(
        cfg.upstream_base_url.removesuffix("/v1") + "/api/generate",
        data=json.dumps({"model": cfg.model, "keep_alive": cfg.keep_alive}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def _skip_seconds(exc: Exception) -> float | None:
    """How long to leave the cloud model alone after this error; None when the
    error is not one the local model can fix (a bad request fails there too)."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:  # rate limit: Groq says when to come back
            try:
                return float(exc.headers.get("retry-after") or 60)
            except (TypeError, ValueError):
                return 60.0
        return 30.0 if exc.code >= 500 else None
    if isinstance(exc, (urllib.error.URLError, ConnectionError)):  # offline
        return 30.0
    return None


def _completion(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-hc-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
    }


def _run_with_deadline(fn: Callable, timeout: float):
    """Run fn in a thread; return (result, error). Abandon it at the deadline."""
    box: dict = {}

    def target():
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return None, TimeoutError(f"no answer in {timeout:.1f}s")
    return box.get("result"), box.get("error")


class Helper:
    """The request logic, kept apart from HTTP so tests can drive it directly."""

    def __init__(self, cfg: Config, capture: Callable[[], Context] | None = None, upstream=None,
                 keys=None, read_selection: Callable[[], str] | None = None, memory: Memory | None = None,
                 learner=None, warm=None):
        self.cfg = cfg
        self.warm = warm or warm_local
        self._warmed_at = -WARM_EVERY_S  # monotonic time of the last warm-up
        self._warm_started = False  # for the next dictation's log line
        self.capture = capture or (
            lambda: context_mod.capture(modes.EDIT_MAX_CHARS, cfg.context_budget_ms,
                                        cfg.context_max_chars, cfg.visible_max_chars)
        )
        self.upstream = upstream or (
            lambda c, messages, timeout: call_upstream(c, messages, timeout, self.saw_headers)
        )
        self.keys = keys  # select_left(n), collapse_right(); winui on Windows when None
        self.read_selection = read_selection or (lambda: context_mod.capture(modes.EDIT_MAX_CHARS, 120).selection)
        # Direct selection only with the real keyboard; tests with fake keys drive the key path.
        self.select_uia = context_mod.select_before_caret if keys is None else None
        self.memory = memory or Memory(cfg.edit_window_s)
        self.learner = learner
        self._prefetch_lock = threading.Lock()
        self._prefetched: dict | None = None
        self.fallback_cfg = cfg.fallback()
        self._cloud_back_at = 0.0  # monotonic time the cloud model may be tried again

    def saw_headers(self, headers) -> None:
        """After each answer: if the cloud quota is running low, load the local
        fallback model in the background. Never blocks, never raises."""
        local = self.fallback_cfg
        if local is None or not local.upstream_is_local or not quota_low(headers):
            return
        now = time.monotonic()
        if now - self._warmed_at < WARM_EVERY_S:
            return
        self._warmed_at, self._warm_started = now, True

        def run():
            try:
                self.warm(local)
            except Exception:
                pass  # the fallback then loads the model itself, as before

        threading.Thread(target=run, name="hc-warm", daemon=True).start()

    def prefetch(self) -> None:
        """Read the screen now, when the talk key goes up, so the request that
        arrives after Handy transcribes does not wait for it. Never blocks."""
        box = {"at": time.monotonic(), "done": threading.Event()}

        def run():
            try:
                box["ctx"] = self.capture()
            except Exception as exc:
                box["error"] = exc
            box["done"].set()

        with self._prefetch_lock:
            self._prefetched = box
        threading.Thread(target=run, name="hc-prefetch", daemon=True).start()

    def _take_prefetched(self) -> Context | None:
        with self._prefetch_lock:
            box, self._prefetched = self._prefetched, None
        if box is None or time.monotonic() - box["at"] > PREFETCH_MAX_AGE_S:
            return None
        if not box["done"].wait(self.cfg.context_budget_ms / 1000 + 0.1):
            return None
        return box.get("ctx")

    def handle(self, request: dict) -> dict:
        started = time.perf_counter()
        prefetched = self._take_prefetched()
        users = [m for m in request.get("messages", []) if m.get("role") == "user"]
        raw = users[-1].get("content", "") if users else ""
        if isinstance(raw, list):  # content parts
            raw = " ".join(p.get("text", "") for p in raw if isinstance(p, dict))
        transcript = extract_transcript(raw)
        log = {"chars_in": len(transcript)}
        dictionary = Dictionary.load(self.cfg.dictionary_path)
        if not transcript.strip():
            return self._answer(request, "", log, started)

        if prefetched is not None:
            ctx, log["prefetched"] = prefetched, True
        else:
            ctx, err = _run_with_deadline(self.capture, self.cfg.context_budget_ms / 1000 + 0.1)
            if err or ctx is None:
                ctx = Context(error=f"capture: {err!r}"[:200])
        log.update(app=ctx.app, context_ms=ctx.ms, context_chars=len(ctx.near_cursor) + len(ctx.visible) + len(ctx.selection))
        if ctx.error:
            log["context_error"] = ctx.error
        if self.cfg.log_context:
            log["context"] = ctx.__dict__
        if self.learner is not None:
            try:
                learned = self.learner.check(ctx)  # a hand fix of the previous paste, if any
            except Exception as exc:
                learned, log["learn_error"] = None, f"{exc!r}"[:200]
            if learned:
                log["learned"] = learned
                dictionary = Dictionary.load(self.cfg.dictionary_path)

        # One time budget for every model call this dictation makes; the local
        # fallback, when it takes over, gets its own (it is slower).
        local = self.fallback_cfg if time.monotonic() < self._cloud_back_at else None
        budget = {"end": time.perf_counter() + (local or self.cfg).timeout_s, "cfg": local or self.cfg}
        spent = {"ms": 0}
        if local:
            log["upstream"] = "fallback: cloud resting"

        def call(cfg, messages):
            remaining = budget["end"] - time.perf_counter()
            if remaining <= 0.05:
                raise TimeoutError("time budget spent")
            t0 = time.perf_counter()
            answer, err = _run_with_deadline(lambda: self.upstream(cfg, messages, remaining), remaining + 0.2)
            spent["ms"] += int((time.perf_counter() - t0) * 1000)
            return answer, err

        def ask(messages):
            answer, err = call(budget["cfg"], messages)
            if err is not None and budget["cfg"] is self.cfg and self.fallback_cfg is not None:
                skip = _skip_seconds(err)
                if skip is not None:
                    self._cloud_back_at = time.monotonic() + skip
                    budget.update(cfg=self.fallback_cfg, end=time.perf_counter() + self.fallback_cfg.timeout_s)
                    log["upstream"] = f"fallback: {err!r}"[:160]
                    answer, err = call(self.fallback_cfg, messages)
            if err is not None:
                raise err
            return answer or ""

        last = self.memory.last_before_caret(ctx) if self.cfg.edit_last else None
        out = modes.decide(transcript, ctx, dictionary, last[0] if last else None, ask)
        log.update(mode=out.mode, model_ms=spent["ms"])
        if self.cfg.edit_last and out.mode == "dictate":
            log["edit_route"] = out.route or f"no last dictation: {self.memory.why_not(ctx)}"
        if out.fallback:
            log["fallback"] = out.fallback
        if self._warm_started:
            self._warm_started, log["warm_local"] = False, "cloud quota low"
        text = out.text
        if out.mode == "edit_last" and text:
            ok = self._select_last(*last)
            log["select_check"] = "ok" if ok else "mismatch"
            log["select_seen"] = self._select_seen  # lengths only, never the text
            if not ok:
                text = ""  # the selection was dropped; paste nothing, the old text stays
        text = dictionary.apply(text) if text else ""
        if text:
            self.memory.remember(text, ctx)
            if self.learner is not None:
                self.learner.pasted(text, ctx)
        return self._answer(request, text, log, started)

    def _select_last(self, text: str, presses: int) -> bool:
        """Select the last paste, then confirm the selection is exactly it.

        Through UI Automation when the app allows it (one call, any length),
        else Shift+Left key presses. On any doubt the selection is dropped
        again (Right arrow) and False returned.
        """
        keys = self.keys
        select_uia = self.select_uia
        if keys is None:
            from . import winui as keys
        self._select_seen = {"want": presses, "reads": []}
        try:
            t0 = time.perf_counter()
            via = select_uia(presses) if select_uia else None
            self._select_seen["via"] = "uia" if via is not None else "keys"
            if via is None:
                keys.select_left(presses)
            wanted = {text, text + " "}
            # Keys reach Notepad at ~100 per second (measured 2026-10-07), so allow for them.
            end = time.perf_counter() + 0.8 + (0 if via is not None else presses * 0.012)
            while time.perf_counter() < end:  # SendInput is asynchronous; poll the read-back
                got = normalize(self.read_selection())
                self._select_seen["reads"].append([len(got), int((time.perf_counter() - t0) * 1000)])
                if got in wanted:
                    return True
                time.sleep(0.02)
        except Exception as exc:
            self._select_seen["error"] = f"{exc!r}"[:120]
        try:
            keys.collapse_right()
        except Exception:
            pass
        return False

    def _answer(self, request: dict, text: str, log: dict, started: float) -> dict:
        fmt = request.get("response_format") or {}
        content = json.dumps({"transcription": text}) if fmt.get("type") == "json_schema" else text
        log.update(chars_out=len(text), total_ms=int((time.perf_counter() - started) * 1000))
        self._log(log)
        return _completion(content, self.cfg.model)

    def _log(self, entry: dict) -> None:
        try:
            self.cfg.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.cfg.log_dir / "requests.jsonl"
            if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
                path.replace(path.with_suffix(".old.jsonl"))
            entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
            with path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass


def make_server(cfg: Config, helper: Helper | None = None) -> ThreadingHTTPServer:
    helper = helper or Helper(cfg)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _from_browser(self) -> bool:
            # Any web page can post to 127.0.0.1, and with DNS rebinding read the answer.
            # Browsers always send Origin on such a post; Handy never does (llm_client.rs).
            # A rebound page's Host is its own name, so only loopback names pass.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if self.headers.get("Origin") is not None or host not in LOOPBACK_HOSTS:
                self._send(403, {"error": "forbidden"})
                return True
            return False

        def do_GET(self):
            if self._from_browser():
                return
            path = self.path.rstrip("/")
            if path == "/health":
                self._send(200, b"ok", "text/plain")
            elif path.endswith("/models"):
                self._send(200, {"object": "list", "data": [{"id": cfg.model, "object": "model", "owned_by": "handy-context"}]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self._from_browser():
                return
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"error": "bad json"})
                return
            self._send(200, helper.handle(request))
            if self.server.on_done:
                self.server.on_done()

        def log_message(self, *args):  # quiet; our own log is requests.jsonl
            pass

    server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    server.on_done = None  # set by __main__ to tell the floater a cleanup finished
    return server
