# Security review before the first public release

Done 2026-10-11 on the private repository, before this public one was
created. The public history starts after it with a single commit, so the
old history (40 commits) is not part of this repository.

| Check | Tool | Result | Status |
|---|---|---|---|
| Secrets in all old history | gitleaks 8.30.1 | 0 | Nothing to fix |
| Secrets in the files published here | gitleaks 8.30.1 | 0 (2 hits in untracked local files: `.env` and a graph cache, both gitignored) | Published from tracked files only |
| Python static analysis | bandit 1.9.4 | 16 low or false (try/except/pass, `subprocess` with fixed arguments, `urlopen` on the configured model URL) | Accepted: none takes outside input |
| Python static analysis | semgrep 1.180.0, `p/python` and `p/secrets` | 0 in 21 files (tests skipped by semgrep's default ignore list) | Nothing to fix |
| Dependencies | pip-audit 2.10.1 | 0 known vulnerabilities in `uiautomation` 2.0.29 and `comtypes` | Nothing to fix |
| Personal and employer details | `git grep` for names, emails, hosts, IPs and paths, including spoken spellings of names | Employer name in notes, tests and comments; a colleague's name in one test; the author's handle as a sample dictionary word | Replaced with made-up names |
| Commit metadata | `git log` author and committer emails | Old commits carried a work email | Not published: fresh history with GitHub's noreply address |
| Images | the 8 PNGs in `docs/floater/`, read by eye and checked for metadata chunks | Floater crops only, no text, no metadata | Nothing to fix |
| Local attack surface | a test that posts to the helper the way a web page would | **The helper accepted the request, read the screen and called the model** | Fixed: requests with an `Origin` header or a non-loopback `Host` get 403 (`tests/test_server.py`) |
| Fresh install | a clone, `pip install -e .`, tests, helper started with no model | `pip install -e .` failed (setuptools found several top-level folders) | Fixed: `pyproject.toml` names the package; 94 tests pass; with no model the raw words came back in 2.1 s |

## The local attack surface finding

Handy sends its cleanup request to the helper on `127.0.0.1`. Any web page
open in a browser can send a request to the same address. Before the fix,
such a request made the helper read the active window, send that text to the
cleanup model and, with "edit last dictation" on, select text in the active
app. A page cannot read a normal reply from another address, but with DNS
rebinding (a page's own host name re-pointed at `127.0.0.1`) it can, so it
could have asked the model to repeat the screen text back.

Browsers always send an `Origin` header on such a request and a rebound page
carries its own name in `Host`. Handy sends neither (`src-tauri/src/llm_client.rs`
in Handy's source sets `Content-Type`, `Referer`, `User-Agent`, `X-Title` and
`Authorization` only), so refusing both blocks the browser and leaves Handy
working.

## Not covered

- No penetration test of the Windows keyboard hook or UI Automation code
  beyond the static analysis above.
- `scripts/configure_handy.py` and `scripts/install.ps1` change Handy's
  settings and the Startup folder; they were checked by reading, not run on
  a clean machine.
