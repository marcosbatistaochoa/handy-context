# Security

The helper reads text from your screen and can type into the active window,
so a bug here can matter. If you find one, open a private report through
this repository's **Security** tab ("Report a vulnerability") rather than a
public issue.

What the helper does to limit its reach:

- It listens on `127.0.0.1` only.
- It refuses any request that carries an `Origin` header or a `Host` other
  than `127.0.0.1`, `localhost` or `::1`, so a web page open in your browser
  cannot make it read your screen, even through DNS rebinding.
- It sends screen text only to the model URL in your `.env`, and logs no
  screen text unless you set `HC_LOG_CONTEXT=1`.

The review done before the first public release is in
`docs/security-review.md`.
