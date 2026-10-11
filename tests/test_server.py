import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from handy_context.config import LOCAL_MODEL, LOCAL_URL, load_config
from handy_context.context import Context
from handy_context.server import Helper, make_server

# Handy's legacy body for the Custom provider (llm_client.rs, actions.rs:310).
HANDY_BODY = {"model": "qwen3:4b", "messages": [{"role": "user", "content": ""}], "stream": False, "reasoning_effort": "none"}


@pytest.fixture
def cfg(tmp_path):
    base = load_config()
    dict_path = tmp_path / "dictionary.txt"
    dict_path.write_text("Xylocarpa\nmari gold => Marigold\n", encoding="utf-8")
    # The local-model setup whatever this laptop's .env says (the Framework's points at Groq).
    return replace(base, dictionary_path=dict_path, log_dir=tmp_path / "logs", timeout_s=1.0, context_budget_ms=200, port=0,
                   upstream_base_url=LOCAL_URL, upstream_api_key="", model=LOCAL_MODEL, reasoning_effort="none",
                   fallback_base_url=LOCAL_URL, fallback_model=LOCAL_MODEL)


def http_error(code, retry_after=None):
    headers = {"retry-after": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://api.groq.com/openai/v1/chat/completions", code, "err", headers, None)


def cloud(cfg):
    return replace(cfg, upstream_base_url="https://api.groq.com/openai/v1", upstream_api_key="k",
                   model="openai/gpt-oss-120b", reasoning_effort="low", fallback_timeout_s=1.0)


def test_rate_limit_falls_back_to_local_and_rests_the_cloud(cfg):
    calls = []

    def upstream(c, messages, timeout):
        calls.append(c.model)
        if c.model == "openai/gpt-oss-120b":
            raise http_error(429, "120")
        assert c.upstream_base_url == LOCAL_URL and c.upstream_api_key == "" and c.reasoning_effort == "none"
        return "Hello there."

    helper = Helper(cloud(cfg), capture=lambda: Context(), upstream=upstream)
    assert content(helper.handle(body("hello there"))) == "Hello there."
    assert calls == ["openai/gpt-oss-120b", LOCAL_MODEL]
    assert "429" in logs(cfg)[-1]["upstream"]
    # Within Retry-After the cloud is not tried again.
    assert content(helper.handle(body("hello there"))) == "Hello there."
    assert calls[2:] == [LOCAL_MODEL]
    assert logs(cfg)[-1]["upstream"] == "fallback: cloud resting"


def test_bad_request_does_not_fall_back(cfg):
    calls = []

    def upstream(c, messages, timeout):
        calls.append(c.model)
        raise http_error(400)

    helper = Helper(cloud(cfg), capture=lambda: Context(), upstream=upstream)
    assert content(helper.handle(body("hello there"))) == "hello there"
    assert calls == ["openai/gpt-oss-120b"]


def test_local_upstream_has_no_fallback(cfg):
    assert cfg.fallback() is None
    assert cloud(cfg).fallback().model == LOCAL_MODEL


# Groq's real headers, 2026-10-09: limit 8000 tokens a minute, 1000 requests a day.
def groq_headers(tokens_left, requests_left=998):
    return {"x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": str(tokens_left),
            "x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": str(requests_left)}


def wait_for(cond, seconds=2.0):
    end = time.monotonic() + seconds
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def test_low_cloud_quota_warms_the_local_model_once(cfg):
    warmed = []
    helper = Helper(cloud(cfg), capture=lambda: Context(), upstream=lambda c, m, t: "Hi.", warm=warmed.append)
    helper.saw_headers(groq_headers(7921))  # plenty left
    helper.saw_headers({})  # no rate-limit headers at all
    time.sleep(0.05)
    assert warmed == []
    helper.saw_headers(groq_headers(1500))  # under a quarter of the minute's tokens
    assert wait_for(lambda: len(warmed) == 1)
    assert warmed[0].model == LOCAL_MODEL and warmed[0].upstream_base_url == LOCAL_URL
    helper.saw_headers(groq_headers(900, requests_left=5))  # still low: no second load within 5 minutes
    time.sleep(0.05)
    assert len(warmed) == 1
    helper.handle(body("hello there"))
    assert logs(cfg)[-1]["warm_local"] == "cloud quota low"


def test_few_requests_left_today_warms(cfg):
    warmed = []
    helper = Helper(cloud(cfg), capture=lambda: Context(), upstream=lambda c, m, t: "Hi.", warm=warmed.append)
    helper.saw_headers(groq_headers(7900, requests_left=10))
    assert wait_for(lambda: len(warmed) == 1)


def test_local_upstream_never_warms(cfg):
    warmed = []
    helper = Helper(cfg, capture=lambda: Context(), upstream=lambda c, m, t: "Hi.", warm=warmed.append)
    helper.saw_headers(groq_headers(10, requests_left=1))
    time.sleep(0.05)
    assert warmed == []


def test_failing_warm_is_harmless(cfg):
    def boom(c):
        raise urllib.error.URLError("ollama down")

    helper = Helper(cloud(cfg), capture=lambda: Context(), upstream=lambda c, m, t: "Hi.", warm=boom)
    helper.saw_headers(groq_headers(100))
    assert content(helper.handle(body("hello there"))) == "Hi."


def body(text):
    b = json.loads(json.dumps(HANDY_BODY))
    b["messages"][0]["content"] = text
    return b


def content(resp):
    return resp["choices"][0]["message"]["content"]


def logs(cfg):
    return [json.loads(l) for l in (cfg.log_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()]


def test_context_and_dictionary_reach_the_model(cfg):
    seen = {}

    def upstream(c, messages, timeout):
        seen["messages"] = messages
        return "Ask mari gold about Xylocarpa."

    helper = Helper(cfg, capture=lambda: Context(app="notepad.exe", title="notes.txt", near_cursor="Xylocarpa"), upstream=upstream)
    out = content(helper.handle(body("ask mari gold about zylo carpa")))
    assert out == "Ask Marigold about Xylocarpa."
    system = seen["messages"][0]["content"]
    assert "notepad.exe" in system and "Xylocarpa" in system
    assert seen["messages"][1]["content"] == "<transcript>\nask mari gold about zylo carpa\n</transcript>"
    assert logs(cfg)[-1]["app"] == "notepad.exe"


def test_hanging_upstream_returns_raw_transcript_in_budget(cfg):
    def upstream(c, messages, timeout):
        time.sleep(10)

    helper = Helper(cfg, capture=lambda: Context(), upstream=upstream)
    t0 = time.perf_counter()
    out = content(helper.handle(body("hello mari gold")))
    assert time.perf_counter() - t0 < cfg.timeout_s + 0.2 + cfg.context_budget_ms / 1000 + 0.5
    assert out == "hello Marigold"
    assert "model" in logs(cfg)[-1]["fallback"]


def test_hanging_capture_still_cleans(cfg):
    def capture():
        time.sleep(10)

    helper = Helper(cfg, capture=capture, upstream=lambda c, m, t: "Hello.")
    t0 = time.perf_counter()
    assert content(helper.handle(body("hello"))) == "Hello."
    assert time.perf_counter() - t0 < cfg.context_budget_ms / 1000 + 0.6
    assert "capture" in logs(cfg)[-1]["context_error"]


def test_prefetched_screen_is_used_once(cfg):
    calls = []

    def capture():
        calls.append(1)
        return Context(app=f"app{len(calls)}.exe")

    helper = Helper(cfg, capture=capture, upstream=lambda c, m, t: "Hello.")
    helper.prefetch()  # the key went up
    helper.handle(body("hello"))
    assert len(calls) == 1 and logs(cfg)[-1]["prefetched"] and logs(cfg)[-1]["app"] == "app1.exe"
    helper.handle(body("hello"))  # no key release before this one: capture again
    assert len(calls) == 2 and "prefetched" not in logs(cfg)[-1]


def test_stale_or_failed_prefetch_captures_again(cfg, monkeypatch):
    import handy_context.server as server_mod

    helper = Helper(cfg, capture=lambda: Context(app="fresh.exe"), upstream=lambda c, m, t: "Hello.")
    helper.prefetch()
    monkeypatch.setattr(server_mod, "PREFETCH_MAX_AGE_S", -1.0)
    helper.handle(body("hello"))
    assert "prefetched" not in logs(cfg)[-1]
    monkeypatch.setattr(server_mod, "PREFETCH_MAX_AGE_S", 10.0)

    results = [RuntimeError("uia"), Context(app="fresh.exe")]

    def capture():
        r = results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    helper.capture = capture
    helper.prefetch()  # fails
    helper.handle(body("hello"))
    assert "prefetched" not in logs(cfg)[-1] and logs(cfg)[-1]["app"] == "fresh.exe"


def test_failing_upstream_and_crashing_capture(cfg):
    def boom(*a):
        raise RuntimeError("down")

    helper = Helper(cfg, capture=boom, upstream=boom)
    assert content(helper.handle(body("raw words"))) == "raw words"


def test_answer_far_longer_than_transcript_is_rejected(cfg):
    helper = Helper(cfg, capture=lambda: Context(), upstream=lambda c, m, t: "x" * 1000)
    assert content(helper.handle(body("what time is it"))) == "what time is it"


def test_blank_transcript_skips_model(cfg):
    def upstream(*a):
        raise AssertionError("must not be called")

    assert content(Helper(cfg, capture=lambda: Context(), upstream=upstream).handle(body("   "))) == ""


def test_handy_default_prompt_wrapping_is_unwrapped(cfg):
    seen = {}

    def upstream(c, messages, timeout):
        seen["user"] = messages[1]["content"]
        return "ok"

    Helper(cfg, capture=lambda: Context(), upstream=upstream).handle(
        body("<transcript>\nhi um there\n</transcript>\n\nThe above is a transcript...")
    )
    assert seen["user"] == "<transcript>\nhi um there\n</transcript>"


def test_structured_request_gets_json(cfg):
    req = body("hi")
    req["response_format"] = {"type": "json_schema", "json_schema": {"name": "transcription_output"}}
    out = content(Helper(cfg, capture=lambda: Context(), upstream=lambda c, m, t: "Hi.").handle(req))
    assert json.loads(out) == {"transcription": "Hi."}


class FakeOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.last = req
        data = json.dumps({"choices": [{"message": {"role": "assistant", "content": "<think></think>Hello, Xylocarpa."}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_full_http_round_trip(cfg):
    fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    c = replace(cfg, upstream_base_url=f"http://127.0.0.1:{fake.server_port}/v1")
    server = make_server(c, Helper(c, capture=lambda: Context(title="t")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert urllib.request.urlopen(base + "/health").read() == b"ok"
        models = json.loads(urllib.request.urlopen(base + "/v1/models").read())
        assert models["data"][0]["id"] == c.model
        req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body("hello zylo carpa")).encode(), headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req).read())
        assert content(resp) == "Hello, Xylocarpa."
        assert FakeOllama.last["model"] == c.model and FakeOllama.last["reasoning_effort"] == c.reasoning_effort
        assert "keep_alive" in FakeOllama.last  # a 127.0.0.1 upstream is Ollama
    finally:
        server.shutdown()
        fake.shutdown()


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},  # a page in the browser posting to 127.0.0.1
    {"Origin": "null"},  # the same from a sandboxed frame or a file:// page
    {"Host": "evil.example:5000"},  # DNS rebinding: the page's own name, pointed at 127.0.0.1
])
def test_browser_requests_are_refused_before_the_screen_is_read(cfg, headers):
    captured = []
    server = make_server(cfg, Helper(cfg, capture=lambda: captured.append(1) or Context(), upstream=lambda c, m, t: "x"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body("hello")).encode(),
                                     headers={"Content-Type": "text/plain", **headers})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        assert err.value.code == 403
        assert captured == []
    finally:
        server.shutdown()


def test_handy_request_headers_are_accepted(cfg):
    # What Handy's llm_client.rs sends: no Origin, Host from the base URL.
    server = make_server(cfg, Helper(cfg, capture=lambda: Context(), upstream=lambda c, m, t: "Hi."))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for host in ("127.0.0.1", "localhost"):
            req = urllib.request.Request(f"http://{host}:{server.server_port}/v1/chat/completions",
                                         data=json.dumps(body("hi")).encode(),
                                         headers={"Content-Type": "application/json", "Referer": "https://github.com/cjpais/Handy",
                                                  "User-Agent": "Handy/1.0 (+https://github.com/cjpais/Handy)", "X-Title": "Handy"})
            assert content(json.loads(urllib.request.urlopen(req).read())) == "Hi."
    finally:
        server.shutdown()


class FakeGroq(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        data = json.dumps({"choices": [{"message": {"role": "assistant", "content": "Hi."}}]}).encode()
        self.send_response(200)
        for k, v in groq_headers(1200).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_real_upstream_call_passes_rate_limit_headers_to_the_warm_check(cfg):
    fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeGroq)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    warmed = []
    # The fake stands in for the cloud; the fallback stays on Ollama's address.
    c = replace(cloud(cfg), upstream_base_url=f"http://127.0.0.1:{fake.server_port}/v1")
    try:
        helper = Helper(c, capture=lambda: Context(), warm=warmed.append)
        assert content(helper.handle(body("hi"))) == "Hi."
        assert wait_for(lambda: len(warmed) == 1)
    finally:
        fake.shutdown()


class FakeKeys:
    def __init__(self):
        self.calls = []

    def select_left(self, n):
        self.calls.append(("select_left", n))

    def collapse_right(self):
        self.calls.append(("collapse_right",))


LAST = "Send the report to Kate on Friday."


def edit_last_helper(cfg, selection_read_back):
    cfg = replace(cfg, edit_last=True)
    answers = iter(["EDIT", "Send the report to Kate on Monday."])
    keys = FakeKeys()
    ctx = Context(app="notepad.exe", title="notes.txt", element_id="42", before_caret="Hi. " + LAST)
    helper = Helper(cfg, capture=lambda: ctx, upstream=lambda c, m, t: next(answers), keys=keys,
                    read_selection=lambda: selection_read_back)
    helper.memory.remember(LAST, ctx)
    return helper, keys


def test_edit_last_selects_and_replaces(cfg):
    helper, keys = edit_last_helper(cfg, LAST)
    assert content(helper.handle(body("change Friday to Monday"))) == "Send the report to Kate on Monday."
    assert keys.calls == [("select_left", len(LAST))]
    assert logs(cfg)[-1]["select_check"] == "ok"


def test_edit_last_selection_mismatch_pastes_nothing(cfg):
    helper, keys = edit_last_helper(cfg, "something else")
    assert content(helper.handle(body("change Friday to Monday"))) == ""
    assert keys.calls == [("select_left", len(LAST)), ("collapse_right",)]
    assert logs(cfg)[-1]["select_check"] == "mismatch"


def test_edit_last_key_failure_pastes_nothing(cfg):
    helper, keys = edit_last_helper(cfg, LAST)

    def broken(n):
        raise OSError("SendInput failed")

    keys.select_left = broken
    assert content(helper.handle(body("change Friday to Monday"))) == ""
    assert keys.calls == [("collapse_right",)]


def test_edit_selection_failure_pastes_nothing(cfg):
    def upstream(c, m, t):
        raise RuntimeError("down")

    helper = Helper(cfg, capture=lambda: Context(selection="Long text here."), upstream=upstream)
    assert content(helper.handle(body("make it shorter"))) == ""
    assert logs(cfg)[-1]["mode"] == "edit_selection"
