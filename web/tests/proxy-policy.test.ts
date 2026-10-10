import { describe, expect, it } from "vitest";
import { isAllowedPath, isSameOrigin } from "../src/lib/proxy-policy";

describe("isAllowedPath", () => {
  it("allows the user-facing areas", () => {
    expect(isAllowedPath(["debate", "async"])).toBe(true);
    expect(isAllowedPath(["debate", "jobs", "abc"])).toBe(true);
    expect(isAllowedPath(["memory", "research"])).toBe(true);
    expect(isAllowedPath(["health"])).toBe(true);
  });
  it("refuses admin and unknown areas (fails closed)", () => {
    expect(isAllowedPath(["cache", "clear"])).toBe(false);
    expect(isAllowedPath(["batch", "debate"])).toBe(false);
    expect(isAllowedPath(["debate", "multi-agent"])).toBe(false);
    expect(isAllowedPath(["openapi.json"])).toBe(false);
    expect(isAllowedPath([])).toBe(false);
  });
  it("refuses path traversal and separators in a segment", () => {
    expect(isAllowedPath(["debate", "..", "cache", "clear"])).toBe(false);
    expect(isAllowedPath(["debate", ".", "jobs"])).toBe(false);
    expect(isAllowedPath(["debate", "a/b"])).toBe(false);
    expect(isAllowedPath(["debate", "a\\b"])).toBe(false);
    expect(isAllowedPath(["debate", ""])).toBe(false);
  });
});

describe("isSameOrigin", () => {
  it("lets safe methods through without an Origin", () => {
    expect(isSameOrigin("GET", null, "localhost:3000")).toBe(true);
  });
  it("requires a matching Origin for state-changing methods", () => {
    expect(isSameOrigin("POST", "http://localhost:3000", "localhost:3000")).toBe(true);
    expect(isSameOrigin("POST", "http://evil.test", "localhost:3000")).toBe(false);
    expect(isSameOrigin("DELETE", null, "localhost:3000")).toBe(false);
    expect(isSameOrigin("POST", "not a url", "localhost:3000")).toBe(false);
  });
});
