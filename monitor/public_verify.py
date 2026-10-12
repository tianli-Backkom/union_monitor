"""Public deployment verification against actual bytes (UDR-029).

After deploy, the pipeline must fetch every resource named in the candidate's
complete manifest and compare its actual **bytes** (hash and size) with the
expected fingerprint — never just a few manifest identity fields. Transient
fetch failures (503, network) are retried under a finite attempt/backoff budget
driven by an injectable clock; a permanent mismatch is never retried. Only a
fully matching run produces a receipt bound to the candidate identity and the
verification time that authorises baseline promotion.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

try:
    import urllib.request
except ImportError:  # pragma: no cover - urllib is stdlib
    urllib_request = None
else:
    urllib_request = urllib.request


class TransientFetchError(RuntimeError):
    """A fetch failure that may succeed on retry (503, network, timeout)."""


class PermanentFetchError(RuntimeError):
    """A fetch failure that retrying cannot fix (404, invalid resource)."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _default_fetch(timeout):
    def fetch(url):
        try:
            with urllib_request.urlopen(url, timeout=timeout) as response:
                if getattr(response, "status", 200) >= 500:
                    raise TransientFetchError(f"{url}: HTTP {response.status}")
                return response.read()
        except TransientFetchError:
            raise
        except Exception as exc:  # network/timeout/parse failures are retryable
            raise TransientFetchError(f"{url}: {exc!r}") from exc

    return fetch


def _resources_of(manifest):
    resources = manifest.get("resources") if isinstance(manifest, dict) else None
    if not isinstance(resources, dict) or not resources:
        raise ValueError("manifest carries no `resources` table to verify against")
    return resources


class PublicVerifier:
    """Fetch and byte-compare every manifest resource with a finite retry budget.

    ``clock`` returns a monotonic value; ``sleep`` pauses between retries; both
    are injectable so tests drive a virtual clock without waiting. ``fetch``
    returns bytes or raises ``TransientFetchError``.
    """

    def __init__(self, *, timeout=1.0, max_attempts=3, backoff=0.25,
                 clock=None, sleep=None, fetch=None):
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.clock = clock if clock is not None else time.monotonic
        self.sleep = sleep if sleep is not None else time.sleep
        self.fetch = fetch if fetch is not None else _default_fetch(timeout)
        self.requests = []

    def _fetch_retry(self, url):
        last = None
        for attempt in range(1, self.max_attempts + 1):
            self.requests.append({"url": url, "attempt": attempt, "at": self.clock()})
            try:
                return self.fetch(url)
            except TransientFetchError as exc:
                last = exc
                if attempt < self.max_attempts:
                    self.sleep(self.backoff)
        raise last

    def verify(self, base_url, manifest, *, verified_at=None):
        """Return the verification receipt; only a full match is ``verified``."""
        resources = _resources_of(manifest)
        base = base_url.rstrip("/")
        checked = []
        problems = []
        for path in sorted(resources):
            expected = resources[path]
            url = f"{base}/{path}"
            try:
                data = self._fetch_retry(url)
            except (TransientFetchError, PermanentFetchError) as exc:
                problems.append({"resource": path, "url": url, "expected": expected.get("sha256"),
                                 "actual": None, "reason": "fetch_failed", "detail": str(exc),
                                 "at": self.clock()})
                continue
            actual_hash = sha256_bytes(data)
            actual_size = len(data)
            entry = {"resource": path, "url": url, "sha256": actual_hash, "size": actual_size}
            if actual_hash != expected.get("sha256"):
                problems.append({"resource": path, "url": url, "expected": expected.get("sha256"),
                                 "actual": actual_hash, "reason": "sha256_mismatch", "at": self.clock()})
                continue
            if expected.get("size") is not None and actual_size != expected["size"]:
                problems.append({"resource": path, "url": url, "expected_size": expected.get("size"),
                                 "actual_size": actual_size, "reason": "size_mismatch", "at": self.clock()})
                continue
            checked.append(entry)
        receipt = {
            "verified": not problems,
            "release_id": manifest.get("release_id"),
            "run_id": manifest.get("run_id"),
            "code_sha": manifest.get("code_sha"),
            "cutoff_at": manifest.get("cutoff_at"),
            "resources_total": len(resources),
            "resources_checked": len(checked),
            "problems": problems,
            "requests": list(self.requests),
            "verified_at": verified_at or datetime.now(timezone.utc).isoformat(),
            "attempts_budget": self.max_attempts,
        }
        return receipt


def verify_public_resources(base_url, manifest, *, timeout=1.0, max_attempts=3, backoff=0.25,
                            clock=None, sleep=None, fetch=None, verified_at=None):
    """Convenience wrapper returning the receipt of a fresh verifier run."""
    verifier = PublicVerifier(timeout=timeout, max_attempts=max_attempts, backoff=backoff,
                              clock=clock, sleep=sleep, fetch=fetch)
    return verifier.verify(base_url, manifest, verified_at=verified_at)