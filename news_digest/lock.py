"""Optional passphrase lock for the public website.

With SITE_PASSPHRASE set, every page (and search.json) is published encrypted
with AES-GCM under a key derived from the passphrase (PBKDF2-SHA256). The
published page is a small unlock screen; after the passphrase is typed once,
the phone keeps the derived key (never the passphrase) and opens pages directly.
Without the passphrase, the published files reveal nothing but their size.
"""

from __future__ import annotations

import base64
import functools
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT = b"the-daily-brief/v1"  # fixed so one unlock works for every page
ITERATIONS = 250_000


def passphrase() -> str:
    return os.environ.get("SITE_PASSPHRASE", "").strip()


@functools.lru_cache(maxsize=2)
def _key(secret: str) -> bytes:
    return PBKDF2HMAC(hashes.SHA256(), 32, SALT, ITERATIONS).derive(secret.encode())


def _seal(data: bytes, secret: str) -> dict:
    iv = os.urandom(12)
    ct = AESGCM(_key(secret)).encrypt(iv, data, None)
    return {"iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(ct).decode()}


def lock_json(text: str, secret: str) -> str:
    return json.dumps({"locked": 1, **_seal(text.encode(), secret)})


def unlock_json(text: str, secret: str) -> str:
    """Inverse of lock_json (raises ValueError when the key is wrong)."""
    box = json.loads(text)
    try:
        return AESGCM(_key(secret)).decrypt(base64.b64decode(box["iv"]), base64.b64decode(box["ct"]), None).decode()
    except Exception as exc:
        raise ValueError("cannot decrypt: wrong SITE_PASSPHRASE?") from exc


def lock_html(html: str, secret: str) -> str:
    sealed = json.dumps(_seal(html.encode(), secret))
    return UNLOCK_PAGE.replace("__SEALED__", sealed).replace("__ITER__", str(ITERATIONS)).replace(
        "__SALT__", SALT.decode())


UNLOCK_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Brief">
<title>The Daily Brief</title>
<style>
  :root { --paper: #fff1e5; --ink: #1a1817; --muted: #66605c; --claret: #990f3d; --card: #fff8f1; --rule: #e0cdbc; }
  @media (prefers-color-scheme: dark) { :root { --paper: #111112; --ink: #f2eee9; --muted: #a39d97; --claret: #f0668f; --card: #19191b; --rule: #2c2b2b; } }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--paper); color: var(--ink);
         font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  form { width: min(340px, calc(100vw - 32px)); padding: 24px; border: 1px solid var(--rule); border-radius: 14px; background: var(--card); }
  h1 { margin: 0 0 6px; font: 700 1.6rem/1.1 Georgia, serif; } h1 span { color: var(--claret); }
  p { margin: 0 0 16px; color: var(--muted); font-size: .9rem; }
  input { width: 100%; box-sizing: border-box; padding: 12px; border: 1px solid var(--rule); border-radius: 10px; background: var(--paper);
          color: var(--ink); font-size: 1rem; }
  button { width: 100%; margin-top: 10px; padding: 12px; border: 0; border-radius: 10px; background: var(--claret); color: var(--paper);
           font-weight: 700; font-size: 1rem; }
  .err { min-height: 1.3em; margin: 8px 0 0; color: var(--claret); font-size: .85rem; }
</style></head>
<body>
<form id="f" hidden>
  <h1>The Daily Brief<span>.</span></h1>
  <p>Enter the passphrase. This phone will remember it.</p>
  <input id="p" type="password" autocomplete="current-password" placeholder="Passphrase" required>
  <button>Unlock</button>
  <div class="err" id="e" role="alert"></div>
</form>
<script>
(async () => {
  const S = __SEALED__;
  const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const open = async raw => {
    const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
    const html = new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(S.iv) }, key, b64(S.ct)));
    // Replace this page only once it has fully loaded: writing earlier would add the
    // brief to this page instead of replacing it (wrong viewport, desktop-width layout).
    if (document.readyState !== "complete") await new Promise(r => addEventListener("load", r, { once: true }));
    document.open(); document.write(html); document.close();
  };
  let saved = null;
  try { saved = localStorage.getItem("brief-key"); } catch (e) {}
  if (saved) { try { await open(b64(saved)); return; } catch (e) { try { localStorage.removeItem("brief-key"); } catch (x) {} } }
  const f = document.getElementById("f");
  f.hidden = false;
  document.getElementById("p").focus();
  f.addEventListener("submit", async ev => {
    ev.preventDefault();
    document.getElementById("e").textContent = "";
    const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(document.getElementById("p").value.trim()), "PBKDF2", false, ["deriveBits"]);
    const raw = new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: new TextEncoder().encode("__SALT__"), iterations: __ITER__ }, base, 256));
    try {
      await open(raw);
      try { localStorage.setItem("brief-key", btoa(String.fromCharCode(...raw))); } catch (e) {}
    } catch (e) { document.getElementById("e").textContent = "That passphrase doesn't match."; }
  });
})();
</script>
</body></html>
"""
