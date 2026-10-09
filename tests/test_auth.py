"""Phase 10a: authentication (is this token genuine?) and role authorization.

Structured as attacks, because a verifier that accepts good tokens proves nothing:
the property that matters is that every *bad* token is refused, for the right reason,
without telling the caller which check failed.
"""
import base64
import hashlib
import hmac
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from auth_helpers import TEST_PRIVATE_PEM, TEST_PUBLIC_PEM, _new_keypair, mint_test_token

GENERIC_401 = "Invalid or missing credentials"

# A route that needs only a valid user and touches no database or LLM:
# an unknown job id is a 404 *after* auth passes.
USER_PROBE = "/debate/jobs/00000000-0000-0000-0000-000000000000"
ADMIN_PROBE = "/cache/stats"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# --- 1. the happy path, so the attacks below mean something --------------------

def test_valid_student_token_reaches_the_handler(anon_client):
    r = anon_client.get(USER_PROBE, headers=bearer(mint_test_token("alice", "student")))
    assert r.status_code == 404  # authenticated, then "job not found"


def test_valid_admin_token_reaches_admin_route(anon_client):
    assert anon_client.get(ADMIN_PROBE, headers=bearer(mint_test_token("root", "admin"))).status_code == 200


# --- 2. missing / malformed credentials ---------------------------------------

@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": ""},
    {"Authorization": "Bearer"},
    {"Authorization": "Bearer "},
    {"Authorization": "Basic dXNlcjpwYXNz"},
    {"Authorization": "Token abc"},
    {"Authorization": "Bearer not.a.jwt"},
    {"Authorization": "Bearer " + "a" * 5000},
])
def test_missing_or_malformed_credentials_are_401(anon_client, headers):
    r = anon_client.get(USER_PROBE, headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC_401
    assert r.headers["www-authenticate"] == "Bearer"


def test_token_in_query_string_is_not_accepted(anon_client):
    token = mint_test_token()
    assert anon_client.get(f"{USER_PROBE}?access_token={token}").status_code == 401


# --- 3. forged and tampered tokens --------------------------------------------

def test_alg_none_is_rejected(anon_client):
    now = int(time.time())
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({
        "sub": "mallory", "role": "admin", "iss": "aletheia-auth", "aud": "aletheia-api",
        "iat": now, "exp": now + 600,
    }).encode())
    assert anon_client.get(ADMIN_PROBE, headers=bearer(f"{header}.{payload}.")).status_code == 401


def test_algorithm_confusion_hs256_signed_with_the_public_key_is_rejected(anon_client):
    """The classic attack: the public key is, by definition, public. If the server
    trusts the token's `alg` header, an attacker signs HS256 using that public key
    as the HMAC secret and the server 'verifies' it with the same bytes."""
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({
        "sub": "mallory", "role": "admin", "iss": "aletheia-auth", "aud": "aletheia-api",
        "iat": now, "exp": now + 600,
    }).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(TEST_PUBLIC_PEM.encode(), signing_input, hashlib.sha256).digest()
    forged = f"{header}.{payload}.{_b64(sig)}"
    assert anon_client.get(ADMIN_PROBE, headers=bearer(forged)).status_code == 401


def test_token_signed_by_a_different_key_is_rejected(anon_client):
    other_private, _ = _new_keypair()
    token = mint_test_token("mallory", "admin", key=other_private)
    assert anon_client.get(ADMIN_PROBE, headers=bearer(token)).status_code == 401


def test_tampered_payload_is_rejected(anon_client):
    """Promote yourself: swap the payload to role=admin, keep the student signature."""
    head, _, sig = mint_test_token("alice", "student").split(".")
    now = int(time.time())
    evil = _b64(json.dumps({
        "sub": "alice", "role": "admin", "iss": "aletheia-auth", "aud": "aletheia-api",
        "iat": now, "exp": now + 600,
    }).encode())
    assert anon_client.get(ADMIN_PROBE, headers=bearer(f"{head}.{evil}.{sig}")).status_code == 401


