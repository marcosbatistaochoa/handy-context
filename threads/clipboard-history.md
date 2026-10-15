# Clipboard copy and History tab

Session: cd7408f6-b1b3-4a6f-82aa-df1830d2c8d5

Asked 2026-10-15 (Framework): a dictation with no text box focused is lost;
put it on the clipboard. And a place in Handy to see and copy past dictations.

Found in Handy 0.9.8's source: both exist. `clipboard_handling =
copy_to_clipboard` writes the pasted text to the clipboard after the paste
(`clipboard.rs`). The History tab keeps `history_limit` dictations (was 5).
Its copy button copies the raw transcript, not the helper's cleaned text
(`HistorySettings.tsx` uses `transcription_text`); still true on Handy main.

Done: `configure_handy.py` sets and checks both (e88b55c). `--check` on the
Framework flags both as not yet applied.

Next: apply on the live Handy. Waiting on the user: restart Handy (5-10 s
gap) or flip the two settings in Handy's Advanced page. Then decide whether
History should show the cleaned text (needs a Handy fork; AGENTS.md says no
fork). The Spectre picks it up at its next pull and `configure_handy.py`.
