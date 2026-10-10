"use strict";

(() => {
  const button = document.querySelector("#passkey-login");
  const error = document.querySelector("#passkey-error");
  if (!button || !error) return;

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Waiting for passkey…";
    error.hidden = true;
    try {
      if (!window.PublicKeyCredential || !navigator.credentials?.get) {
        throw new Error("This browser cannot unlock passkeys. Use an up-to-date iOS Safari or Android Chrome.");
      }
      const optionsResponse = await fetch("/api/v1/passkeys/login/options", {
        method: "POST", credentials: "same-origin", headers: { "X-Hutch-Request": "1" },
      });
      const options = await optionsResponse.json().catch(() => ({}));
      if (!optionsResponse.ok) throw new Error(options.detail || "Could not start passkey sign-in.");
      const challengeId = options.challenge_id;
      delete options.challenge_id;
      options.challenge = fromBase64url(options.challenge);
      if (options.allowCredentials) {
        options.allowCredentials = options.allowCredentials.map((item) => ({ ...item, id: fromBase64url(item.id) }));
      }
      const credential = await navigator.credentials.get({ publicKey: options });
      const verifyResponse = await fetch("/api/v1/passkeys/login/verify", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Hutch-Request": "1" },
        body: JSON.stringify({ challenge_id: challengeId, credential: serializeAuthentication(credential) }),
      });
      const result = await verifyResponse.json().catch(() => ({}));
      if (!verifyResponse.ok) throw new Error(result.detail || "Passkey sign-in failed. Try again.");
      window.location.replace("/");
    } catch (cause) {
      error.textContent = cause.name === "NotAllowedError"
        ? "Passkey sign-in was cancelled or timed out. Try again."
        : cause.message || "Passkey sign-in failed. Try again.";
      error.hidden = false;
      button.focus();
    } finally {
      button.disabled = false;
      button.textContent = "Unlock with passkey";
    }
  });

  function fromBase64url(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
    return Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
  }
  function toBase64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }
  function serializeAuthentication(credential) {
    return {
      id: credential.id, rawId: toBase64url(credential.rawId), type: credential.type,
      response: {
        authenticatorData: toBase64url(credential.response.authenticatorData),
        clientDataJSON: toBase64url(credential.response.clientDataJSON),
        signature: toBase64url(credential.response.signature),
        userHandle: credential.response.userHandle ? toBase64url(credential.response.userHandle) : null,
      },
      clientExtensionResults: credential.getClientExtensionResults?.() || {},
      authenticatorAttachment: credential.authenticatorAttachment || null,
    };
  }
})();
