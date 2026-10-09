"""Token issuer for Aletheia (Phase 10a). The API only VERIFIES tokens; this is the
other half of the system, and the only place the private key is used.

  # 1. once: create an ES256 keypair under .auth/ (gitignored)
  poetry run python scripts/mint_token.py gen-keys

  # 2. mint a short-lived token for a person
  poetry run python scripts/mint_token.py mint --sub alice@bu.edu --role student
  poetry run python scripts/mint_token.py mint --sub me --role admin --ttl 600

  # 3. use it
  curl -H "Authorization: Bearer $TOKEN" localhost:8000/debate -d '{"claim": "..."}'

Invite-only by construction: nobody can get a token without access to the private
key, so "inviting" a student means running `mint` for them. Later the TypeScript
frontend's server side takes over this job; the API will not need to change.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DEFAULT_DIR = Path(".auth")
MAX_TTL = 3600  # must not exceed app.auth.MAX_TOKEN_LIFETIME_SECONDS


def gen_keys(directory: Path) -> int:
    directory.mkdir(mode=0o700, exist_ok=True)
    private_path, public_path = directory / "private.pem", directory / "public.pem"
    if private_path.exists():
        print(f"refusing to overwrite {private_path} (delete it first if you really mean to rotate)", file=sys.stderr)
        return 1
    key = ec.generate_private_key(ec.SECP256R1())
    # Create with 0600 from the start; chmod-after leaves a window where it is world-readable.
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ))
    public_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ))
    print(f"private key: {private_path}  (secret -- keep it with the issuer only)")
    print(f"public key:  {public_path}   (set AUTH_JWT_PUBLIC_KEY_FILE to this path for the API)")
    return 0


def mint(args) -> int:
    if not 1 <= args.ttl <= MAX_TTL:
        print(f"--ttl must be between 1 and {MAX_TTL} seconds", file=sys.stderr)
        return 1
    private_path = Path(args.key)
    if not private_path.exists():
        print(f"no private key at {private_path}; run gen-keys first", file=sys.stderr)
        return 1
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": args.sub, "role": args.role,
            "iss": os.environ.get("AUTH_JWT_ISSUER", "aletheia-auth"),
            "aud": os.environ.get("AUTH_JWT_AUDIENCE", "aletheia-api"),
            "iat": now, "exp": now + args.ttl,
        },
        private_path.read_text(),
        algorithm="ES256",
    )
    print(token)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen-keys", help="create an ES256 keypair")
    g.add_argument("--dir", default=str(DEFAULT_DIR))
    m = sub.add_parser("mint", help="issue a short-lived token")
    m.add_argument("--sub", required=True, help="who the token is for (e.g. an email)")
    m.add_argument("--role", choices=["student", "admin"], required=True)
    m.add_argument("--ttl", type=int, default=900, help=f"lifetime in seconds (default 900, max {MAX_TTL})")
    m.add_argument("--key", default=str(DEFAULT_DIR / "private.pem"))
    args = parser.parse_args()
    return gen_keys(Path(args.dir)) if args.cmd == "gen-keys" else mint(args)


if __name__ == "__main__":
    sys.exit(main())
