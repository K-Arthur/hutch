/* Two-step governed permanent deletion of saved reference facts.
 *
 * window.hutchFactPurge.mount(root, botName, suggestionKeys, onPurged) renders the
 * whole control into root. Server-rendered pages carry a [data-fact-purge-bot]
 * element and are mounted automatically. API strings reach the DOM as textContent
 * only, never as markup; the preview token and request id stay in this closure.
 */
(function () {
  'use strict';

  var COUNT_FIELDS = [
    ['fact_revisions', 'Fact revisions'],
    ['legacy_rows', 'Older saved copies'],
    ['outgoing_shares', 'Shares sent'],
    ['incoming_shares', 'Shares received'],
    ['task_snapshots', 'Task brief snapshots'],
    ['receipts_redacted', 'API replay receipts redacted'],
    ['total', 'Total saved copies']
  ];
  var mountCount = 0;

  function node(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function clear(element) {
    element.replaceChildren();
  }

  function readJson(response) {
    return response.json().catch(function () { return null; });
  }

  function apiDetail(body, status) {
    var detail = body && body.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      var messages = detail.map(function (item) {
        return item && typeof item.msg === 'string' ? item.msg : 'The request was refused.';
      });
      if (messages.length) return messages.join(' ');
    }
    return 'The server refused the request (HTTP ' + status + ').';
  }

  function idempotencyKey() {
    var cryptoObject = window.crypto;
    if (cryptoObject && typeof cryptoObject.randomUUID === 'function') return cryptoObject.randomUUID();
    var bytes = new Uint8Array(16);
    if (cryptoObject && typeof cryptoObject.getRandomValues === 'function') cryptoObject.getRandomValues(bytes);
    else for (var fallback = 0; fallback < bytes.length; fallback += 1) bytes[fallback] = Math.floor(Math.random() * 256);
    var key = 'purge-';
    for (var index = 0; index < bytes.length; index += 1) key += bytes[index].toString(16).padStart(2, '0');
    return key;
  }

  function localTime(value) {
    var date = new Date(value);
    return isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  function buildCounts(counts) {
    var list = document.createElement('dl');
    list.setAttribute('data-fact-purge-counts', '');
    COUNT_FIELDS.forEach(function (pair) {
      var value = counts && typeof counts[pair[0]] === 'number' ? counts[pair[0]] : 0;
      list.append(node('dt', '', pair[1]));
      var amount = node('dd', 'mono', String(value));
      amount.setAttribute('data-fact-purge-count', pair[0]);
      list.append(amount);
    });
    return list;
  }

  function buildRemaining(items) {
    var list = document.createElement('ul');
    list.className = 'hint';
    list.setAttribute('data-fact-purge-remaining', '');
    (Array.isArray(items) ? items : []).forEach(function (item) {
      if (typeof item === 'string' && item) list.append(node('li', '', item));
    });
    return list;
  }

  function fetchSuggestionKeys(botName) {
    var url = '/api/v1/bots/' + encodeURIComponent(botName) + '/facts?all_scopes=true&limit=100';
    return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (page) {
        return page && Array.isArray(page.facts)
          ? page.facts.map(function (fact) { return fact.key; }) : [];
      })
      .catch(function () { return []; });
  }

  function routeBotName() {
    var match = /^#\/bot\/([^/?]+)/.exec(window.location.hash || '');
    if (!match) return '';
    try { return decodeURIComponent(match[1]); } catch (error) { return ''; }
  }

  function refreshRoute() {
    try { window.dispatchEvent(new HashChangeEvent('hashchange')); } catch (error) { window.location.reload(); }
  }

  function mount(root, botName, suggestionKeys, onPurged) {
    if (!root || typeof botName !== 'string' || !botName) return;
    if (root.getAttribute('data-fact-purge-mounted') === '1') return;
    root.setAttribute('data-fact-purge-mounted', '1');
    var groupId = 'fact-purge-scope-' + (++mountCount);
    var keys = [];
    var seen = {};
    (Array.isArray(suggestionKeys) ? suggestionKeys : []).forEach(function (key) {
      if (typeof key === 'string' && key.trim() && !Object.prototype.hasOwnProperty.call(seen, key)) {
        seen[key] = true;
        keys.push(key);
      }
    });
    var preview = null;
    var expected = '';
    var busy = false;

    var heading = node('h2', '', 'Permanent deletion');
    var intro = node('p', 'hint',
      'Erases the saved reference-fact content itself, including inherited share and task snapshots and short-lived API replay receipts. It does not erase chats, run transcripts, files, backups, or copies held by model providers.');
    var status = node('div', 'hint', '');
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    status.setAttribute('data-fact-purge-status', '');
    var alert = node('div', 'hint', '');
    alert.setAttribute('role', 'alert');
    alert.setAttribute('data-fact-purge-alert', '');
    alert.hidden = true;

    var stepOne = node('div');
    stepOne.setAttribute('data-fact-purge-step', '1');
    var fieldset = document.createElement('fieldset');
    fieldset.append(node('legend', '', 'Choose what to erase'));
    var keyRadio = document.createElement('input');
    keyRadio.type = 'radio';
    keyRadio.name = groupId;
    keyRadio.value = 'key';
    keyRadio.setAttribute('data-fact-purge-scope', 'key');
    var keyChoice = node('label', 'inline');
    keyChoice.append(keyRadio, document.createTextNode(' One saved key'));
    var allRadio = document.createElement('input');
    allRadio.type = 'radio';
    allRadio.name = groupId;
    allRadio.value = 'all';
    allRadio.setAttribute('data-fact-purge-scope', 'all');
    var allChoice = node('label', 'inline');
    allChoice.append(allRadio, document.createTextNode(' All saved facts for this assistant'));
    fieldset.append(keyChoice, allChoice);

    var keyLabel = node('label', 'field');
    keyLabel.append(node('span', '', 'Saved key'));
    var keySelect = document.createElement('select');
    keySelect.setAttribute('data-fact-purge-key', '');
    keys.forEach(function (key) {
      var option = document.createElement('option');
      option.value = key;
      option.textContent = key;
      keySelect.append(option);
    });
    keyLabel.append(keySelect);
    var keyHint = node('p', 'hint', '');
    keyHint.setAttribute('data-fact-purge-key-hint', '');

    var noteLabel = node('label', 'field');
    noteLabel.append(node('span', '', 'Note (optional)'));
    var noteInput = document.createElement('input');
    noteInput.type = 'text'; noteInput.maxLength = 1000; noteInput.placeholder = 'Why are you erasing this?';
    noteInput.setAttribute('data-fact-purge-note', '');
    noteLabel.append(noteInput);

    var previewRow = node('div', 'inline');
    var previewButton = node('button', 'btn', 'Preview permanent deletion');
    previewButton.type = 'button';
    previewButton.setAttribute('data-fact-purge-preview', '');
    previewRow.append(previewButton);
    stepOne.append(fieldset, keyLabel, keyHint, noteLabel, previewRow);

    var stepTwo = node('div');
    stepTwo.setAttribute('data-fact-purge-step', '2');
    stepTwo.hidden = true;
    root.append(heading, intro, status, alert, stepOne, stepTwo);

    if (keys.length) {
      keyRadio.checked = true;
    } else {
      keyRadio.disabled = true;
      allRadio.checked = true;
    }
    syncScope();

    function syncScope() {
      keySelect.disabled = allRadio.checked || !keys.length;
      if (!keys.length) {
        keyHint.textContent = 'No saved keys are visible here. Preview all saved facts for this assistant, or erase one key from Saved notes or the CLI (bot purge --key).';
      } else if (allRadio.checked) {
        keyHint.textContent = 'Every saved fact for this assistant will be previewed.';
      } else {
        keyHint.textContent = 'Only the selected saved key will be previewed.';
      }
    }

    function resetToOne() {
      preview = null;
      expected = '';
      busy = false;
      clear(stepTwo);
      stepTwo.hidden = true;
      stepOne.hidden = false;
      previewButton.disabled = false;
      status.textContent = '';
      alert.hidden = true;
    }

    function renderStepTwo(data) {
      clear(stepTwo);
      var scope = node('p', 'hint', data.scope_kind === 'all'
        ? 'Scope: all saved facts for ' + botName
        : 'Scope: saved key ' + expected);
      scope.setAttribute('data-fact-purge-scope-label', '');
      stepTwo.append(scope);
      if (data.expires_at) {
        var expiry = node('p', 'hint', 'This confirmation expires ' + localTime(data.expires_at) + '.');
        expiry.setAttribute('data-fact-purge-expiry', '');
        stepTwo.append(expiry);
      }
      stepTwo.append(buildCounts(data.counts));
      stepTwo.append(node('p', 'hint', 'Not erased by this control:'));
      stepTwo.append(buildRemaining(data.remaining));

      var confirmLabel = node('label', 'field');
      confirmLabel.setAttribute('data-fact-purge-confirm-label', '');
      var labelText = node('span', '', 'Type ');
      var expectedCode = node('code', 'mono', expected);
      expectedCode.setAttribute('data-fact-purge-expected', '');
      labelText.append(expectedCode, document.createTextNode(data.scope_kind === 'all'
        ? " (this assistant's address) exactly to enable Erase permanently."
        : ' exactly to enable Erase permanently.'));
      confirmLabel.append(labelText);
      var confirmation = document.createElement('input');
      confirmation.type = 'text'; confirmation.autocomplete = 'off'; confirmation.spellcheck = false;
      confirmation.setAttribute('data-fact-purge-confirmation', '');
      confirmLabel.append(confirmation);

      var actions = node('div', 'inline');
      var confirmButton = node('button', 'btn danger', 'Erase permanently');
      confirmButton.type = 'button';
      confirmButton.disabled = true;
      confirmButton.setAttribute('data-fact-purge-confirm', '');
      var cancelButton = node('button', 'btn ghost', 'Cancel');
      cancelButton.type = 'button';
      cancelButton.setAttribute('data-fact-purge-cancel', '');
      actions.append(confirmButton, cancelButton);
      stepTwo.append(confirmLabel, actions);
      stepTwo.hidden = false;
      confirmation.focus();

      confirmation.addEventListener('input', function () {
        confirmButton.disabled = busy || confirmation.value.trim() !== expected;
      });
      confirmButton.addEventListener('click', function () {
        if (!busy && confirmation.value.trim() === expected) {
          doConfirm(data, confirmation, confirmButton, cancelButton);
        }
      });
      cancelButton.addEventListener('click', resetToOne);
    }

    async function doPreview() {
      if (busy) return;
      var all = allRadio.checked;
      if (!all && !keySelect.value) {
        alert.textContent = 'Choose one saved key before previewing.';
        alert.hidden = false;
        return;
      }
      alert.hidden = true;
      alert.textContent = '';
      busy = true;
      previewButton.disabled = true;
      status.textContent = 'Previewing permanent deletion...';
      try {
        var body = all ? { all: true } : { key: keySelect.value };
        var note = noteInput.value.trim();
        if (note) body.note = note;
        var response = await fetch('/api/v1/bots/' + encodeURIComponent(botName) + '/facts/purge-requests', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(body)
        });
        var data = await readJson(response);
        if (!response.ok) throw new Error(apiDetail(data, response.status));
        preview = data;
        expected = data.scope_kind === 'all' ? botName : (data.scope_key || keySelect.value);
        status.textContent = '';
        stepOne.hidden = true;
        renderStepTwo(data);
      } catch (error) {
        status.textContent = '';
        alert.textContent = 'Could not preview the deletion: ' + error.message;
        alert.hidden = false;
      } finally {
        busy = false;
        previewButton.disabled = false;
      }
    }

    async function doConfirm(data, confirmation, confirmButton, cancelButton) {
      if (busy || !preview) return;
      busy = true;
      confirmButton.disabled = true;
      cancelButton.disabled = true;
      alert.hidden = true;
      alert.textContent = '';
      status.textContent = 'Erasing saved copies...';
      try {
        var response = await fetch('/api/v1/bots/' + encodeURIComponent(botName)
          + '/facts/purge-requests/' + encodeURIComponent(data.request_id) + '/confirm', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'Idempotency-Key': idempotencyKey()
          },
          body: JSON.stringify({ token: data.token, confirmation: confirmation.value.trim() })
        });
        var result = await readJson(response);
        if (!response.ok) throw new Error(apiDetail(result, response.status));
        renderSuccess(result);
      } catch (error) {
        status.textContent = '';
        alert.textContent = 'Could not erase the saved copies: ' + error.message;
        alert.hidden = false;
        confirmButton.disabled = confirmation.value.trim() !== expected;
        cancelButton.disabled = false;
      } finally {
        busy = false;
      }
    }

    function renderSuccess(result) {
      var counts = result.counts || {};
      var total = typeof counts.total === 'number' ? counts.total : 0;
      stepOne.hidden = true; clear(stepTwo); stepTwo.hidden = true; status.textContent = '';
      status.setAttribute('data-fact-purge-success', '');
      status.tabIndex = -1; status.focus();
      status.append(node('strong', '', 'Erased ' + total + ' saved ' + (total === 1 ? 'copy' : 'copies') + '.'));
      status.append(buildCounts(counts));
      status.append(node('p', 'hint', 'Not erased by this control:'));
      status.append(buildRemaining(result.remaining));
      if (typeof onPurged === 'function') {
        // Refreshing the saved notes re-renders this panel, so show the outcome first.
        window.setTimeout(onPurged, 2500);
      }
    }

    keyRadio.addEventListener('change', syncScope);
    allRadio.addEventListener('change', syncScope);
    previewButton.addEventListener('click', doPreview);
  }

  function autoMount() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-fact-purge-bot]'), function (root) {
      var botName = root.getAttribute('data-fact-purge-bot') || '';
      fetchSuggestionKeys(botName).then(function (keys) {
        mount(root, botName, keys, function () { window.location.reload(); });
      });
    });
    // If the dashboard rendered before this script loaded, its explicit mount was skipped.
    var spaRoot = document.getElementById('fact-purge-root');
    if (!spaRoot || spaRoot.getAttribute('data-fact-purge-mounted') === '1' || spaRoot.childElementCount) return;
    var spaBot = routeBotName();
    if (!spaBot) return;
    fetchSuggestionKeys(spaBot).then(function (keys) {
      mount(spaRoot, spaBot, keys, refreshRoute);
    });
  }

  window.hutchFactPurge = { mount: mount, autoMount: autoMount };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoMount, { once: true });
  } else {
    autoMount();
  }
})();
