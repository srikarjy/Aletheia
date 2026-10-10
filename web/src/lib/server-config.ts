import "server-only";

export const COOKIE_NAME = "aletheia_session";

export const config = {
  apiUrl: (process.env.ALETHEIA_API_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  issuer: process.env.AUTH_JWT_ISSUER ?? "aletheia-auth",
  audience: process.env.AUTH_JWT_AUDIENCE ?? "aletheia-api",
  // Dev login signs tokens with a private key held by this server. That is a stand-in
  // for a real identity provider and must never be switched on in production.
  devLoginEnabled:
    process.env.NODE_ENV !== "production" && process.env.DEV_LOGIN_ENABLED === "true",
  devPrivateKeyFile: process.env.DEV_LOGIN_PRIVATE_KEY_FILE ?? "../.auth/private.pem",
  tokenTtlSeconds: 900,
};
