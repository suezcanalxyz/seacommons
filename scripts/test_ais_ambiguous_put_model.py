"""Model-level negative controls for ambiguous S3-compatible archive writes.

This is NOT an integration test against R2 or canonical TrackStore.prune.
Run: python -m unittest discover -s scripts -p 'test_ais_ambiguous_put_model.py'
"""
import hashlib
import unittest


class PreconditionFailed(Exception):
    pass


class InMemoryObjectStore:
    def __init__(self):
        self.objects = {}

    def put_if_absent(self, key, payload, *, lose_response=False):
        if key in self.objects:
            raise PreconditionFailed(key)
        self.objects[key] = payload
        if lose_response:
            raise TimeoutError("response lost after server commit")

    def get(self, key):
        return self.objects[key]


def ensure_archive(store, key, payload):
    """Resolve ambiguous PUT by readback; never overwrite a different object."""
    digest = hashlib.sha256(payload).digest()
    try:
        store.put_if_absent(key, payload)
    except (TimeoutError, PreconditionFailed):
        try:
            actual = store.get(key)
        except KeyError:
            raise RuntimeError("archive state unresolved; prohibit deletion")
        if hashlib.sha256(actual).digest() != digest or actual != payload:
            raise RuntimeError("archive conflict; prohibit deletion")
    actual = store.get(key)
    if actual != payload:
        raise RuntimeError("archive verification failed; prohibit deletion")
    return True


class AmbiguousPutModelTests(unittest.TestCase):
    def test_same_bytes_after_existing_object(self):
        store = InMemoryObjectStore()
        store.put_if_absent("ais/one", b"snapshot")
        self.assertTrue(ensure_archive(store, "ais/one", b"snapshot"))

    def test_conflicting_existing_object_must_not_overwrite(self):
        store = InMemoryObjectStore()
        store.put_if_absent("ais/one", b"other")
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            ensure_archive(store, "ais/one", b"snapshot")
        self.assertEqual(store.get("ais/one"), b"other")

    def test_missing_readback_after_timeout_is_not_success(self):
        class UnresolvedStore(InMemoryObjectStore):
            def put_if_absent(self, key, payload):
                raise TimeoutError("ambiguous")
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            ensure_archive(UnresolvedStore(), "ais/one", b"snapshot")

    def test_lost_response_with_matching_readback(self):
        class LostResponseStore(InMemoryObjectStore):
            def put_if_absent(self, key, payload):
                return super().put_if_absent(key, payload, lose_response=True)
        store = LostResponseStore()
        self.assertTrue(ensure_archive(store, "ais/one", b"snapshot"))


if __name__ == "__main__":
    unittest.main()