# --- 4. claims: every one that matters is enforced -----------------------------

now = int(time.time())

BAD_CLAIMS = {
    "expired": {"exp": now - 3600, "iat": now - 7200},
    "wrong_audience": {"aud": "some-other-service"},
    "wrong_issuer": {"iss": "evil-issuer"},
    "missing_exp": {"exp": None},
    "missing_iat": {"iat": None},
    "missing_iss": {"iss": None},
    "missing_aud": {"aud": None},
    "missing_sub": {"sub": None},
    "missing_role": {"role": None},
    "empty_sub": {"sub": ""},
    "unknown_role": {"role": "superuser"},
    "role_wrong_case": {"role": "Admin"},
    "role_is_list": {"role": ["admin"]},
    "not_yet_valid": {"nbf": now + 3600},
    "lifetime_too_long": {"iat": now, "exp": now + 7 * 24 * 3600},
}


@pytest.mark.parametrize("name", BAD_CLAIMS)
def test_bad_claims_are_rejected_with_a_generic_401(anon_client, name):
    token = mint_test_token("alice", "admin", overrides=BAD_CLAIMS[name])
    r = anon_client.get(ADMIN_PROBE, headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC_401  # never says *which* check failed


def test_small_clock_skew_is_tolerated(anon_client):
    token = mint_test_token(overrides={"iat": now + 5, "exp": now + 905})
    assert anon_client.get(USER_PROBE, headers=bearer(token)).status_code == 404


# --- 5. authorization: roles ---------------------------------------------------

def test_student_is_forbidden_from_admin_routes(anon_client):
    r = anon_client.get(ADMIN_PROBE, headers=bearer(mint_test_token("alice", "student")))
    assert r.status_code == 403
    assert r.json()["detail"] == "Insufficient permissions"


def test_401_and_403_are_distinct(anon_client):
    """401 = we do not know who you are; 403 = we know, and the answer is no."""
    assert anon_client.get(ADMIN_PROBE).status_code == 401
    assert anon_client.get(ADMIN_PROBE, headers=bearer(mint_test_token(role="student"))).status_code == 403


# (method, path) -> roles allowed. This table IS the authorization policy; changing it
# should be a deliberate edit to this file, visible in review.
POLICY = {
    ("POST", "/debate"): {"student", "admin"},
    ("POST", "/debate/async"): {"student", "admin"},
    ("GET", "/debate/jobs/{job_id}"): {"student", "admin"},
    ("GET", "/memory/research/{debate_id}"): {"student", "admin"},
    ("POST", "/debate/multi-agent"): {"admin"},
    ("GET", "/debate/jobs"): {"student", "admin"},  # scoped to the caller's own data (Phase 10b)
    ("DELETE", "/debate/jobs/{job_id}"): {"student", "admin"},  # scoped to the caller's own data (Phase 10b)
    ("GET", "/memory/research"): {"student", "admin"},  # scoped to the caller's own data (Phase 10b)
    ("DELETE", "/memory/research/{debate_id}"): {"student", "admin"},  # scoped to the caller's own data (Phase 10b)
    ("POST", "/cache/clear"): {"admin"},
    ("POST", "/cache/embeddings/clear"): {"admin"},
    ("GET", "/cache/stats"): {"admin"},
    ("POST", "/batch/debate"): {"admin"},
    ("GET", "/batch/debate/{batch_id}"): {"admin"},
    ("POST", "/batch/eval/run"): {"admin"},
    ("GET", "/batch/eval/claims"): {"admin"},
}

# Operations that are intentionally open. FastAPI's own /docs and /openapi.json and the
# static-frontend catch-all are not in the OpenAPI schema; they are public by design
# (revisit /docs before a public deploy).
PUBLIC = {("GET", "/health")}


def _served_operations() -> set[tuple[str, str]]:
    """Every (method, path) the app actually serves, from the OpenAPI schema.

    Deliberately NOT app.routes: FastAPI >= 0.139 stores included routers as an opaque
    _IncludedRouter, so walking app.routes silently skips the whole /batch router.
    The OpenAPI schema is the public contract and sees everything."""
    from app.main import app
    app.openapi_schema = None  # never reuse a stale cached schema
    spec = app.openapi()
    return {
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }


def test_route_audit_every_route_is_in_the_policy_or_explicitly_public():
    """Default-deny, enforced by a test: a route added tomorrow without a decision
    about who may call it fails here instead of shipping open."""
    served = _served_operations()
    known = set(POLICY) | PUBLIC
    unreviewed = sorted(served - known)
    stale = sorted(known - served)
    assert not unreviewed, f"routes with no authorization decision (add to POLICY or PUBLIC): {unreviewed}"
    assert not stale, f"POLICY/PUBLIC lists routes that no longer exist: {stale}"


def _url(path: str) -> str:
    return path.replace("{job_id}", "x").replace("{debate_id}", "x").replace("{batch_id}", "x")


def test_every_gated_route_is_401_without_a_token(anon_client):
    """Behavioural twin of the audit: actually call each route with no credentials."""
    for (method, path) in POLICY:
        url = _url(path)
        r = anon_client.request(method, url, json={"claim": "Glucosamine reduces pain"} if method == "POST" else None)
        assert r.status_code == 401, f"{method} {path} returned {r.status_code} without credentials"


def test_student_is_403_on_every_admin_only_route(anon_client):
    headers = bearer(mint_test_token("alice", "student"))
    for (method, path), roles in POLICY.items():
        if roles != {"admin"}:
            continue
        url = _url(path)
        r = anon_client.request(method, url, headers=headers, json={"claims": ["Glucosamine reduces pain"]} if method == "POST" else None)
        assert r.status_code == 403, f"{method} {path} returned {r.status_code} for a student"


# --- 6. fail closed ------------------------------------------------------------

def test_unconfigured_auth_fails_closed_not_open(anon_client, monkeypatch):
    monkeypatch.delenv("AUTH_JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("AUTH_JWT_PUBLIC_KEY_FILE", raising=False)
    r = anon_client.get(USER_PROBE, headers=bearer(mint_test_token()))
    assert r.status_code == 503
    assert anon_client.get("/health").status_code == 200  # liveness stays independent of auth


def test_a_private_key_in_the_public_key_slot_fails_closed(anon_client, monkeypatch):
    monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", TEST_PRIVATE_PEM)
    assert anon_client.get(USER_PROBE, headers=bearer(mint_test_token())).status_code == 503


def test_wrong_curve_public_key_fails_closed(anon_client, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    p384 = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", p384)
    assert anon_client.get(USER_PROBE, headers=bearer(mint_test_token())).status_code == 503


def test_public_key_may_be_supplied_with_escaped_newlines(anon_client, monkeypatch):
    monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", TEST_PUBLIC_PEM.strip().replace("\n", "\\n"))
    assert anon_client.get(USER_PROBE, headers=bearer(mint_test_token())).status_code == 404


def test_rotating_to_a_new_public_key_invalidates_old_tokens(anon_client, monkeypatch):
    old_token = mint_test_token()
    _, new_public = _new_keypair()
    monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", new_public)
    assert anon_client.get(USER_PROBE, headers=bearer(old_token)).status_code == 401


def test_student_is_let_through_user_level_routes(anon_client):
    """The other half of the policy: user routes must not be over-locked. An empty
    body makes the handler stop at validation (422) without calling an LLM, so
    reaching 422/404 proves the role gate admitted the student."""
    headers = bearer(mint_test_token("alice", "student"))
    for (method, path), roles in POLICY.items():
        if roles != {"student", "admin"}:
            continue
        r = anon_client.request(method, _url(path), headers=headers, json={} if method == "POST" else None)
        assert r.status_code not in (401, 403), f"{method} {path} wrongly refused a student ({r.status_code})"
