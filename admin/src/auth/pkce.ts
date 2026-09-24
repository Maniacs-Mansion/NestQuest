/**
 * PKCE (RFC 7636) helpers for a public SPA client.
 *
 * Uses the Web Crypto API, which requires a SECURE CONTEXT: the app must be
 * served over https or http://localhost, otherwise crypto.subtle is
 * unavailable and login cannot work.
 */

const VERIFIER_CHARSET =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";

/** base64url-encode bytes with NO padding. */
export function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomBase64Url(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

/**
 * Random code_verifier: 43-128 chars, unreserved charset only.
 * 32 random bytes -> 43 base64url chars, which is the minimum allowed length.
 */
export function generateCodeVerifier(): string {
  return randomBase64Url(32);
}

/** S256 code_challenge = base64url(SHA-256(verifier)), no padding. */
export async function computeCodeChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  return base64UrlEncode(new Uint8Array(digest));
}

/** Random opaque state value for CSRF protection. */
export function generateState(): string {
  return randomBase64Url(16);
}

export function isLikelyValidVerifier(verifier: string): boolean {
  return (
    verifier.length >= 43 &&
    verifier.length <= 128 &&
    [...verifier].every((char) => VERIFIER_CHARSET.includes(char))
  );
}
