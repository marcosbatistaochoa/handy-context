# Backburner

Shelved on purpose, each with the condition that takes it off the shelf.

- **Linux context capture (AT-SPI)** for when the Spectre runs Fedora.
  Shelved 2026-10-04 by Sherpa. Unshelve when: the Spectre's Fedora install
  is done (`ai-system` STATE.md item 2.1 marked done).
- **Screenshot context** (send a picture of the window to a vision model),
  for apps whose text the accessibility tree does not expose. Shelved
  2026-10-04 by Sherpa. Unshelve when: the user reports a wrong name in an
  app where `handy-context` logged empty context.
- **Email formatting by context** (the user, 2026-10-07). When the
  focused field is a new email draft (Gmail or Outlook in a browser, or
  the Outlook app), format the dictation as an email: greeting, paragraphs,
  sign-off, cleaned up. Detection would read the app, window title and the
  draft's accessibility tree, which `context.py` already captures. Unshelve
  when: Handy runs on the Framework (`STATE.md` Next 1 done) and the user
  says to start it.
- **Translate hotkey** (the user, 2026-10-07). A second push-to-talk key,
  Alt+T or similar, that has the model translate the dictation into another
  language: speak English, paste Spanish, say. Plain dictation never
  translates (fixed the same day: `modes.language()` catches a translated
  answer and retries in the spoken language). Open question: how the user
  picks the target language. The user's idea: holding Alt and pressing a
  key opens a small menu of languages to click. Check first that the key
  does not clash with Right Alt, which already starts dictation. Unshelve
  when: the user says to start it.

Edit Mode (shelved 2026-10-04) came off the shelf when the user asked for
it and was built 2026-10-07 (`plans/2026-10-07-dictation-edit.md`).
