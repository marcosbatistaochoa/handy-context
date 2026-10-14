# Public release of handy-context

Tier: 2 · Repo: handy-context · Written: 2026-10-11 · Bene Gesserit: skipped, no Bene Gesserit yet
Run: through · Risky: yes (publishes to the internet)
Lessons applied: `2026-09-23 [install]` (scanner installs go to the user as one `!` line if auto mode refuses), `2026-09-23 [facts]` (every count in the findings comes from a command run that day), `2026-09-24 [rewrite]` (README rewrite carries kept text)

## Summary

- **You get:** handy-context public on GitHub under the MIT license, starting from one clean commit. It has a README anyone can follow to install it. Before that: a security review of what goes public, every finding fixed or explained, and a notes file of what this first review taught, kept for a future security agent.
- **Cost:** about 2 hours of agent time, moderate usage.
- **Risks:** a leak we miss becomes public and stays cached even if deleted later (the reason for the fresh repo and the scan). The old repo is kept private, renamed, with all of its history.
- **Your decisions:** none open. Settled 2026-10-11: a fresh start with the old history kept privately; MIT license.

## Goal (frozen once approved)

- **Objective:** `github.com/marcosbatistaochoa/handy-context` is a new public repo whose only history is one reviewed commit, and a stranger can install the helper from its README.
- **Always:** fail open; the helper stays local by default; the old history stays in a private repo.
- **Never:** employer data or work identity in the public tree or its commit metadata; secrets in git; opening windows or pasting on the user's screen during checks.
- **Stop conditions:** a finding that needs a design change the user would notice; a leaked live key (revoking it is the user's step).

## Acceptance criteria

- **A1.** The old repo is private under a new name and `git ls-remote` of it matches the pre-release remote ref for ref; the mirror copy `handy-context-archive` matches too.
- **A2.** The detailed findings (`security-review-2026-10-11.md`) are committed to the private old repo only. The public tree has `docs/security-review.md`, a summary with no names, listing each scan, tool and version, counts, and each finding's status.
- **A3.** On the published tree, gitleaks finds 0 secrets, and a case-insensitive `git grep` for the employer's name and its heard form, the staff name, the user's handle and spoken variants of it, and both personal emails prints nothing. The same grep over the A8 file prints nothing.
- **A4.** `git log --all --format='%ae %ce'` on a fresh clone of the public repo prints one line, the GitHub noreply address twice.
- **A5.** `LICENSE` is MIT, 2026, in the holder's name.
- **A6.** From a fresh clone in the scratchpad: `pip install -e .` works, `pytest` passes, and a helper started headless returns the raw transcript when the model is unreachable (fail open). The README steps that change Handy or autostart (`configure_handy.py`, `install.ps1`) are checked by reading against the scripts, not run.
- **A7.** `gh repo view --json visibility` prints `PUBLIC`, and `gh api repos/marcosbatistaochoa/handy-context --jq .security_and_analysis` shows secret scanning and push protection enabled.
- **A8.** `ai-system/docs/research/2026-10-11-security-review-lessons.md` holds the checklist and the lessons, each tied to a finding in A2, with no names.
- **A9.** A browser-style request (an `Origin` header, or a non-loopback `Host`) to the helper gets 403 before the screen is read (`tests/test_server.py`), and the running helper on this laptop was restarted onto that code.

## Decided without you

- New public repo, old one renamed and kept private: the critic showed a force-push leaves old commits reachable by ID on GitHub. Source: critic pass one; GitHub docs on removing sensitive data (unverified this session).
- Author email on the public commit is GitHub's noreply address, not the gmail: public commit emails are harvested. My choice.
- Scanners: gitleaks (secrets, tree and full history), bandit and semgrep (Python static analysis), pip-audit (dependencies), a privacy grep, every image read by eye, and a probe of the local server. My choice.
- Personal sample words in tests are replaced with made-up ones; the eval case that guarded the user's own acronym becomes generic. My choice; cost: that eval case no longer checks the user's real dictionary.
- Personal working files (`STATE.md`, `TRIALS.md`, `plans/`, `runs/`, `BACKBURNER.md`) stay public with employer details removed; laptop names stay. My choice.
- The Framework clone: its `origin` will point at the new public repo. It is reset to the public commit and given the noreply email from a session on the Framework, tracked in `ai-system` `STATE.md`; a GitHub ruleset that refuses other author emails is tried first. My choice.

## Units

### U1. Archive and keep the old repo private
- **Does:** mirror to `handy-context-archive` (done), and at publish rename the old repo so the name is free.
- **Check:** A1. · **Risk:** high (network) · **Owner:** inline

### U2. Scan
- **Does:** every scanner above; detailed findings to the private file, summary to `docs/security-review.md`.
- **Check:** A2. · **Risk:** routine · **Owner:** inline

### U3. Fix findings and scrub
- **Does:** the localhost fix (A9); names replaced; tests updated.
- **Check:** `pytest` passes; A3; A9. · **Risk:** high · **Owner:** inline

### U4. README setup, LICENSE, SECURITY note
- **Files:** `README.md`, `LICENSE`, `SECURITY.md`, `pyproject.toml`.
- **Check:** A5, A6. · **Risk:** routine · **Owner:** inline

### U5. Publish
- **Does:** export the tracked tree only; one commit with the noreply author; create the new public repo with secret scanning and push protection; push; set the local clone's `origin` and `user.email`.
- **Check:** A4, A7. · **Risk:** high (outward) · **Owner:** inline

### U6. Lessons for the security agent
- **Files:** `ai-system/docs/research/2026-10-11-security-review-lessons.md`, `ai-system/STATE.md`.
- **Check:** A8. · **Risk:** routine · **Owner:** inline

## Critic

- Force-push leaves old commits reachable on GitHub — fixed: new repo, old one renamed and private (A1, U5).
- An honest findings list contains the names A3 forbids — fixed: detailed list stays private, public summary has none (A2, A8).
- `git pull --rebase` on an old clone stacks new work-identity commits onto the public history — fixed: ruleset attempt plus a tracked Framework reset step.
- A3 and A4 too narrow (heard form, surrounding wording, committer email, images) — fixed: A3 and A4 widened; images read by eye and logged in A2.
- A1, A6, A7 did not prove their part — fixed: ref-for-ref compare, README steps that touch Handy checked by reading, `security_and_analysis` read back.

## Progress

Now: done. Framework re-cloned 2026-10-13 (`ai-system` STATE 2.2); plan closed 2026-10-14.

- 2026-10-11 U1 mirror made; refs identical to the remote.
- 2026-10-11 U2 gitleaks history 0, tree 0 tracked (2 hits in ignored files); bandit 16 low/false; semgrep 0 of 21 files; pip-audit 0; 8 images clean; localhost finding confirmed by failing tests.
- 2026-10-11 U3 localhost fix 334fe16; scrub done, 94 tests pass.
- 2026-10-11 U4 README setup, LICENSE, SECURITY.md; fresh clone: pip install -e . failed, fixed in pyproject; 94 pass; fail open 2.1 s; browser request 403 (A5, A6).
- 2026-10-11 U5 old repo renamed handy-context-old (private); new public repo, secret scanning and push protection on before the push; ruleset protect-main (no force push, no deletion); author-email rules refused by GitHub (422). Fresh clone: one commit, noreply author and committer, gitleaks 0, privacy grep empty, license MIT (A1, A3, A4, A7).
- 2026-10-11 A9 live helper restarted with install.ps1, browser request 403.
- 2026-10-11 U6 lessons in ai-system docs/research/2026-10-11-security-review-lessons.md, playbook lesson 2026-10-11 [publish], STATE 2.2 re-clone step (A8).
- 2026-10-11 after restart: eval_cleanup --pace 8 on Groq: cleanup 37/40 (3 sentence-splitting cases), edit 21/21, not_edit 22/22, false edits 0, median 457 ms.
