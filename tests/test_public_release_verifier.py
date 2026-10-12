"""UDR-029: public deployment verification against actual resource bytes.

The public verifier fetches every resource in the candidate's complete manifest
and byte-compares it, retrying transient failures under a finite budget driven
by a virtual clock. Byte/path/size tampering names the resource; persistent
unavailability exhausts the budget without ever marking the release verified.
"""
import hashlib
import unittest

from monitor.public_verify import (PermanentFetchError, PublicVerifier,
                                   TransientFetchError, verify_public_resources)


def sha(data):
    return hashlib.sha256(data).hexdigest()


TRITON_PAYLOAD = b'{"batches":[]}'
QUALIFICATION = b'{"schema_version":1,"batches":[]}'
INDEX = b"<!doctype html><html></html>"


def candidate(resources=None, release_id="rel-1"):
    manifest = {
        "release_id": release_id,
        "run_id": "run-1",
        "code_sha": "0" * 40,
        "cutoff_at": "2026-10-10T00:00:00Z",
        "projects": {"triton": {"data_mode": "fresh", "snapshot_sha256": sha(TRITON_PAYLOAD)}},
    }
    manifest["resources"] = resources or {
        "data/triton.json": {"sha256": sha(TRITON_PAYLOAD), "size": len(TRITON_PAYLOAD), "project": "triton"},
        "data/triton-qualifications-v1.json": {"sha256": sha(QUALIFICATION), "size": len(QUALIFICATION), "project": "triton"},
        "index.html": {"sha256": sha(INDEX), "size": len(INDEX), "project": None},
    }
    return manifest


class FakeTransport:
    def __init__(self, responses, transient=None, permanent=None):
        self.responses = responses
        self.transient = transient or {}
        self.permanent = permanent or {}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        remaining = self.transient.get(url, 0)
        if remaining:
            self.transient[url] = remaining - 1
            raise TransientFetchError(f"{url}: HTTP 503")
        if url in self.permanent:
            raise PermanentFetchError(self.permanent[url])
        if url in self.responses:
            return self.responses[url]
        raise PermanentFetchError(f"{url}: 404")


def responses():
    return {
        "https://site.example/data/triton.json": TRITON_PAYLOAD,
        "https://site.example/data/triton-qualifications-v1.json": QUALIFICATION,
        "https://site.example/index.html": INDEX,
    }


class PublicVerifierTests(unittest.TestCase):
    def receipt(self, manifest, transport, **kwargs):
        state = [0.0]
        sleeps = []
        clock = lambda: state[0]
        def sleep(seconds):
            sleeps.append(seconds)
            state[0] += seconds
        receipt = verify_public_resources(
            "https://site.example", manifest, clock=clock, sleep=sleep,
            fetch=transport, verified_at="2026-10-10T01:00:00Z", **kwargs,
        )
        return receipt, sleeps

    def test_tc01_transient_503_recovers_within_budget(self):
        transport = FakeTransport(responses(), transient={"https://site.example/index.html": 1})
        receipt, sleeps = self.receipt(candidate(), transport)
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["resources_checked"], 3)
        self.assertEqual(receipt["problems"], [])
        # The faulted resource needed exactly two requests.
        index_attempts = [r for r in receipt["requests"] if r["url"].endswith("index.html")]
        self.assertEqual(len(index_attempts), 2)
        self.assertEqual(sleeps, [0.25])

    def test_tc01_receipt_is_bound_to_candidate_and_time(self):
        transport = FakeTransport(responses())
        receipt, _ = self.receipt(candidate(release_id="rel-9"), transport)
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["release_id"], "rel-9")
        self.assertEqual(receipt["code_sha"], "0" * 40)
        self.assertEqual(receipt["verified_at"], "2026-10-10T01:00:00Z")
        self.assertEqual(receipt["resources_total"], 3)

    def test_tc02_byte_tampering_names_the_resource(self):
        transport = FakeTransport(responses())
        tampered = dict(responses())
        tampered["https://site.example/data/triton.json"] = b'{"batches":[1]}'
        receipt, _ = self.receipt(candidate(), FakeTransport(tampered))
        self.assertFalse(receipt["verified"])
        self.assertEqual(len(receipt["problems"]), 1)
        self.assertEqual(receipt["problems"][0]["resource"], "data/triton.json")
        self.assertEqual(receipt["problems"][0]["reason"], "sha256_mismatch")
        self.assertIn("actual", receipt["problems"][0])

    def test_tc02_missing_resource_is_named_not_retried(self):
        transport = FakeTransport(responses(), transient={"https://site.example/data/triton.json": 10})
        receipt, _ = self.receipt(candidate(), transport)
        self.assertFalse(receipt["verified"])
        problem = next(p for p in receipt["problems"] if p["resource"] == "data/triton.json")
        self.assertEqual(problem["reason"], "fetch_failed")
        attempts = [r for r in receipt["requests"] if r["url"].endswith("triton.json")]
        self.assertEqual(len(attempts), 3)  # budget exhausted, never more
        self.assertEqual(receipt["attempts_budget"], 3)

    def test_tc02_persistent_503_never_exceeds_budget(self):
        transport = FakeTransport(responses(), transient=self._always("https://site.example/index.html"))
        receipt, sleeps = self.receipt(candidate(), transport)
        self.assertFalse(receipt["verified"])
        self.assertEqual(receipt["resources_checked"], 2)
        index_attempts = [r for r in receipt["requests"] if r["url"].endswith("index.html")]
        self.assertEqual(len(index_attempts), 3)
        self.assertEqual(sleeps, [0.25, 0.25])  # two backoffs, bounded

    def test_tc02_size_mismatch_is_flagged(self):
        good = candidate()
        good["resources"]["data/triton.json"]["size"] = len(TRITON_PAYLOAD) + 5
        transport = FakeTransport(responses())
        receipt, _ = self.receipt(good, transport)
        self.assertFalse(receipt["verified"])
        problem = next(p for p in receipt["problems"] if p["resource"] == "data/triton.json")
        self.assertEqual(problem["reason"], "size_mismatch")

    def test_manifest_without_resources_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_public_resources("https://site.example", {"release_id": "rel-1"})

    @staticmethod
    def _always(url):
        # A dict that always reports a remaining transient failure.
        class Always:
            def get(self, key, default=0):
                return 1 if key == url else default
            def __setitem__(self, key, value):
                pass
        return Always()


class PublicVerifierClassTests(unittest.TestCase):
    def test_verifier_records_every_request(self):
        verifier = PublicVerifier(fetch=FakeTransport(responses()))
        manifest = candidate()
        verifier.verify("https://site.example", manifest, verified_at="2026-10-10T01:00:00Z")
        self.assertEqual(len(verifier.requests), 3)


if __name__ == "__main__":
    unittest.main()