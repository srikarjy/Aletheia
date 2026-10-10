"""Auth test helpers: ONE throwaway ES256 keypair per test session.

Lives in its own module, not conftest.py, on purpose: pytest loads conftest.py under
the name `conftest`, and importing it again as `tests.conftest` would execute it a
second time, generating a second keypair and overwriting AUTH_JWT_PUBLIC_KEY so that
every token signed with the first key fails. One module, one keypair.

The API only ever sees the public half (AUTH_JWT_PUBLIC_KEY); the private half stays
in this process, exactly like the real issuer. Nothing here is a secret.
"""
import os

import time as _time

import jwt as _jwt
from cryptography.hazmat.primitives import serialization as _ser
from cryptography.hazmat.primitives.asymmetric import ec as _ec


def _new_keypair():
    private = _ec.generate_private_key(_ec.SECP256R1())
    private_pem = private.private_bytes(
        _ser.Encoding.PEM, _ser.PrivateFormat.PKCS8, _ser.NoEncryption()
    ).decode()
    public_pem = private.public_key().public_bytes(
        _ser.Encoding.PEM, _ser.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private_pem, public_pem


TEST_PRIVATE_PEM, TEST_PUBLIC_PEM = _new_keypair()
os.environ["AUTH_JWT_PUBLIC_KEY"] = TEST_PUBLIC_PEM


def mint_test_token(sub="user-1", role="student", *, key=None, algorithm="ES256", overrides=None):
    """Mint a token the API should accept; pass `overrides` (a dict) to break one
    property. An override value of None removes that claim entirely."""
    now = int(_time.time())
    claims = {
        "sub": sub, "role": role, "iss": "aletheia-auth", "aud": "aletheia-api",
        "iat": now, "exp": now + 900,
    }
    claims.update(overrides or {})
    claims = {k: v for k, v in claims.items() if v is not None}
    return _jwt.encode(claims, key or TEST_PRIVATE_PEM, algorithm=algorithm)
