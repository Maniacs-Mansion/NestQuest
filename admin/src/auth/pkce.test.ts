import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  base64UrlEncode,
  computeCodeChallenge,
  generateCodeVerifier,
  generateState,
  isLikelyValidVerifier,
} from "./pkce";

describe("PKCE helpers", () => {
  it("base64UrlEncode has no padding and url-safe characters", () => {
    // bytes chosen to force "+" and "/" and padding in plain base64
    const bytes = new Uint8Array([0xfb, 0xff, 0xbf, 0xff]);
    const encoded = base64UrlEncode(bytes);
    expect(encoded).not.toMatch(/[+/=]/);
  });

  it("computes the RFC 7636 appendix-B S256 vector", async () => {
    const verifier =
      "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    const challenge = await computeCodeChallenge(verifier);
    expect(challenge).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  });

  it("generates verifiers with valid charset and length", () => {
    for (let i = 0; i < 20; i++) {
      const verifier = generateCodeVerifier();
      expect(isLikelyValidVerifier(verifier)).toBe(true);
    }
  });

  it("rejects verifiers outside 43-128 chars or with reserved chars", () => {
    expect(isLikelyValidVerifier("short")).toBe(false);
    expect(isLikelyValidVerifier("a".repeat(129))).toBe(false);
    expect(isLikelyValidVerifier("a".repeat(43) + "+")).toBe(false);
  });

  it("generates distinct random states", () => {
    expect(generateState()).not.toBe(generateState());
  });
});
