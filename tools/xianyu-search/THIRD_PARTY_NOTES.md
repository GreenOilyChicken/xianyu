# Third-party notes

This skill's code was written from scratch, but its design was informed by
public research on Xianyu's web APIs.  Thanks to:

- [yz68ac/goofish_spider](https://github.com/yz68ac/goofish_spider) (MIT)
  — the mtop signing scheme, search API payload shape, cookie/token handling,
  risk-control backoff strategy, and response field layout.
- [LENKIN233/xianyu-monitor-skill](https://github.com/LENKIN233/xianyu-monitor-skill)
  — Playwright login-state capture patterns and the safety model around
  credentials and risk control.

The mtop `sign = md5(token&t&appKey&data)` scheme itself is a public protocol
convention used across Alibaba H5 APIs.

No code from those projects is vendored here; no credentials, cookies, or
user data are included.
