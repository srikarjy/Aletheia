import createClient from "openapi-fetch";
import type { components, paths } from "./api-schema";

// Typed client over the generated OpenAPI schema. It talks to our own origin; the BFF
// proxy adds the credentials, so no token handling exists in browser code.
export const api = createClient<paths>({ baseUrl: "/api/aletheia" });

export type Job = components["schemas"]["JobStatusResponse"];
export type DebateResult = components["schemas"]["DebateResponse"];
