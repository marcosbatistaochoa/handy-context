"""Run the helper: python -m handy_context"""

import sys
import threading

from . import context
from .config import load_config
from .dictionary import Dictionary
from .learn import Learner
from .server import Helper, call_upstream, make_server


def _warm_model(cfg) -> None:
    """Load the model now, so the first dictation does not pay the load time."""
    try:
        call_upstream(cfg, [{"role": "user", "content": "ok"}], timeout=60)
    except Exception as exc:
        print(f"model warm-up: {exc!r}"[:200], flush=True)


def main() -> None:
    cfg = load_config()
    Dictionary.load(cfg.dictionary_path)  # creates the file on first run
    error = context.warm_up()  # UI Automation setup costs ~0.5 s; pay it now, not on the first dictation
    if error:
        print(f"context: {error}", flush=True)
    learner = Learner(cfg.dictionary_path, cfg.log_dir) if cfg.learn else None
    helper = Helper(cfg, learner=learner)
    server = make_server(cfg, helper)
    threading.Thread(target=_warm_model, args=(cfg,), name="hc-warm", daemon=True).start()
    print(f"handy-context on http://{cfg.host}:{cfg.port}/v1 -> {cfg.upstream_base_url} ({cfg.model})", flush=True)
    if sys.platform != "win32" or not (cfg.floater or cfg.right_alt):
        server.serve_forever()
        return

    from .winui import App

    app = App(str(cfg.handy_exe), right_alt=cfg.right_alt, show_floater=cfg.floater)
    server.on_done = app.post_done  # a finished cleanup ends the floater's finalizing state
    app.on_release = helper.prefetch  # read the screen while Handy transcribes, not after
    threading.Thread(target=server.serve_forever, name="hc-server", daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()
