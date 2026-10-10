"use strict";

(() => {
  const form = document.querySelector("#pair-form");
  const submit = document.querySelector("#pair-submit");
  const error = document.querySelector("#pair-error");
  const success = document.querySelector("#pair-success");
  if (!form || !submit || !error || !success) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const codeField = form.elements.code;
    const labelField = form.elements.label;
    const payload = { code: codeField.value.trim(), label: labelField.value.trim() || "Phone" };
    if (!payload.code) {
      error.textContent = "Enter the one-time code shown on your Hutch host.";
      error.hidden = false;
      codeField.focus();
      return;
    }

    submit.disabled = true;
    submit.textContent = "Pairing…";
    error.hidden = true;
    codeField.value = "";
    try {
      const response = await fetch("/api/v1/pairing/exchange", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Hutch-Request": "1" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `Pairing failed (${response.status}).`);
      if (!window.PublicKeyCredential || !navigator.credentials?.create) {
        throw new Error("This browser cannot create a passkey. Use an up-to-date iOS Safari or Android Chrome.");
      }
      submit.textContent = "Create passkey…";
      const optionResponse = await fetch("/api/v1/passkeys/registration/options", {
        method: "POST", credentials: "same-origin", headers: { "X-Hutch-Request": "1" },
      });
      const options = await optionResponse.json().catch(() => ({}));
      if (!optionResponse.ok) throw new Error(options.detail || "Could not start passkey registration.");
      const challengeId = options.challenge_id;
      delete options.challenge_id;
      options.challenge = fromBase64url(options.challenge);
      options.user.id = fromBase64url(options.user.id);
      options.excludeCredentials = (options.excludeCredentials || []).map((item) => ({ ...item, id: fromBase64url(item.id) }));
      const credential = await navigator.credentials.create({ publicKey: options });
      const verified = await fetch("/api/v1/passkeys/registration/verify", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Hutch-Request": "1" },
        body: JSON.stringify({ challenge_id: challengeId, credential: serializeRegistration(credential) }),
      });
      const verification = await verified.json().catch(() => ({}));
      if (!verified.ok) throw new Error(verification.detail || "Passkey verification failed. Request a new pairing code.");
      form.hidden = true;
      document.querySelector("#pair-instructions").hidden = true;
      success.hidden = false;
      success.querySelector("a").focus();
    } catch (cause) {
      error.textContent = cause.message || "Pairing failed. Check the code and try again.";
      error.hidden = false;
      codeField.focus();
    } finally {
      submit.disabled = false;
      submit.textContent = "Pair device";
    }
  });

  function fromBase64url(value) {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
    return Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
  }
  function toBase64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }
  function serializeRegistration(credential) {
    return {
      id: credential.id, rawId: toBase64url(credential.rawId), type: credential.type,
      response: {
        attestationObject: toBase64url(credential.response.attestationObject),
        clientDataJSON: toBase64url(credential.response.clientDataJSON),
        transports: credential.response.getTransports?.() || [],
      },
      clientExtensionResults: credential.getClientExtensionResults?.() || {},
      authenticatorAttachment: credential.authenticatorAttachment || null,
    };
  }
})();
