import "server-only";
import { readFile } from "node:fs/promises";
import { importPKCS8, SignJWT } from "jose";
import { config } from "./server-config";

export type Role = "student" | "admin";

// Mirrors scripts/mint_token.py: ES256, sub/role/iss/aud/iat/exp.
export async function mintDevToken(sub: string, role: Role): Promise<string> {
  const pem = await readFile(config.devPrivateKeyFile, "utf8");
  const key = await importPKCS8(pem, "ES256");
  return new SignJWT({ role })
    .setProtectedHeader({ alg: "ES256" })
    .setSubject(sub)
    .setIssuer(config.issuer)
    .setAudience(config.audience)
    .setIssuedAt()
    .setExpirationTime(`${config.tokenTtlSeconds}s`)
    .sign(key);
}
