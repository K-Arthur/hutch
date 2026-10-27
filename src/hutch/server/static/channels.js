/* Channel setup stays owner-only. Tokens never enter browser storage or URLs. */
(() => {
  function panel() {
    return `<section class="panel conn-card channel-panel" id="connection-telegram" aria-labelledby="telegram-title">
      <header class="channel-intro"><h2 id="telegram-title">A direct line to your assistant</h2>
        <p>Send a private Telegram message. Get the reply in the same place, with the work and its history in Hutch.</p></header>
      <ul class="channel-boundaries"><li>Only the people you choose</li><li>Changes reviewed in Hutch</li><li>Runs while this computer is awake</li></ul>
      <details class="channel-privacy"><summary>Data and permission boundaries</summary><p class="hint">Private text messages only for now. Groups, attachments and slash commands are ignored. Each sender has a separate conversation; your main chat is not copied into it. Replies may use this assistant’s existing knowledge and permitted tools. Telegram and the selected model service receive the messages they handle.</p></details>
      <p id="channel-status" class="hint" role="status"></p>
      <div id="channel-connections" aria-label="Telegram connections"><p class="hint">Loading connections…</p></div>
      <details id="channel-setup"><summary>Connect a Telegram bot</summary>
        <div class="channel-setup-body"><p>Create a dedicated bot with <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer">Telegram’s BotFather</a>, then paste its bot token below. A bot used by another polling app cannot be shared with Hutch.</p>
          <form id="channel-create" class="channel-form">
            <div class="field"><label for="channel-name">Connection name</label><input id="channel-name" type="text" name="name" required maxlength="80" placeholder="Personal Telegram" autocomplete="off"></div>
            <div class="field"><label for="channel-bot">Assistant</label><select id="channel-bot" name="bot_id" required><option value="">Choose an assistant…</option></select></div>
            <div class="field channel-form-wide"><label for="channel-token">Bot token</label><input id="channel-token" name="token" type="password" required autocomplete="off" spellcheck="false" maxlength="128" aria-describedby="channel-token-help"><span class="hint" id="channel-token-help">Saved in your operating system’s secure store. Never sent to a model.</span></div>
            <div class="channel-form-wide channel-sender-picker"><h3>Who can message this assistant?</h3>
              <p class="hint">Send a private “hello” to your bot in Telegram, then find and select your account. Finding accounts does not start work or acknowledge messages.</p>
              <button class="btn ghost" id="channel-find-senders" type="button">Find my Telegram account</button>
              <div id="channel-sender-choices" role="group" aria-label="Allowed Telegram accounts"></div>
              <details><summary>Enter Telegram user IDs instead</summary><div class="field"><label for="channel-sender-ids">Allowed user IDs</label><input id="channel-sender-ids" type="text" name="sender_ids" inputmode="numeric" autocomplete="off" placeholder="123456789" aria-describedby="channel-ids-help"><span id="channel-ids-help" class="hint">Separate numeric IDs with commas. Usernames are not accepted.</span></div></details>
            </div>
            <p class="hint channel-form-wide">Messages and replies reach Telegram and the model service selected for this assistant. Other tools keep their current permissions. Channel messages cannot approve actions.</p>
            <div class="channel-form-wide"><button type="submit" class="btn primary">Save connection</button><p class="hint">Saved connections stay paused until you choose to start receiving and replying. Send a new message after starting; older backlog is ignored.</p></div>
          </form>
        </div>
      </details>
      <footer class="channel-preview-note"><strong>More channels</strong><p class="hint">Slack Socket Mode and signed webhooks are not available yet. Telegram acceptance here is limited to private text conversations.</p></footer>
    </section>`;
  }

  async function mount(root, { api, bots, esc, openModal, initial }) {
    if (!root) return;
    const status = root.querySelector('#channel-status');
    const form = root.querySelector('#channel-create');
    const list = root.querySelector('#channel-connections');
    const choices = root.querySelector('#channel-sender-choices');
    let data = null, requestVersion = 0;
    const active = () => root.isConnected && location.hash.split('?')[0] === '#/connections';
    const say = message => { if (active()) status.textContent = message; };
    const selectedBot = id => bots.find(bot => bot.id === id);
    const label = id => selectedBot(id)?.display_name || selectedBot(id)?.name || 'Assistant unavailable';
    const eligible = bots.filter(bot => bot.approval_mode === 'ask');
    form.elements.bot_id.innerHTML += eligible.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join('');

    async function load() {
      const version = ++requestVersion;
      try {
        const current = initial || await api('/v1/channels');
        initial = null;
        if (!active() || version !== requestVersion) return;
        data = current;
        list.innerHTML = current.connections.length ? current.connections.map(connection => `<article class="channel-connection" data-channel="${esc(connection.id)}">
          <header><div><h3>${esc(connection.name)}</h3><p>${esc(label(connection.bot_id))} · ${connection.allowed_senders.length} allowed account${connection.allowed_senders.length === 1 ? '' : 's'}</p></div><span class="chip ${connection.enabled ? 'ok' : ''}">${connection.enabled ? 'Receiving and replying' : connection.has_token ? 'Paused' : 'Disconnected'}</span></header>
          ${connection.last_error ? `<p class="channel-error" role="status">${esc(connection.last_error)}</p>` : ''}
          <div class="channel-actions"><button class="btn ${connection.enabled ? 'ghost' : 'primary'}" type="button" data-channel-toggle="${esc(connection.id)}" ${!connection.has_token ? 'disabled' : ''}>${connection.enabled ? 'Pause' : 'Start receiving and replying'}</button><button class="btn ghost" type="button" data-channel-deliveries="${esc(connection.id)}">Review deliveries</button></div>
          <details><summary>Connection details</summary><p class="hint">Allowed Telegram IDs: ${connection.allowed_senders.map(esc).join(', ')}. Up to 20 new tasks per hour; one task at a time for this connection.</p>
            <p class="hint">Pausing stops queued and active channel tasks and cancels unsent replies. A send already in progress may still reach Telegram. Chat history stays in Hutch.</p>
            ${!connection.enabled ? `<form data-channel-configure="${esc(connection.id)}" class="channel-access-form">
              <div class="field"><label for="channel-name-${esc(connection.id)}">Connection name</label><input type="text" id="channel-name-${esc(connection.id)}" name="name" required maxlength="80" value="${esc(connection.name)}"></div>
              <div class="field"><label for="channel-bot-${esc(connection.id)}">Assigned assistant</label><select id="channel-bot-${esc(connection.id)}" name="bot_id" required><option value="">Choose an assistant…</option>${eligible.map(bot => `<option value="${esc(bot.id)}" ${bot.id === connection.bot_id ? 'selected' : ''}>${esc(bot.display_name || bot.name)}</option>`).join('')}</select></div>
              <div class="field"><label for="channel-senders-${esc(connection.id)}">Allowed Telegram user IDs</label><input type="text" id="channel-senders-${esc(connection.id)}" name="sender_ids" required value="${esc(connection.allowed_senders.join(', '))}" aria-describedby="channel-access-help-${esc(connection.id)}"></div>
              <p class="hint" id="channel-access-help-${esc(connection.id)}">Changing assistants starts a separate conversation for each sender. Previous history is not transferred. Keep only people you trust with this assistant’s knowledge and tools.</p>
              <button type="submit" class="btn ghost">Save channel access</button></form>` : ''}
            ${!connection.enabled ? `<form data-channel-reconnect="${esc(connection.id)}" class="channel-reconnect"><label class="field">Replacement bot token<input name="token" type="password" required maxlength="128" autocomplete="off"></label><button type="submit" class="btn ghost">Reconnect this bot</button></form>` : ''}
            <button class="btn danger" type="button" data-channel-disconnect="${esc(connection.id)}" ${!connection.has_token ? 'disabled' : ''}>Disconnect and remove token</button></details>
          <div data-channel-delivery-list hidden></div></article>`).join('') : '<p class="channel-empty">No Telegram bots connected. Set up your first connection below.</p>';
        root.querySelector('#channel-setup').open = !current.connections.length;
        for (const control of form.querySelectorAll('input,select,button')) control.disabled = !current.secret_store_available;
        if (!current.secret_store_available) say('Secure credential storage is unavailable. Unlock your system keyring before connecting. On Linux, install secret-tool if needed.');
        else if (!eligible.length) say('Create an assistant that asks before changes before connecting Telegram.');
      } catch (error) { say(`Could not load Telegram connections: ${error.message}`); }
    }

    form.elements.token.addEventListener('input', () => { choices.replaceChildren(); });
    root.querySelector('#channel-find-senders').addEventListener('click', async event => {
      const button = event.currentTarget, token = form.elements.token.value;
      if (!token) { say('Paste the bot token first, then send your bot a private hello.'); form.elements.token.focus(); return; }
      button.disabled = true; say('Checking pending private-message senders…');
      try {
        const result = await api('/v1/channels/telegram/senders', { method: 'POST', body: { token } });
        if (!active() || form.elements.token.value !== token) return;
        choices.innerHTML = result.senders.map(sender => `<label class="channel-sender"><input type="checkbox" value="${esc(sender.id)}"><span>${esc(sender.name)}<small>Telegram ID ${esc(sender.id)}</small></span></label>`).join('');
        say(result.senders.length ? 'Select only accounts you trust to use this assistant.' : 'No pending private messages found. Send your bot a hello in Telegram, then try again.');
      } catch (error) { say(error.message); }
      finally { if (active()) button.disabled = false; }
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[type=submit]');
      const allowed = [...new Set([...choices.querySelectorAll('input:checked')].map(input => input.value)
        .concat(form.elements.sender_ids.value.split(',').map(value => value.trim()).filter(Boolean)))];
      if (!allowed.length) { say('Choose an allowed Telegram account, or enter its numeric ID.'); return; }
      const body = { name: form.elements.name.value, bot_id: form.elements.bot_id.value,
        token: form.elements.token.value, allowed_senders: allowed };
      button.disabled = true; say('Checking the bot and saving a paused connection…');
      try {
        await api('/v1/channels/telegram', { method: 'POST', body });
        if (!active()) return;
        form.reset(); choices.replaceChildren(); await load(); say('Connection saved and paused. Review it, then start receiving and replying.');
      } catch (error) { say(error.message); }
      finally { if (active()) button.disabled = !data?.secret_store_available; }
    });

    async function change(connection, enabled) {
      await api(`/v1/channels/${encodeURIComponent(connection.id)}/enabled`, { method: 'PUT',
        body: { enabled, expected_revision: connection.revision } });
      await load(); say(enabled ? 'Receiving and replying to the selected Telegram accounts.' : 'Channel paused. Unsent replies are cancelled; a send already in progress may still arrive.');
    }
    list.addEventListener('click', async event => {
      const button = event.target.closest('button');
      const card = button?.closest('[data-channel]');
      if (!card || !data) return;
      const connection = data.connections.find(item => item.id === card.dataset.channel);
      if (!connection) return;
      if (button.dataset.channelToggle && !connection.enabled) {
        openModal({ title: 'Start this Telegram connection?', returnFocus: button, confirmText: 'Start receiving and replying',
          bodyHtml: `<p><strong>${esc(label(connection.bot_id))}</strong> will respond to Telegram IDs <strong>${connection.allowed_senders.map(esc).join(', ')}</strong>.</p><p>Replies can use this assistant’s existing knowledge and permitted tools. Telegram and the selected model service receive the messages they handle. Changes still require review in Hutch.</p><p class="hint">You can pause or disconnect this connection here at any time.</p><p class="hint" id="channel-start-status" role="status"></p>`,
          onConfirm: async () => { try { await change(connection,true); return true; } catch (error) { const field=document.querySelector('#channel-start-status'); if(field)field.textContent=error.message; return false; } } });
        return;
      }
      button.disabled = true;
      try {
        if (button.dataset.channelToggle) await change(connection,false);
        else if (button.dataset.channelDisconnect) {
          await api(`/v1/channels/${encodeURIComponent(connection.id)}?expected_revision=${connection.revision}`, { method: 'DELETE' });
          await load(); say('Token removed. This connection is disconnected; its history is retained.');
        } else if (button.dataset.channelDeliveries) {
          const result = await api(`/v1/channels/${encodeURIComponent(connection.id)}/deliveries`);
          if (!active() || !card.isConnected) return;
          const target = card.querySelector('[data-channel-delivery-list]'); target.hidden = false;
          target.innerHTML = `<h4>Recent reply deliveries</h4>${result.deliveries.length ? result.deliveries.map(delivery => `<div class="channel-delivery"><strong>${esc(delivery.state === 'uncertain' ? 'Delivery unconfirmed' : delivery.state)}</strong><p class="hint">${esc(delivery.error || (delivery.state === 'sent' ? 'Telegram accepted the reply. This does not prove it was read.' : 'No confirmed delivery yet.'))}</p><a class="btn ghost" href="#/run/${encodeURIComponent(delivery.run_id)}">Open task and answer</a>${delivery.state === 'uncertain' ? `<button class="btn ghost" type="button" data-channel-reconcile="${delivery.id}" data-channel-attempts="${delivery.attempts}">Review outcome</button>` : ''}</div>`).join('') : '<p class="hint">No replies sent yet.</p>'}`;
        } else if (button.dataset.channelReconcile) {
          openModal({ title: 'Reconcile this reply', returnFocus: button, confirmText: 'Record checked outcome',
            bodyHtml: `<p>Check the actual Telegram conversation before choosing. Hutch cannot safely infer whether a lost response was delivered.</p><div class="field"><label for="channel-delivery-outcome">Checked outcome</label><select id="channel-delivery-outcome"><option value="">Choose an outcome…</option><option value="yes">The reply is present in Telegram</option><option value="no">Confirmed absent; allow one retry</option></select></div><div class="field"><label for="channel-delivery-evidence">Evidence</label><textarea id="channel-delivery-evidence" minlength="10" maxlength="500" placeholder="What did you check?"></textarea></div><p class="hint" role="status" id="channel-reconcile-status"></p>`,
            onConfirm: async () => {
              const outcome=document.querySelector('#channel-delivery-outcome').value, evidence=document.querySelector('#channel-delivery-evidence').value;
              const statusField=document.querySelector('#channel-reconcile-status');
              if (!outcome || evidence.trim().length<10) { statusField.textContent='Choose a checked outcome and record its independent evidence.'; return false; }
              try { await api(`/v1/channels/${encodeURIComponent(connection.id)}/deliveries/${button.dataset.channelReconcile}/reconcile`, { method:'POST',body:{attempts:Number(button.dataset.channelAttempts),delivered:outcome==='yes',evidence} }); await load(); say('Checked delivery outcome recorded.'); return true; }
              catch (error) { if(statusField.isConnected)statusField.textContent=error.message; return false; }
            } });
        }
      } catch (error) { say(error.message); }
      finally { if (button.isConnected) button.disabled = false; }
    });
    list.addEventListener('submit', async event => {
      const configure = event.target.closest('[data-channel-configure]');
      if (configure && data) {
        event.preventDefault();
        const connection = data.connections.find(item => item.id === configure.dataset.channelConfigure);
        const button = configure.querySelector('button'); button.disabled = true;
        try {
          await api(`/v1/channels/${encodeURIComponent(connection.id)}/configuration`, { method:'PUT',body:{
            expected_revision:connection.revision,name:configure.elements.name.value,bot_id:configure.elements.bot_id.value,
            allowed_senders:configure.elements.sender_ids.value.split(',').map(value => value.trim()).filter(Boolean) } });
          await load(); say('Channel access saved. Review the selected accounts before starting it again.');
        } catch (error) { say(error.message); }
        finally { if(button.isConnected)button.disabled=false; }
        return;
      }
      const reconnect = event.target.closest('[data-channel-reconnect]');
      if (!reconnect || !data) return;
      event.preventDefault();
      const connection=data.connections.find(item => item.id===reconnect.dataset.channelReconnect), button=reconnect.querySelector('button');
      button.disabled=true;
      try { await api(`/v1/channels/${encodeURIComponent(connection.id)}/token`,{method:'PUT',body:{token:reconnect.elements.token.value,expected_revision:connection.revision}}); reconnect.reset(); await load(); say('Token replaced. This connection stays paused until you start it.'); }
      catch (error) { say(error.message); }
      finally { if(button.isConnected)button.disabled=false; }
    });
    await load();
  }
  window.hutchChannels = { panel, mount };
})();
