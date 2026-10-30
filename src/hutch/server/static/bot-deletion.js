/* Whole-bot permanent deletion: a two-step, dependency-free control.
 *
 * The page renders only the Bot address; preview counts, the honest remaining
 * list, history and outcomes come from the typed JSON API, so this control can
 * never show demo data. Step one previews and renders the exact counts. Step
 * two stays disabled until the typed text equals the Bot address, then posts a
 * confirmation with a fresh Idempotency-Key and reports the cleanup state.
 *
 * Mount points: add data-bot-deletion plus data-bot-name to a container that
 * carries [data-bot-delete-preview], [data-bot-delete-confirmation] and
 * [data-bot-delete-confirm], then call HutchBotDeletion.mount(root) or rely on
 * the automatic mount below.
 */
(function () {
    "use strict";

    var API_ROOT = "/api/v1/bots/";
    var IDLE_PREVIEW_LABEL = "Preview permanent deletion";

    function deletionUrl(name) {
        return API_ROOT + encodeURIComponent(name) + "/deletion-requests";
    }

    function make(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function focusNode(node) {
        if (!node || typeof node.focus !== "function") return;
        try {
            node.focus();
        } catch (error) {
            /* A detached region is already unreachable by keyboard. */
        }
    }

    function idempotencyKey() {
        var cryptoApi = window.crypto;
        if (cryptoApi && typeof cryptoApi.randomUUID === "function") return cryptoApi.randomUUID();
        var bytes = new Uint8Array(16);
        if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
            cryptoApi.getRandomValues(bytes);
        } else {
            for (var i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
        }
        var hex = "";
        for (var j = 0; j < bytes.length; j += 1) hex += (bytes[j] < 16 ? "0" : "") + bytes[j].toString(16);
        return "fallback-" + hex;
    }

    function errorDetail(payload, status) {
        var detail = payload && payload.detail;
        if (typeof detail === "string" && detail) return detail;
        if (Array.isArray(detail)) {
            var messages = detail.map(function (item) {
                return item && item.msg ? item.msg : "invalid input";
            });
            if (messages.length) return messages.join(" ");
        }
        return "The request failed (" + status + ").";
    }

    function request(url, options) {
        return fetch(url, options).then(function (response) {
            return response.json().catch(function () {
                return null;
            }).then(function (payload) {
                if (!response.ok) {
                    var error = new Error(errorDetail(payload, response.status));
                    error.status = response.status;
                    throw error;
                }
                return payload || {};
            });
        });
    }

    function countEntries(counts) {
        var entries = [];
        Object.keys(counts || {}).forEach(function (key) {
            if (key === "total") return;
            var value = Number(counts[key]);
            if (!isFinite(value) || value <= 0) return;
            entries.push({ name: key.replace(/_/g, " "), count: value });
        });
        entries.sort(function (a, b) {
            return b.count - a.count || a.name.localeCompare(b.name);
        });
        return entries;
    }

    function countTotal(counts) {
        if (counts && typeof counts.total === "number") return counts.total;
        return countEntries(counts).reduce(function (sum, entry) {
            return sum + entry.count;
        }, 0);
    }

    function cleanupMessage(cleanupState) {
        switch (cleanupState) {
        case "none":
            return "No post-commit cleanup was requested.";
        case "pending":
            return "Managed-file cleanup has not started yet and resumes automatically on restart.";
        case "cleaning":
            return "Managed-file cleanup is still running and resumes automatically on restart.";
        case "cleaned":
            return "Every managed file was removed.";
        case "needs_attention":
            return "Hutch could not remove every managed file. The rows are erased, but the deletion is not fully complete and the remaining files need attention.";
        default:
            return "Cleanup state: " + (cleanupState || "unknown") + ".";
        }
    }

    function mount(root) {
        if (!root || root.getAttribute("data-bot-deletion-mounted") === "1") return;
        root.setAttribute("data-bot-deletion-mounted", "1");

        var els = {
            root: root,
            status: root.querySelector("[data-bot-delete-status]") || root.querySelector("#bot-deletion-status"),
            error: root.querySelector("[data-bot-delete-error]") || root.querySelector("#bot-deletion-error"),
            errorText: root.querySelector("#bot-deletion-error-text"),
            retry: root.querySelector("[data-bot-delete-retry]"),
            previewButton: root.querySelector("[data-bot-delete-preview]"),
            previewLabel: root.querySelector("[data-bot-delete-preview-label]"),
            preview: root.querySelector("[data-bot-delete-step='preview']"),
            countsTitle: root.querySelector("#bot-deletion-counts-title"),
            counts: root.querySelector("[data-bot-delete-counts]"),
            total: root.querySelector("[data-bot-delete-total]"),
            remaining: root.querySelector("[data-bot-delete-remaining]"),
            confirm: root.querySelector("[data-bot-delete-confirm]"),
            confirmation: root.querySelector("[data-bot-delete-confirmation]"),
            addressNodes: root.querySelectorAll("[data-bot-delete-address]"),
            success: root.querySelector("[data-bot-delete-success]"),
            outcome: root.querySelector("[data-bot-delete-outcome]"),
            cleanupState: root.querySelector("[data-bot-delete-cleanup-state]"),
            successRemaining: root.querySelector("[data-bot-delete-success-remaining]"),
            history: root.querySelector("[data-bot-delete-history]")
        };
        if (!els.previewButton || !els.confirmation || !els.confirm || !els.error) return;

        var apiName = root.getAttribute("data-bot-name") || "";
        var state = {
            busy: false,
            preview: null,
            confirmKey: null,
            retry: null,
            address: root.getAttribute("data-bot-name") || ""
        };

        function setStatus(text) {
            if (els.status) els.status.textContent = text;
        }

        function syncConfirm() {
            els.confirm.disabled = state.busy || els.confirmation.value !== state.address;
        }

        function setBusy(busy, message) {
            state.busy = busy;
            if (els.previewButton) els.previewButton.disabled = busy;
            syncConfirm();
            setStatus(busy ? message : "");
        }

        function clearError() {
            state.retry = null;
            if (els.error) els.error.classList.add("hidden");
        }

        function showError(message, retry) {
            if (els.errorText) els.errorText.textContent = message;
            if (els.retry) els.retry.classList.toggle("hidden", typeof retry !== "function");
            state.retry = typeof retry === "function" ? retry : null;
            els.error.classList.remove("hidden");
            setStatus("");
            focusNode(els.error);
        }

        function renderPreview(data) {
            var address = data.bot_name || state.address;
            state.address = address;
            Array.prototype.forEach.call(els.addressNodes, function (node) {
                node.textContent = address;
            });
            els.counts.textContent = "";
            countEntries(data.counts).forEach(function (entry) {
                var item = document.createElement("li");
                item.appendChild(make("span", "count", entry.count));
                item.appendChild(document.createTextNode(" " + entry.name));
                els.counts.appendChild(item);
            });
            els.total.textContent = String(countTotal(data.counts));
            els.remaining.textContent = "";
            (Array.isArray(data.remaining) ? data.remaining : []).forEach(function (statement) {
                els.remaining.appendChild(make("li", "", statement));
            });
            els.confirmation.value = "";
            els.confirmation.setAttribute("aria-invalid", "false");
            if (els.previewLabel) els.previewLabel.textContent = "Refresh preview";
            els.preview.classList.remove("hidden");
            syncConfirm();
            focusNode(els.countsTitle);
        }

        function renderOutcome(data) {
            var remaining = Array.isArray(data.remaining) ? data.remaining : [];
            var lines = [];
            var total = countTotal(data.counts);
            lines.push(total === 1
                ? "1 row or managed file was erased from Hutch."
                : total + " rows and managed files were erased from Hutch.");
            lines.push(cleanupMessage(data.cleanup_state));
            if (remaining.length) lines.push("What remains:");
            if (els.outcome) els.outcome.textContent = lines.join(" ");
            if (els.cleanupState) els.cleanupState.textContent = String(data.cleanup_state || "unknown");
            if (els.successRemaining) {
                els.successRemaining.textContent = "";
                remaining.forEach(function (statement) {
                    els.successRemaining.appendChild(make("li", "", statement));
                });
            }
            if (data.cleanup_state === "needs_attention") els.success.classList.add("error");
            els.preview.classList.add("hidden");
            els.previewButton.classList.add("hidden");
            els.success.classList.remove("hidden");
            els.history.textContent = "";
            els.history.appendChild(make("li", "muted",
                "This assistant is deleted. Its content-free deletion record remains in Hutch's evidence."));
            setStatus("");
            focusNode(els.success);
        }

        function renderHistory(requests) {
            els.history.textContent = "";
            if (!requests.length) {
                els.history.appendChild(make("li", "muted", "No deletion requests yet"));
                return;
            }
            requests.forEach(function (item) {
                var li = document.createElement("li");
                var status = typeof item.status === "string" && item.status ? item.status : "unknown";
                var chip = make("span", "chip", status);
                chip.classList.add("st-" + status);
                li.appendChild(chip);
                var created = typeof item.created_at === "string" ? item.created_at : "";
                li.appendChild(make("span", "small muted", " " + created));
                if (item.counts && typeof item.counts.total === "number") {
                    li.appendChild(make("span", "small", " - " + item.counts.total + " counted items"));
                }
                els.history.appendChild(li);
            });
        }

        function loadHistory() {
            request(deletionUrl(apiName), { headers: { "Accept": "application/json" } })
                .then(function (data) {
                    renderHistory(Array.isArray(data.requests) ? data.requests : []);
                })
                .catch(function (error) {
                    els.history.textContent = "";
                    var message = error.status === 404
                        ? "This assistant no longer exists, so its deletion history is not listed here."
                        : "Could not load deletion history.";
                    els.history.appendChild(make("li", "muted", message));
                });
        }

        function loadPreview() {
            if (state.busy) return;
            clearError();
            setBusy(true, "Requesting a preview. Nothing is deleted by a preview.");
            request(deletionUrl(apiName), {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: "{}"
            }).then(function (data) {
                state.preview = data;
                state.confirmKey = null;
                renderPreview(data);
            }, function (error) {
                var retry = error.status === 403 || error.status === 404 ? null : loadPreview;
                showError(error.message, retry);
            }).then(function () {
                setBusy(false);
            });
        }

        function confirmDeletion() {
            if (state.busy || !state.preview) return;
            var typed = els.confirmation.value;
            if (typed !== state.address) {
                syncConfirm();
                showError("That does not match the assistant address. Type " + state.address + " exactly.", null);
                return;
            }
            clearError();
            if (!state.confirmKey) state.confirmKey = idempotencyKey();
            var requestId = String(state.preview.request_id || "");
            var url = deletionUrl(apiName) + "/" + encodeURIComponent(requestId) + "/confirm";
            setBusy(true, "Deleting the assistant. Do not close this page.");
            request(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Idempotency-Key": state.confirmKey
                },
                body: JSON.stringify({ token: state.preview.token, confirmation: typed })
            }).then(function (data) {
                renderOutcome(data);
            }, function (error) {
                var retry = confirmDeletion;
                if (error.status === 403) {
                    retry = null;
                } else if (error.status === 404 || error.status === 409 || error.status === 422) {
                    state.preview = null;
                    state.confirmKey = null;
                    retry = loadPreview;
                }
                showError(error.message, retry);
            }).then(function () {
                setBusy(false);
            });
        }

        els.previewButton.addEventListener("click", loadPreview);
        els.retry.addEventListener("click", function () {
            var retry = state.retry;
            clearError();
            if (retry) retry();
        });
        els.confirmation.addEventListener("input", function () {
            els.confirmation.setAttribute("aria-invalid", "false");
            syncConfirm();
        });
        els.confirmation.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") return;
            event.preventDefault();
            if (els.confirm.disabled) {
                showError("That does not match the assistant address. Type " + state.address + " exactly.", null);
                return;
            }
            confirmDeletion();
        });
        els.confirm.addEventListener("click", confirmDeletion);

        if (els.previewLabel) els.previewLabel.textContent = IDLE_PREVIEW_LABEL;
        syncConfirm();
        loadHistory();
    }

    function autoMount() {
        Array.prototype.forEach.call(document.querySelectorAll("[data-bot-deletion]"), mount);
    }

    window.HutchBotDeletion = { mount: mount };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", autoMount);
    } else {
        autoMount();
    }
})();
