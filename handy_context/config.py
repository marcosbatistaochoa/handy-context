"""All settings, resolved in one place. Model ids live here and in .env only."""

import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_URL = "http://127.0.0.1:11434/v1"  # Ollama
LOCAL_MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def _data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "handy-context"


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines; real environment wins."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    upstream_base_url: str
    upstream_api_key: str
    model: str
    dictionary_path: Path
    timeout_s: float
    context_budget_ms: int
    context_max_chars: int
    log_dir: Path
    log_context: bool
    floater: bool
    right_alt: bool
    handy_exe: Path
    edit_last: bool = True
    edit_window_s: float = 60.0
    learn: bool = True
    keep_alive: str = "-1m"
    visible_max_chars: int = 500
    reasoning_effort: str = "none"
    # Used when a cloud upstream is rate-limited, failing or unreachable.
    fallback_base_url: str = ""
    fallback_model: str = ""
    fallback_timeout_s: float = 8.0

    @property
    def upstream_is_local(self) -> bool:
        return "127.0.0.1" in self.upstream_base_url or "localhost" in self.upstream_base_url

    def fallback(self) -> "Config | None":
        """The local model's settings, or None when there is no separate fallback."""
        if not self.fallback_base_url or self.fallback_base_url == self.upstream_base_url:
            return None
        return replace(self, upstream_base_url=self.fallback_base_url, upstream_api_key="",
                       model=self.fallback_model, reasoning_effort="none", timeout_s=self.fallback_timeout_s,
                       fallback_base_url="")


def load_config() -> Config:
    _load_dotenv(ROOT / ".env")
    data = _data_dir()
    env = os.environ.get
    return Config(
        host=env("HC_HOST", "127.0.0.1"),
        port=int(env("HC_PORT", "8765")),
        upstream_base_url=env("HC_UPSTREAM_BASE_URL", LOCAL_URL).rstrip("/"),
        upstream_api_key=env("HC_UPSTREAM_API_KEY", ""),
        model=env("HC_MODEL", LOCAL_MODEL),
        dictionary_path=Path(env("HC_DICTIONARY", str(data / "dictionary.txt"))),
        timeout_s=float(env("HC_TIMEOUT_S", "4")),
        context_budget_ms=int(env("HC_CONTEXT_BUDGET_MS", "250")),
        context_max_chars=int(env("HC_CONTEXT_MAX_CHARS", "1000")),
        visible_max_chars=int(env("HC_VISIBLE_MAX_CHARS", "500")),
        log_dir=Path(env("HC_LOG_DIR", str(data / "logs"))),
        log_context=env("HC_LOG_CONTEXT", "0") == "1",
        floater=env("HC_FLOATER", "1") == "1",
        right_alt=env("HC_RIGHT_ALT", "1") == "1",
        handy_exe=Path(env("HC_HANDY_EXE", str(Path(env("LOCALAPPDATA", "")) / "Handy" / "handy.exe"))),
        edit_last=env("HC_EDIT_LAST", "1") == "1",
        edit_window_s=float(env("HC_EDIT_WINDOW_S", "60")),
        learn=env("HC_LEARN", "1") == "1",
        keep_alive=env("HC_KEEP_ALIVE", "-1m"),
        reasoning_effort=env("HC_REASONING_EFFORT", "none"),
        fallback_base_url=env("HC_FALLBACK_BASE_URL", LOCAL_URL).rstrip("/"),
        fallback_model=env("HC_FALLBACK_MODEL", LOCAL_MODEL),
        fallback_timeout_s=float(env("HC_FALLBACK_TIMEOUT_S", "8")),
    )
