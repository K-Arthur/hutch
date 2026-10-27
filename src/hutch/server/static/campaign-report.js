/* Reviewed deterministic method; uses the canonical workflow admission and artifacts. */
"use strict";

function openCampaignReport({ returnFocus, bot, conversationId, generation }) {
  let revision = 0, reviewed = null, busy = false, form = null, confirm = null;
  let fileGeneration = 0, fileLoading = false;
  const field = selector => form.querySelector(selector);
  const current = () => generation === studioGeneration && conversationId === currentConversationId && bot === currentStudioBot;
  openModal({
    title: "Campaign report", wide: true, returnFocus,
    confirmText: "Preview report", confirmClass: "primary",
    bodyHtml: `<div class="campaign-report-form">
      <p class="campaign-report-lead">Turn a campaign export into checked metrics. Review the numbers before saving a local draft.</p>
      <p class="campaign-report-scope">No model calls · no campaign changes</p>
      <div class="campaign-report-source">
        <label class="field" for="campaign-source">Campaign CSV
          <textarea id="campaign-source" rows="6" maxlength="65536" spellcheck="false" wrap="off" aria-describedby="campaign-source-help" placeholder="Paste the CSV export here"></textarea>
        </label>
        <p id="campaign-source-help" class="hint">Use one export with matching currency, units and reporting window. Up to 64 KB.</p>
        <div><button type="button" class="btn ghost" id="campaign-file-open">Choose CSV file</button><input type="file" id="campaign-file" accept=".csv,text/csv" hidden><span id="campaign-file-name" class="hint" role="status"></span></div>
        <details><summary>Required columns and calculations</summary><p class="hint campaign-report-columns">campaign,impressions,clicks,spend,conversions,revenue,daily_budget</p>
          <p class="hint">One row per campaign. CTR = clicks / impressions; CVR = conversions / clicks; CPA = spend / conversions; ROAS = revenue / spend. Empty metrics are undefined, not zero.</p></details>
      </div>
      <div class="field"><label for="campaign-days">Reporting period in whole days</label>
        <input id="campaign-days" type="number" min="0" max="3660" step="1" value="0" aria-describedby="campaign-days-help">
        <span class="hint" id="campaign-days-help">Leave 0 when unknown. Budget checks need a complete matching window and daily budgets that stayed constant.</span>
      </div>
      <section id="campaign-preview" aria-label="Report preview" hidden></section>
      <p id="campaign-report-error" class="campaign-report-error" role="alert"></p>
    </div>`,
    onConfirm: async () => {
      if (busy || fileLoading) return false;
      busy = true;
      confirm.disabled = true;
      const error = field("#campaign-report-error");
      error.textContent = "";
      try {
        if (!current()) throw new Error("The conversation changed. Close this dialog and reopen the report in your chosen chat.");
        const source = field("#campaign-source").value;
        const rawDays = field("#campaign-days").value;
        if (!source.trim()) throw new Error("Paste a campaign CSV or choose a file first.");
        if (new TextEncoder().encode(source).length > 65536) throw new Error("Choose a campaign CSV of 64 KB or less.");
        if (!/^\d+$/.test(rawDays) || Number(rawDays) > 3660) throw new Error("Use a whole number from 0 to 3660 for reporting days.");
        const inputs = { source_csv: source, reporting_days: Number(rawDays) };
        if (!reviewed) {
          const expectedRevision = revision;
          const result = await api("/v1/workflows/starters/campaign-report/preview", { method: "POST", body: inputs });
          if (!current() || !form.isConnected) return false;
          if (revision !== expectedRevision) throw new Error("Your source changed during preview. Preview the updated report before saving.");
          reviewed = { ...result, inputs };
          const report = result.report;
          const fields = ["campaign", "ctr", "cvr", "cpa", "roas", "alert"];
          const labels = ["Campaign", "CTR", "CVR", "CPA", "ROAS", "Review flags"];
          const displayValue = (row, field) => field === "alert"
            ? (row.alert ? row.alert.split(";").map(value => ({ zero_conversions: "No conversions", over_budget: "Above budget" })[value] || value).join("; ") : "None")
            : row[field];
          field("#campaign-preview").innerHTML = `<h3>Review the report</h3>
            <p>${report.reporting_days ? `${esc(report.reporting_days)} whole day(s), as supplied.` : "Reporting period unknown — daily overspend and pacing are unverified."}</p>
            <p class="hint">Rates are fractions, rounded to four decimal places. — means undefined. Amounts keep the source’s units.</p>
            <div class="campaign-report-table" tabindex="0" role="region" aria-label="Campaign metrics, scroll horizontally for all columns"><table><thead><tr>${labels.map(label => `<th scope="col">${label}</th>`).join("")}</tr></thead><tbody>${report.rows.slice(0, 20).map(row => `<tr>${fields.map((field, index) => index === 0 ? `<th scope="row">${esc(row[field])}</th>` : `<td>${row[field] === null ? '<span aria-label="Undefined">—</span>' : esc(displayValue(row, field))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
            <p class="hint">Six columns. Scroll the table horizontally if needed.</p>
            <p class="hint">${report.rows.length > 20 ? `Showing the first 20 of ${esc(report.rows.length)} campaigns. Saved artifacts include every row. ` : ""}ROAS is not profit. Currency and attribution are unverified. Review flags do not authorize changes.</p>
            <p>Saving creates three local draft artifacts in this chat: metrics CSV, calculation record and report notes. Hutch checks their saved bytes. Your source is retained in the workflow’s local history. The reusable method is saved for manual use; automatic use stays off.</p>`;
          field("#campaign-preview").hidden = false;
          confirm.textContent = "Save local report";
          field("#campaign-preview").scrollIntoView({ block: "nearest" });
          return false;
        }
        const payload = { bot, conversation_id: conversationId, plan: reviewed.plan,
          inputs: reviewed.inputs, save_definition: true };
        const scope = `campaign-report:${conversationId}`;
        const key = await messageIdempotencyKey(scope, payload);
        const result = await api("/v1/workflows/plans", { method: "POST", headers: { "Idempotency-Key": key }, body: payload });
        clearMessageIdempotencyKey(scope, key);
        if (current()) {
          currentRunId = result.attempt_run_id;
          subscribeRun(result.attempt_run_id);
          void refreshWorkflowPanel(bot, conversationId, generation, true);
        }
        toast("Campaign report started. Saved artifacts and checks will appear in this chat.");
        return true;
      } catch (failure) {
        error.textContent = failure.message;
        return false;
      } finally {
        busy = false;
        confirm.disabled = fileLoading;
      }
    },
  });
  form = $(".campaign-report-form");
  form.closest(".modal-card").classList.add("campaign-report-dialog");
  confirm = $("#modal-confirm");
  function invalidate() {
    revision++;
    reviewed = null;
    field("#campaign-preview").hidden = true;
    confirm.textContent = "Preview report";
  }
  field("#campaign-source").addEventListener("input", () => {
    invalidate();
    field("#campaign-file-name").textContent = "";
  });
  field("#campaign-days").addEventListener("input", invalidate);
  field("#campaign-file-open").addEventListener("click", () => field("#campaign-file").click());
  field("#campaign-file").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    const fileToken = ++fileGeneration;
    fileLoading = true;
    confirm.disabled = true;
    field("#campaign-file-name").textContent = "Reading CSV…";
    const loadingRevision = ++revision;
    reviewed = null;
    field("#campaign-preview").hidden = true;
    confirm.textContent = "Preview report";
    try {
      if (file.size > 65536) throw new Error("Choose a campaign CSV of 64 KB or less.");
      const text = await file.text();
      if (revision !== loadingRevision || !form.isConnected) return;
      field("#campaign-source").value = text;
      invalidate();
      field("#campaign-file-name").textContent = file.name;
      field("#campaign-report-error").textContent = "";
    } catch (failure) {
      if (fileToken === fileGeneration && revision === loadingRevision) {
        field("#campaign-file-name").textContent = "";
        field("#campaign-report-error").textContent = failure.message;
      }
    } finally {
      if (fileToken === fileGeneration) {
        fileLoading = false;
        confirm.disabled = busy;
        if (field("#campaign-file-name").textContent === "Reading CSV…") field("#campaign-file-name").textContent = "";
      }
      event.target.value = "";
    }
  });
}
