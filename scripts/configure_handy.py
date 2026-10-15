"""Point Handy at the helper. Run with Handy closed: it rewrites its settings while running.

    python scripts/configure_handy.py          # apply
    python scripts/configure_handy.py --check  # print the settings A6 checks, change nothing
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from handy_context.config import load_config  # noqa: E402

STORE = Path(os.environ["APPDATA"]) / "com.pais.handy" / "settings_store.json"
PROMPT_ID = "handy-context"
RAW_SHORTCUT = "ctrl+shift+space"
# Right Alt is read by the helper's keyboard hook, which holds F13 down for as
# long as you talk. Handy listens on F13 in push-to-talk mode, so its recording
# state always follows the key (handy-keys 0.3.4 maps F13 and accepts injected keys).
HELPER_KEY = "f13"
# The mic stays off between dictations (the user, 2026-10-07: an always-open
# mic felt creepy). Handy 0.9.8 opens it on key press: ~1 s the first time
# after Handy starts (mic format query 653 ms + voice detector load 228 ms,
# both cached in memory after), then ~42 ms, and closes it at release. The
# buffer keeps recording after release so the last word is not cut
# (managers/audio.rs).
EXTRA_BUFFER_MS = 200
# A dictation with no text box focused was lost (the user, 2026-10-15). Handy
# 0.9.8 writes the pasted text to the clipboard after pasting when this is set
# (clipboard.rs), so it can be pasted again by hand.
CLIPBOARD_HANDLING = "copy_to_clipboard"
# Handy's History tab keeps this many dictations, each with its ~1 MB recording
# (recording_retention_period "preserve_limit"). Handy's default is 5.
HISTORY_LIMIT = 100


def handy_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq handy.exe", "/NH"], capture_output=True, text=True).stdout
    return "handy.exe" in out.lower()


def check(s: dict, base_url: str, right_alt: bool = False) -> list[str]:
    problems = []
    if right_alt:
        if s.get("bindings", {}).get("transcribe_with_post_process", {}).get("current_binding") != HELPER_KEY:
            problems.append(f"the cleanup shortcut is not {HELPER_KEY} (the helper presses it for Right Alt)")
        if s.get("shortcut_activation") != "push_to_talk":
            problems.append(f"shortcut_activation is {s.get('shortcut_activation')!r}, not 'push_to_talk'")
        if s.get("overlay_style") != "none":
            problems.append("Handy's own overlay is on; the helper's floater replaces it")
    if s.get("always_on_microphone"):
        problems.append("always_on_microphone is on: the mic stays open while idle")
    if s.get("extra_recording_buffer_ms", 0) < EXTRA_BUFFER_MS:
        problems.append(f"extra_recording_buffer_ms is under {EXTRA_BUFFER_MS}: the last word is cut at release")
    if s.get("clipboard_handling") != CLIPBOARD_HANDLING:
        problems.append("clipboard_handling does not keep the dictation on the clipboard")
    if s.get("history_limit", 0) < HISTORY_LIMIT:
        problems.append(f"history_limit is under {HISTORY_LIMIT}: the History tab drops older dictations")
    if not s.get("post_process_enabled"):
        problems.append("post-processing is off")
    if s.get("post_process_provider_id") != "custom":
        problems.append(f"provider is {s.get('post_process_provider_id')!r}, not 'custom'")
    custom = next((p for p in s.get("post_process_providers", []) if p.get("id") == "custom"), {})
    if custom.get("base_url") != base_url:
        problems.append(f"custom base_url is {custom.get('base_url')!r}")
    prompt = next((p for p in s.get("post_process_prompts", []) if p.get("id") == s.get("post_process_selected_prompt_id")), {})
    if prompt.get("prompt") != "${output}":
        problems.append(f"selected prompt text is {prompt.get('prompt', '')[:40]!r}, not '${{output}}'")
    b = s.get("bindings", {})
    if b.get("transcribe", {}).get("current_binding") != RAW_SHORTCUT:
        problems.append("plain transcribe is not on ctrl+shift+space")
    return problems


def main() -> int:
    cfg = load_config()
    base_url = f"http://{cfg.host}:{cfg.port}/v1"
    if not STORE.exists():
        print(f"No Handy settings at {STORE}. Open Handy once, finish its setup, close it, then rerun.")
        return 1
    data = json.loads(STORE.read_text(encoding="utf-8"))
    s = data["settings"]

    if "--check" in sys.argv:
        b = s.get("bindings", {})
        print(f"main shortcut (with cleanup): {b.get('transcribe_with_post_process', {}).get('current_binding')}")
        print(f"raw shortcut (no cleanup):    {b.get('transcribe', {}).get('current_binding')}")
        print(f"speech model: {s.get('selected_model')}")
        if s.get("custom_words"):
            print(f"note: Handy's own custom words are set ({len(s['custom_words'])}); dictionary.txt is the one list")
        problems = check(s, base_url, cfg.right_alt)
        print("OK" if not problems else "PROBLEMS:\n- " + "\n- ".join(problems))
        return 0 if not problems else 1

    if handy_running():
        print("Handy is running. Quit it from the tray icon (right-click > Quit), then rerun.")
        return 1

    shutil.copy2(STORE, STORE.with_name(f"settings_store.backup-{time.strftime('%Y%m%d-%H%M%S')}.json"))

    s["always_on_microphone"] = False
    s["extra_recording_buffer_ms"] = max(s.get("extra_recording_buffer_ms", 0), EXTRA_BUFFER_MS)
    s["clipboard_handling"] = CLIPBOARD_HANDLING
    s["history_limit"] = max(s.get("history_limit", 0), HISTORY_LIMIT)
    s["post_process_enabled"] = True
    s["post_process_provider_id"] = "custom"
    for p in s.setdefault("post_process_providers", []):
        if p.get("id") == "custom":
            p["base_url"] = base_url
    s.setdefault("post_process_models", {})["custom"] = cfg.model
    prompts = [p for p in s.setdefault("post_process_prompts", []) if p.get("id") != PROMPT_ID]
    # Exactly ${output}: the helper owns the cleanup rules. Never blank (Handy skips blank prompts).
    prompts.append({"id": PROMPT_ID, "name": "handy-context (rules live in the helper)", "prompt": "${output}"})
    s["post_process_prompts"] = prompts
    s["post_process_selected_prompt_id"] = PROMPT_ID

    # Only the post-processing action reaches the helper, so it gets the main shortcut.
    b = s["bindings"]
    plain, post = b["transcribe"], b["transcribe_with_post_process"]
    if plain["current_binding"] != RAW_SHORTCUT:
        main_key = plain["current_binding"]
        post["current_binding"] = main_key
        plain["current_binding"] = RAW_SHORTCUT
    if cfg.right_alt:
        post["current_binding"] = HELPER_KEY
        s["shortcut_activation"] = "push_to_talk"
    if cfg.floater:
        s["overlay_style"] = "none"

    STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    problems = check(s, base_url, cfg.right_alt)
    print("Handy configured." if not problems else "Still wrong:\n- " + "\n- ".join(problems))
    if cfg.right_alt:
        print("Dictate: hold Right Alt to talk; Right Alt+Space for hands-free, Right Alt again to stop.")
    else:
        print(f"Main shortcut, with Deep Context: {post['current_binding']}.")
    print(f"Raw, no cleanup: {plain['current_binding']}.")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
