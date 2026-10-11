"""Web Push notifications for the installed app (RFC 8030 / 8291 / 8292).

No push server is needed: each phone subscribes in the app (bell icon) and
shows a code. Paste the codes, one per line, into the repository variable
PUSH_SUBSCRIPTIONS. After each scheduled run, every subscriber gets one
notification per chosen tab that has news. The VAPID_PRIVATE_KEY secret signs
the messages; the app's public key is derived from it at build time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import struct
import time
from datetime import datetime
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

CODE_PREFIX = "brief1."
TTL = 20 * 3600  # drop the message if the phone stays offline until the next edition


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw_public(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def private_key(text: str | None = None) -> ec.EllipticCurvePrivateKey | None:
    """The VAPID key from VAPID_PRIVATE_KEY (base64url of the raw 32-byte P-256 scalar)."""
    text = (text if text is not None else os.environ.get("VAPID_PRIVATE_KEY", "")).strip()
    if not text:
        return None
    return ec.derive_private_key(int.from_bytes(unb64u(text), "big"), ec.SECP256R1())


def public_key_b64(key: ec.EllipticCurvePrivateKey) -> str:
    """applicationServerKey for PushManager.subscribe() in the page."""
    return b64u(_raw_public(key.public_key()))


def new_private_key() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return b64u(key.private_numbers().private_value.to_bytes(32, "big"))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def encrypt(payload: bytes, p256dh: str, auth: str, salt: bytes | None = None,
            sender: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """aes128gcm-encrypt a message for one subscription (RFC 8291)."""
    ua_public = unb64u(p256dh)
    sender = sender or ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(sender.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(unb64u(auth), shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # 0x02 = last record
    return salt + struct.pack("!IB", 4096, len(as_public)) + as_public + body


def _vapid_header(endpoint: str, key: ec.EllipticCurvePrivateKey, subject: str) -> str:
    parts = urlsplit(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64u(json.dumps({"aud": f"{parts.scheme}://{parts.netloc}",
                              "exp": int(time.time()) + 12 * 3600, "sub": subject}).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    jwt = f"{head}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={public_key_b64(key)}"


def send(sub: dict, message: dict, key: ec.EllipticCurvePrivateKey, subject: str) -> requests.Response:
    """Send one notification; returns the push service's response."""
    body = encrypt(json.dumps(message, ensure_ascii=False).encode(), sub["keys"]["p256dh"], sub["keys"]["auth"])
    headers = {
        "Authorization": _vapid_header(sub["endpoint"], key, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL),
        "Urgency": "normal",
    }
    # No Topic header: Apple's push service (iPhone) rejects some requests that carry one.
    # The notification's tag already replaces an older one for the same tab on the phone.
    return requests.post(sub["endpoint"], data=body, headers=headers, timeout=20)


def parse_codes(text: str) -> list[dict]:
    """Subscriptions from PUSH_SUBSCRIPTIONS: one app code (brief1.…) per line."""
    subs = []
    for line in (text or "").split():
        line = line.strip().strip(",")
        if not line.startswith(CODE_PREFIX):
            continue
        try:
            sub = json.loads(unb64u(line[len(CODE_PREFIX):]))
            if sub.get("endpoint", "").startswith("https://") and sub.get("keys"):
                subs.append(sub)
        except ValueError:
            log.warning("push: skipping a code that could not be read")
    return subs


def _clip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _label(s: dict) -> str:
    return f"{s.get('emoji', '')} {s.get('short') or s['title']}".strip()


def _weekly(digest: dict) -> list[dict]:
    """The week in review, announced once, on Saturday."""
    week = digest.get("weekly")
    if not week or datetime.fromisoformat(digest["date"]).weekday() != 5:
        return []
    body = (week.get("overview") or ["Your week in review is ready."])[0]
    return [{"title": "🗓️ The week in review", "body": _clip(body.replace("**", "")), "tag": "week",
             "url": "./#week", "icon": "icon-192.png"}]


def important_messages(digest: dict, tabs: list[str]) -> list[dict]:
    """Default mode: only tabs where something big happened (see alerts.py)."""
    out = []
    for s in digest["sections"]:
        if s["id"] in tabs and s.get("alerts"):
            out.append({"title": f"{_label(s)} · Important", "body": _clip(" · ".join(s["alerts"][:3])),
                        "tag": s["id"], "url": f"./#{s['id']}", "icon": f"icon-cat-{s['id']}.png"})
    return out + _weekly(digest)


def messages(digest: dict, tabs: list[str], mode: str = "important") -> list[dict]:
    """Notifications for one phone: important news only, or (mode "daily") every tab with news."""
    if mode != "daily":
        return important_messages(digest, tabs)
    from .__main__ import _lead  # the same headline the front page shows

    out = []
    if "today" in tabs and digest.get("top"):
        first = digest["top"][0]
        text = first["text"] if isinstance(first, dict) else str(first)
        out.append({"title": "☀️ Today's brief", "body": _clip(text), "tag": "today",
                    "url": "./#today", "icon": "icon-192.png"})
    for s in digest["sections"]:
        if s["id"] not in tabs or not s.get("new_count") or (s.get("briefing") or {}).get("quiet"):
            continue
        lead = _lead((s.get("briefing") or {}).get("summary"))
        head = lead["head"] if lead["head"] and not lead["head"].lower().startswith("nothing new") else ""
        if not head:
            fresh = [i for i in s["items"] if i["is_new"]]
            head = fresh[0]["title"] if fresh else ""
        if not head:
            continue
        if s.get("alerts"):
            head = s["alerts"][0]
        body = head + (f". {lead['body']}" if lead["body"] and head == lead["head"] else "")
        out.append({"title": f"{_label(s)} · {s['new_count']} new", "body": _clip(body), "tag": s["id"],
                    "url": f"./#{s['id']}", "icon": f"icon-cat-{s['id']}.png"})
    return out + _weekly(digest)


def notify_all(digest: dict, site_url: str) -> None:
    key = private_key()
    subs = parse_codes(os.environ.get("PUSH_SUBSCRIPTIONS", ""))
    if not key or not subs:
        log.info("push: VAPID_PRIVATE_KEY or PUSH_SUBSCRIPTIONS not set - no notifications")
        return
    subject = os.environ.get("PUSH_CONTACT") or site_url or "mailto:digest@example.invalid"
    for n, sub in enumerate(subs, 1):
        who = sub.get("name") or f"subscriber {n}"
        sent = 0
        for msg in messages(digest, sub.get("tabs") or ["today"], sub.get("mode", "important")):
            if site_url:
                msg = {**msg, "url": site_url + msg["url"][2:], "icon": site_url + msg["icon"]}
            try:
                res = send(sub, msg, key, subject)
            except requests.RequestException as exc:
                log.warning("push to %s failed: %s", who, exc)
                break
            status = res.status_code
            if status in (404, 410):
                log.warning("push: %s's subscription has expired; remove that line from "
                            "PUSH_SUBSCRIPTIONS and turn notifications on again in the app", who)
                break
            if status >= 400:
                # Push services explain rejections in the body, e.g. Apple's {"reason": "BadJwtToken"}.
                log.warning("push to %s (%s): HTTP %s %s", who, urlsplit(sub["endpoint"]).netloc,
                            status, res.text[:300].strip())
                continue
            sent += 1
        log.info("push: %d notification(s) sent to %s", sent, who)


if __name__ == "__main__":
    print("VAPID_PRIVATE_KEY (keep secret):", new_private_key())
