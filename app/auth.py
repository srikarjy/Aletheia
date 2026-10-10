"""Authentication and role authorization (Phase 10a).

Model: Aletheia never sees a password. A separate issuer (today `scripts/mint_token.py`,
later the TypeScript frontend's server side) signs short-lived JWTs with an ES256 PRIVATE
key; this API holds only the PUBLIC key. Consequences worth being able to explain:

  - Compromising this API cannot mint tokens. With a shared HS256 secret it could.
  - The algorithm is pinned here and never read from the token. Reading `alg` from an
    attacker-controlled header is the root of both the `alg: none` and the
    "RS256 public key used as HS256 secret" attacks.
  - Every claim that matters is *required* (exp, iat, iss, aud, sub, role), and the
    lifetime is capped, so a buggy issuer cannot hand out immortal tokens.
  - Unconfigured means closed (503), never open. There is deliberately no "auth
    disabled" switch: a flag like that gets shipped to production.
  - Failures return one generic message. Why a token failed goes to the server log,
    not to the caller, so the endpoint is not an oracle for forging attempts.

Authentication (who are you?) is this file. Authorization (what may you touch?) is the
role dependencies below plus, in Phase 10b, per-user ownership of jobs and memories.
"""

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Pinned. Never derive from the token header.
ALGORITHMS = ["ES256"]
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "role"]
MAX_TOKEN_LIFETIME_SECONDS = 3600
CLOCK_SKEW_SECONDS = 10

DEFAULT_ISSUER = "aletheia-auth"
DEFAULT_AUDIENCE = "aletheia-api"

_bearer = HTTPBearer(auto_error=False)  # auto_error off: we own the error shape


class Role(StrEnum):
    student = "student"
    admin = "admin"


@dataclass(frozen=True)
class Principal:
    sub: str
    role: Role


class AuthNotConfigured(RuntimeError):
    pass


def _unauthorized(reason: str) -> HTTPException:
    logger.warning("auth rejected: %s", reason)
    return HTTPException(
        status_code=401,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache(maxsize=4)
def _parse_public_key(pem: str) -> ec.EllipticCurvePublicKey:
    key = load_pem_public_key(pem.encode())  # raises on a private key or garbage
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise AuthNotConfigured("AUTH_JWT_PUBLIC_KEY must be a P-256 (ES256) public key")
    return key


def _load_public_key() -> ec.EllipticCurvePublicKey:
    pem = os.environ.get("AUTH_JWT_PUBLIC_KEY", "").strip()
    path = os.environ.get("AUTH_JWT_PUBLIC_KEY_FILE", "").strip()
    if not pem and path:
        with open(path, encoding="utf-8") as fh:
            pem = fh.read()
    if not pem:
        raise AuthNotConfigured("neither AUTH_JWT_PUBLIC_KEY nor AUTH_JWT_PUBLIC_KEY_FILE is set")
    pem = pem.replace("\\n", "\n")  # env vars often carry PEMs with literal \n
    try:
        return _parse_public_key(pem)
    except AuthNotConfigured:
        raise
    except Exception as exc:  # unparsable, or a private key was pasted by mistake
        raise AuthNotConfigured(f"AUTH_JWT_PUBLIC_KEY is not a valid public key: {exc}") from exc


def verify_token(token: str) -> Principal:
    """Verify signature, pinned algorithm, issuer, audience, expiry and claims.
    Raises HTTPException(401) on any failure."""
    try:
        key = _load_public_key()
    except (AuthNotConfigured, OSError) as exc:
        logger.error("auth is not configured, refusing all protected requests: %s", exc)
        raise HTTPException(status_code=503, detail="Authentication is not configured") from exc

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=os.environ.get("AUTH_JWT_AUDIENCE", DEFAULT_AUDIENCE),
            issuer=os.environ.get("AUTH_JWT_ISSUER", DEFAULT_ISSUER),
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized(f"{type(exc).__name__}: {exc}") from exc

    if not isinstance(claims["exp"], (int, float)) or not isinstance(claims["iat"], (int, float)):
        raise _unauthorized("exp/iat are not numeric")
    if claims["exp"] - claims["iat"] > MAX_TOKEN_LIFETIME_SECONDS:
        raise _unauthorized("token lifetime exceeds the allowed maximum")

    sub = claims["sub"]
    if not isinstance(sub, str) or not sub.strip():
        raise _unauthorized("sub is not a non-empty string")
    try:
        role = Role(claims["role"])
    except ValueError:
        raise _unauthorized(f"unknown role {claims['role']!r}") from None

    return Principal(sub=sub, role=role)


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("missing or non-bearer Authorization header")
    return verify_token(credentials.credentials)


def require_role(*allowed: Role):
    """Dependency factory. Authorization is an allowlist of roles per route."""

    def dependency(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            logger.warning(
                "auth forbidden: sub=%s role=%s needs one of %s for %s %s",
                principal.sub, principal.role, [r.value for r in allowed],
                request.method, request.url.path,
            )
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return principal

    dependency.__name__ = f"require_{'_or_'.join(r.value for r in allowed)}"
    dependency.allowed_roles = allowed  # introspected by the route-audit test
    return dependency


require_user = require_role(Role.student, Role.admin)
require_admin = require_role(Role.admin)
