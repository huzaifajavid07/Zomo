/**
 * Zomo — Dashboard Application Logic
 * Handles API communication, WebSocket live logs, timers, and UI state.
 */

const App = (() => {
  // ── State ──────────────────────────────────────────────
  let config = null;
  let presets = {};
  let activePreset = 'casual';
  let activeMessages = [];
  let ws = null;
  let statusPollId = null;
  let mouseTrackerId = null;
  let isMouseTracking = false;

  // ── DOM Helpers ────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // ── Initialization ─────────────────────────────────────
  async function init() {
    await loadConfig();
    await loadPresets();
    connectWebSocket();
    startStatusPolling();
    applyConfigToUI();
    renderPresetGrid();
    renderMessageList();
    console.log('[Zomo] Dashboard initialized.');
  }

  // ── API Calls ──────────────────────────────────────────
  async function api(path, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
      const res = await fetch(`/api${path}`, opts);
      return await res.json();
    } catch (err) {
      addLogEntry({ timestamp: now(), level: 'error', message: `API error: ${err.message}` });
      return null;
    }
  }

  async function loadConfig() {
    config = await api('/config');
    if (!config) config = {};
  }

  async function loadPresets() {
    presets = await api('/presets') || {};
  }

  // ── Bot Control ────────────────────────────────────────
  async function startBot() {
    await saveConfig();
    const result = await api('/bot/start', 'POST');
    if (result) {
      addLogEntry({ timestamp: now(), level: 'info', message: result.message || 'Bot started.' });
      updateControlButtons('running');
    }
  }

  async function stopBot() {
    const result = await api('/bot/stop', 'POST');
    if (result) {
      addLogEntry({ timestamp: now(), level: 'info', message: result.message || 'Bot stopped.' });
      updateControlButtons('stopped');
    }
  }

  async function pauseBot() {
    const result = await api('/bot/pause', 'POST');
    if (result) {
      addLogEntry({ timestamp: now(), level: 'info', message: result.message || 'Bot paused.' });
      updateControlButtons('paused');
    }
  }

  async function resumeBot() {
    const result = await api('/bot/resume', 'POST');
    if (result) {
      addLogEntry({ timestamp: now(), level: 'info', message: result.message || 'Bot resumed.' });
      updateControlButtons('running');
    }
  }

  function updateControlButtons(mode) {
    const btnStart = $('#btnStart');
    const btnPause = $('#btnPause');
    const btnStop = $('#btnStop');

    switch (mode) {
      case 'running':
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '⏸ Pause';
        btnPause.onclick = () => App.pauseBot();
        btnPause.className = 'btn btn-warning';
        btnStop.disabled = false;
        break;
      case 'paused':
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '▶ Resume';
        btnPause.onclick = () => App.resumeBot();
        btnPause.className = 'btn btn-success';
        btnStop.disabled = false;
        break;
      case 'stopped':
        btnStart.disabled = false;
        btnPause.disabled = true;
        btnPause.innerHTML = '⏸ Pause';
        btnPause.onclick = () => App.pauseBot();
        btnPause.className = 'btn btn-warning';
        btnStop.disabled = true;
        break;
    }
  }

  // ── Status Polling ─────────────────────────────────────
  function startStatusPolling() {
    statusPollId = setInterval(async () => {
      const status = await api('/bot/status');
      if (status) updateDashboard(status);

      const mbStatus = await api('/multibot/status');
      if (mbStatus) updateMultiBotDashboard(mbStatus);
    }, 1500);
  }

  function updateDashboard(status) {
    // Status badge
    const badge = $('#statusBadge');
    badge.dataset.state = status.state;

    const stateLabels = {
      idle: 'Idle',
      joining: 'Joining...',
      waiting: 'Loading Meeting...',
      active: 'Active',
      camera_live: 'Camera Live',
      paused: 'Paused',
      stopped: 'Stopped',
      error: 'Error',
    };
    $('#statusText').textContent = stateLabels[status.state] || status.state;

    // Metrics
    $('#metricElapsed').textContent = formatTime(status.elapsed || 0);
    $('#metricMessages').textContent = status.messages_sent || 0;

    // Camera
    $('#metricCamera').textContent = status.camera_on ? 'LIVE' : 'OFF';
    $('#metricCamera').className = `metric-value ${status.camera_on ? 'accent-green' : 'accent-cyan'}`;
    $('#metricCamSub').textContent = status.camera_on ? 'OBS Virtual Camera active' : 'Virtual camera feed';

    // Next action
    if (status.state === 'idle' || status.state === 'stopped') {
      $('#metricNextAction').textContent = '—';
      $('#metricNextLabel').textContent = 'Waiting to start';
    } else {
      const nextChat = status.next_chat_in || 0;
      const nextCam = status.next_cam_in || 0;

      if (!status.camera_on && nextCam > 0 && nextCam < nextChat) {
        $('#metricNextAction').textContent = formatTime(nextCam);
        $('#metricNextLabel').textContent = 'Until camera on';
      } else if (nextChat > 0) {
        $('#metricNextAction').textContent = formatTime(nextChat);
        $('#metricNextLabel').textContent = 'Until next chat';
      } else {
        $('#metricNextAction').textContent = '—';
        $('#metricNextLabel').textContent = 'Processing...';
      }
    }

    // Simulation badge
    $('#simBadge').style.display = status.simulation_mode ? 'flex' : 'none';

    // Update buttons based on state
    if (['active', 'camera_live', 'joining', 'waiting'].includes(status.state)) {
      updateControlButtons('running');
    } else if (status.state === 'paused') {
      updateControlButtons('paused');
    } else {
      updateControlButtons('stopped');
    }
  }

  // ── WebSocket ──────────────────────────────────────────
  function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws/logs`);

    ws.onopen = () => {
      $('#wsIndicator').style.background = 'var(--accent-green)';
      addLogEntry({ timestamp: now(), level: 'info', message: 'WebSocket connected — live log stream active.' });
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'log' && msg.data) {
          addLogEntry(msg.data);
        }
      } catch (e) { /* ignore */ }
    };

    ws.onclose = () => {
      $('#wsIndicator').style.background = 'var(--accent-red)';
      addLogEntry({ timestamp: now(), level: 'warn', message: 'WebSocket disconnected. Reconnecting in 3s...' });
      setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  // ── Log Console ────────────────────────────────────────
  function addLogEntry(entry) {
    const console = $('#logConsole');
    const el = document.createElement('div');
    el.className = 'log-entry';
    el.innerHTML = `
      <span class="log-time">${entry.timestamp || '--:--:--'}</span>
      <span class="log-level ${entry.level || 'info'}">${(entry.level || 'INFO').toUpperCase()}</span>
      <span class="log-msg">${escapeHtml(entry.message || '')}</span>
    `;
    console.appendChild(el);

    // Auto-scroll
    console.scrollTop = console.scrollHeight;

    // Limit visible entries
    while (console.children.length > 300) {
      console.removeChild(console.firstChild);
    }
  }

  async function clearLogs() {
    $('#logConsole').innerHTML = '';
    await api('/logs', 'DELETE');
    addLogEntry({ timestamp: now(), level: 'info', message: 'Logs cleared.' });
  }

  // ── Tab Switching ──────────────────────────────────────
  function switchTab(tabId) {
    $$('.tab').forEach(t => t.classList.remove('active'));
    $$('.tab-content').forEach(tc => tc.classList.remove('active'));

    $(`[data-tab="${tabId}"]`).classList.add('active');
    $(`#tab-${tabId}`).classList.add('active');
  }

  // ── Config → UI ────────────────────────────────────────
  function applyConfigToUI() {
    if (!config) return;

    const t = config.timing || {};
    setSliderVal('sliderMinChat', 'valMinChat', t.min_chat_interval, 's');
    setSliderVal('sliderMaxChat', 'valMaxChat', t.max_chat_interval, 's');
    setSliderVal('sliderMinCam', 'valMinCam', t.min_cam_delay, 's');
    setSliderVal('sliderMaxCam', 'valMaxCam', t.max_cam_delay, 's');
    setSliderVal('sliderJitter', 'valJitter', t.human_jitter, '');

    const e = config.execution || {};
    $('#toggleSkipJoin').checked = e.skip_join || false;
    $('#toggleAutoCamera').checked = e.auto_camera !== false;
    $('#toggleAutoChat').checked = e.auto_chat !== false;
    $('#toggleSimulation').checked = e.simulation_mode || false;

    // Mode
    setMode(e.mode || 'shortcut');

    // Coordinates
    const c = config.coordinates || {};
    if (c.join_button) { $('#coordJoinX').value = c.join_button.x; $('#coordJoinY').value = c.join_button.y; }
    if (c.chat_icon) { $('#coordChatX').value = c.chat_icon.x; $('#coordChatY').value = c.chat_icon.y; }
    if (c.camera_icon) { $('#coordCamX').value = c.camera_icon.x; $('#coordCamY').value = c.camera_icon.y; }
    if (c.chat_input) { $('#coordInputX').value = c.chat_input.x; $('#coordInputY').value = c.chat_input.y; }

    activePreset = config.active_preset || 'casual';
  }

  function setSliderVal(sliderId, labelId, value, suffix) {
    const slider = $(`#${sliderId}`);
    const label = $(`#${labelId}`);
    if (slider && value !== undefined) slider.value = value;
    if (label && value !== undefined) label.textContent = value + suffix;
  }

  // ── UI → Config ────────────────────────────────────────
  function collectConfig() {
    if (!config) config = {};

    config.timing = {
      min_chat_interval: parseInt($('#sliderMinChat').value),
      max_chat_interval: parseInt($('#sliderMaxChat').value),
      min_cam_delay: parseInt($('#sliderMinCam').value),
      max_cam_delay: parseInt($('#sliderMaxCam').value),
      typing_speed: 0.05,
      human_jitter: parseFloat($('#sliderJitter').value),
      mouse_move_duration: 0.3,
    };

    config.execution = {
      mode: $('#modeShortcut').classList.contains('active') ? 'shortcut' : 'coordinate',
      skip_join: $('#toggleSkipJoin').checked,
      auto_camera: $('#toggleAutoCamera').checked,
      auto_chat: $('#toggleAutoChat').checked,
      simulation_mode: $('#toggleSimulation').checked,
    };

    config.coordinates = {
      join_button: { x: int($('#coordJoinX').value), y: int($('#coordJoinY').value) },
      chat_icon: { x: int($('#coordChatX').value), y: int($('#coordChatY').value) },
      camera_icon: { x: int($('#coordCamX').value), y: int($('#coordCamY').value) },
      chat_input: { x: int($('#coordInputX').value), y: int($('#coordInputY').value) },
    };

    config.active_preset = activePreset;
    config.custom_messages = activeMessages;

    return config;
  }

  async function saveConfig() {
    const cfg = collectConfig();
    const result = await api('/config', 'POST', cfg);
    if (result) {
      addLogEntry({ timestamp: now(), level: 'info', message: 'Configuration saved.' });
    }
  }

  // ── Slider Updates ─────────────────────────────────────
  function updateSlider(name, value) {
    const map = {
      minChat: 'valMinChat',
      maxChat: 'valMaxChat',
      minCam: 'valMinCam',
      maxCam: 'valMaxCam',
      jitter: 'valJitter',
    };
    const suffix = name === 'jitter' ? '' : 's';
    $(`#${map[name]}`).textContent = value + suffix;
  }

  function updateToggle() {
    // Toggles update on save, no immediate side effects needed
    const simOn = $('#toggleSimulation').checked;
    $('#simBadge').style.display = simOn ? 'flex' : 'none';
  }

  // ── Execution Mode ─────────────────────────────────────
  function setMode(mode) {
    if (mode === 'shortcut') {
      $('#modeShortcut').classList.add('active');
      $('#modeCoordinate').classList.remove('active');
    } else {
      $('#modeShortcut').classList.remove('active');
      $('#modeCoordinate').classList.add('active');
    }
  }

  // ── Preset Grid ────────────────────────────────────────
  function renderPresetGrid() {
    const grid = $('#presetGrid');
    grid.innerHTML = '';

    Object.entries(presets).forEach(([key, preset]) => {
      const card = document.createElement('div');
      card.className = `preset-card ${key === activePreset ? 'active' : ''}`;
      card.onclick = () => selectPreset(key);
      card.innerHTML = `
        <div class="preset-card-name">${preset.name || key}</div>
        <div class="preset-card-desc">${preset.description || ''}</div>
        <div class="preset-card-count">${(preset.messages || []).length} msgs</div>
      `;
      grid.appendChild(card);
    });
  }

  function selectPreset(key) {
    activePreset = key;
    activeMessages = [...(presets[key]?.messages || [])];
    renderPresetGrid();
    renderMessageList();
    $('#activePresetName').textContent = `Preset: ${presets[key]?.name || key}`;
  }

  // ── Message List ───────────────────────────────────────
  function renderMessageList() {
    if (!activeMessages.length && presets[activePreset]) {
      activeMessages = [...(presets[activePreset]?.messages || [])];
    }

    const list = $('#messageList');
    list.innerHTML = '';

    if (!activeMessages.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">💬</div><p>No messages. Select a preset or add your own.</p></div>';
      return;
    }

    activeMessages.forEach((msg, i) => {
      const li = document.createElement('li');
      li.className = 'message-item';
      li.innerHTML = `
        <span class="msg-text">${escapeHtml(msg)}</span>
        <button class="msg-remove" onclick="App.removeMessage(${i})" title="Remove">✕</button>
      `;
      list.appendChild(li);
    });
  }

  function addMessage() {
    const input = $('#newMessageInput');
    const text = input.value.trim();
    if (!text) return;
    activeMessages.push(text);
    input.value = '';
    renderMessageList();
  }

  function removeMessage(index) {
    activeMessages.splice(index, 1);
    renderMessageList();
  }

  // ── Calibration ────────────────────────────────────────
  async function loadResPreset(res) {
    const data = await api('/calibrator/screen-presets');
    if (!data || !data[res]) return;

    const coords = data[res];
    if (coords.join_button) { $('#coordJoinX').value = coords.join_button.x; $('#coordJoinY').value = coords.join_button.y; }
    if (coords.chat_icon) { $('#coordChatX').value = coords.chat_icon.x; $('#coordChatY').value = coords.chat_icon.y; }
    if (coords.camera_icon) { $('#coordCamX').value = coords.camera_icon.x; $('#coordCamY').value = coords.camera_icon.y; }
    if (coords.chat_input) { $('#coordInputX').value = coords.chat_input.x; $('#coordInputY').value = coords.chat_input.y; }

    // Update active button
    $$('.res-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    addLogEntry({ timestamp: now(), level: 'info', message: `Loaded ${res} coordinate preset.` });
  }

  async function saveCoordinates() {
    await saveConfig();
  }

  // ── Mouse Tracker ──────────────────────────────────────
  function toggleMouseTracker() {
    if (isMouseTracking) {
      clearInterval(mouseTrackerId);
      isMouseTracking = false;
      $('#btnTrackMouse').innerHTML = '🔴 Start Tracking';
      $('#btnTrackMouse').className = 'btn btn-ghost';
      $('#mousePos').textContent = '—, —';
    } else {
      isMouseTracking = true;
      $('#btnTrackMouse').innerHTML = '⏹ Stop Tracking';
      $('#btnTrackMouse').className = 'btn btn-danger';
      mouseTrackerId = setInterval(async () => {
        const pos = await api('/calibrator/mouse-position');
        if (pos) {
          $('#mousePos').textContent = `${pos.x}, ${pos.y}`;
        }
      }, 200);
    }
  }

  // ── Utilities ──────────────────────────────────────────
  function formatTime(seconds) {
    const s = Math.floor(seconds);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  function now() {
    return new Date().toLocaleTimeString('en-US', { hour12: false });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function int(v) {
    return parseInt(v) || 0;
  }

  // ── Multi-Bot Configuration & Control ──────────────────
  const MULTI_PRESETS = {
    standard: { count: 5, chatMin: 15, chatMax: 45, joinMin: 5, joinMax: 15 },
    demo:     { count: 3, chatMin: 15, chatMax: 30, joinMin: 3, joinMax: 8 },
    crowd:    { count: 12, chatMin: 10, chatMax: 25, joinMin: 3, joinMax: 10 },
    webinar:  { count: 25, chatMin: 20, chatMax: 60, joinMin: 2, joinMax: 8 },
  };

  function updateMultiSlider(type, val) {
    val = parseInt(val) || 1;
    switch (type) {
      case 'count':
        if ($('#sliderMbCount')) $('#sliderMbCount').value = val;
        if ($('#numMbCount')) $('#numMbCount').value = val;
        if ($('#valMbCount')) $('#valMbCount').textContent = `${val} Bot${val > 1 ? 's' : ''}`;
        if ($('#btnFarmBotCount')) $('#btnFarmBotCount').textContent = val;
        break;
      case 'chatMin':
        if ($('#sliderMbChatMin')) $('#sliderMbChatMin').value = val;
        if ($('#valMbChatMin')) $('#valMbChatMin').textContent = `${val}s`;
        break;
      case 'chatMax':
        if ($('#sliderMbChatMax')) $('#sliderMbChatMax').value = val;
        if ($('#valMbChatMax')) $('#valMbChatMax').textContent = `${val}s`;
        break;
      case 'joinMin':
        if ($('#sliderMbJoinMin')) $('#sliderMbJoinMin').value = val;
        if ($('#valMbJoinMin')) $('#valMbJoinMin').textContent = `${val}s`;
        break;
      case 'joinMax':
        if ($('#sliderMbJoinMax')) $('#sliderMbJoinMax').value = val;
        if ($('#valMbJoinMax')) $('#valMbJoinMax').textContent = `${val}s`;
        break;
    }
  }

  function applyMultiPreset(name) {
    const p = MULTI_PRESETS[name];
    if (!p) return;
    updateMultiSlider('count', p.count);
    updateMultiSlider('chatMin', p.chatMin);
    updateMultiSlider('chatMax', p.chatMax);
    updateMultiSlider('joinMin', p.joinMin);
    updateMultiSlider('joinMax', p.joinMax);

    $$('.presets-quick-bar .btn-chip').forEach(b => b.classList.remove('active'));
    const btnId = `preset${name.charAt(0).toUpperCase() + name.slice(1)}`;
    const btn = $(`#${btnId}`);
    if (btn) btn.classList.add('active');
    addLogEntry({ timestamp: now(), level: 'info', message: `Applied '${name}' optimum preset.` });
  }

  async function pasteMeetingUrl() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        $('#mbMeetingUrl').value = text.trim();
        addLogEntry({ timestamp: now(), level: 'info', message: 'Pasted Zoom link from clipboard.' });
      }
    } catch (err) {
      const promptVal = prompt('Paste your Zoom Meeting link or ID:');
      if (promptVal) $('#mbMeetingUrl').value = promptVal.trim();
    }
  }

  async function startMultiBot() {
    const meetingUrl = $('#mbMeetingUrl').value.trim();
    if (!meetingUrl) {
      alert('Please enter or paste a valid Zoom meeting URL or ID!');
      $('#mbMeetingUrl').focus();
      return;
    }

    const customRaw = $('#mbCustomMessages').value.trim();
    const customMsgs = customRaw ? customRaw.split('\n').map(m => m.trim()).filter(Boolean) : [];

    const payload = {
      meeting_url: meetingUrl,
      bot_count: parseInt($('#sliderMbCount').value) || 5,
      chat_min: parseInt($('#sliderMbChatMin').value) || 15,
      chat_max: parseInt($('#sliderMbChatMax').value) || 45,
      join_delay_min: parseInt($('#sliderMbJoinMin').value) || 5,
      join_delay_max: parseInt($('#sliderMbJoinMax').value) || 15,
      auto_camera: $('#mbToggleCamera').checked,
      headless: $('#mbToggleHeadless').checked,
      per_bot_browser: $('#mbTogglePerBotBrowser').checked,
      custom_messages: customMsgs,
    };

    $('#btnLaunchFarm').disabled = true;
    $('#btnLaunchFarm').innerHTML = '⏳ Launching Farm...';

    const result = await api('/multibot/start', 'POST', payload);
    if (result && result.status === 'ok') {
      addLogEntry({ timestamp: now(), level: 'info', message: result.message });
      $('#btnLaunchFarm').disabled = true;
      $('#btnLaunchFarm').innerHTML = '🟢 Bot Farm Running';
      $('#btnStopFarm').disabled = false;
    } else {
      alert(result ? result.message : 'Failed to start multi-bot farm.');
      $('#btnLaunchFarm').disabled = false;
      $('#btnLaunchFarm').innerHTML = `🚀 Launch Bot Farm (${payload.bot_count} Bots)`;
    }
  }

  async function stopMultiBot() {
    const result = await api('/multibot/stop', 'POST');
    if (result) {
      addLogEntry({ timestamp: now(), level: 'info', message: result.message || 'Multi-bot farm stopped.' });
      $('#btnLaunchFarm').disabled = false;
      const cnt = parseInt($('#sliderMbCount').value) || 5;
      $('#btnLaunchFarm').innerHTML = `🚀 Launch Bot Farm (${cnt} Bots)`;
      $('#btnStopFarm').disabled = true;
    }
  }

  function getInitials(name) {
    if (!name) return 'B';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }

  function updateMultiBotDashboard(mbStatus) {
    const desc = $('#farmStatusDesc');
    const grid = $('#botFarmGrid');

    if (!mbStatus || !mbStatus.is_running) {
      if ($('#btnLaunchFarm') && $('#btnLaunchFarm').disabled && $('#btnLaunchFarm').innerHTML.includes('Running')) {
        $('#btnLaunchFarm').disabled = false;
        const cnt = $('#sliderMbCount') ? $('#sliderMbCount').value : 5;
        $('#btnLaunchFarm').innerHTML = `🚀 Launch Bot Farm (${cnt} Bots)`;
        if ($('#btnStopFarm')) $('#btnStopFarm').disabled = true;
      }
      if (desc) desc.textContent = 'No active bot farm running';
      if (grid && grid.querySelector('.empty-state') === null && (!mbStatus || !mbStatus.bots || !mbStatus.bots.length)) {
        grid.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">🤖</div>
            <div class="empty-title">Farm Idle</div>
            <div class="empty-desc">Enter meeting link and click <strong>Launch Bot Farm</strong> to start.</div>
          </div>`;
      }
      return;
    }

    // Active Farm Running!
    if ($('#btnLaunchFarm')) {
      $('#btnLaunchFarm').disabled = true;
      $('#btnLaunchFarm').innerHTML = '🟢 Bot Farm Running';
    }
    if ($('#btnStopFarm')) $('#btnStopFarm').disabled = false;

    if (desc) {
      desc.textContent = `🟢 ${mbStatus.active_count}/${mbStatus.bot_count} bots active — Elapsed: ${formatTime(mbStatus.elapsed)} — ${mbStatus.total_messages} messages sent`;
    }

    // Sync top metrics row when multibot is running
    if ($('#metricElapsed')) $('#metricElapsed').textContent = formatTime(mbStatus.elapsed);
    if ($('#metricMessages')) $('#metricMessages').textContent = mbStatus.total_messages;
    if ($('#metricNextAction')) $('#metricNextAction').textContent = `${mbStatus.active_count}/${mbStatus.bot_count} Active`;
    if ($('#metricNextLabel')) $('#metricNextLabel').textContent = 'Bot farm participants';
    const isCam = $('#mbToggleCamera') ? $('#mbToggleCamera').checked : true;
    if ($('#metricCamera')) {
      $('#metricCamera').textContent = isCam ? 'LIVE' : 'OFF';
      $('#metricCamera').className = `metric-value ${isCam ? 'accent-green' : 'accent-cyan'}`;
    }

    // Render bot grid cards
    if (grid && mbStatus.bots && mbStatus.bots.length) {
      grid.innerHTML = mbStatus.bots.map(b => `
        <div class="bot-card ${b.alive ? 'alive' : ''}">
          <div class="bot-avatar">${getInitials(b.name)}</div>
          <div class="bot-info">
            <div class="bot-name">${escapeHtml(b.name)}</div>
            <div class="bot-meta">
              <span>${b.alive ? '🟢 In Meeting' : '⚪ Idle'}</span>
              <span class="bot-msg-count">💬 ${b.msgs_sent}</span>
            </div>
          </div>
        </div>
      `).join('');
    }
  }

  // ── Boot ───────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  // ── Public API ─────────────────────────────────────────
  return {
    startBot,
    stopBot,
    pauseBot,
    resumeBot,
    startMultiBot,
    stopMultiBot,
    applyMultiPreset,
    updateMultiSlider,
    pasteMeetingUrl,
    switchTab,
    updateSlider,
    updateToggle,
    setMode,
    saveConfig,
    saveCoordinates,
    addMessage,
    removeMessage,
    loadResPreset,
    toggleMouseTracker,
    clearLogs,
  };
})();
