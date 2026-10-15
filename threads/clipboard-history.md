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

Applied on the Framework 2026-10-15: Handy force-stopped, none left,
`configure_handy.py` run, Handy restarted; one `handy.exe`, `--check` OK
after the restart.

The user chose to keep History as it is (raw text). No fork.

Next: the Spectre picks it up at its next pull and `configure_handy.py`.
Otherwise closed.
