import pytest

from procureai.infrastructure.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from procureai.infrastructure.storage.local import LocalFileStorage
from procureai.rag.embeddings.hashing import HashingEmbedder
from procureai.shared.errors import AuthenticationError, ProcessingError


def test_password_hashing():
    h = hash_password("secret-pass")
    assert h != "secret-pass" and verify_password("secret-pass", h) and not verify_password("other", h)
    assert not verify_password("x", "garbage")


def test_jwt_roundtrip_and_tamper(env):
    token, _ = create_access_token("u1", "admin")
    assert decode_access_token(token)["sub"] == "u1"
    with pytest.raises(AuthenticationError):
        decode_access_token(token + "x")


def test_storage_uses_generated_keys_and_blocks_traversal(tmp_path):
    st = LocalFileStorage(tmp_path / "s")
    key, sha = st.save(b"abc", ".pdf")
    assert key.endswith(".pdf") and len(sha) == 64 and st.read(key) == b"abc"
    with pytest.raises(ProcessingError):
        st.path_for("../../etc/passwd")
    st.delete(key)


def test_embedder_deterministic_and_normalised():
    e = HashingEmbedder(128)
    a, b = e.embed(["minimum warranty three years"]), e.embed(["minimum warranty three years"])
    assert a == b and abs(sum(x * x for x in a[0]) - 1) < 1e-6
