/* dashboard.js — Live polling and DOM updates for the main dashboard */

const POLL_INTERVAL = 5000; // 5 seconds

// ── Polling ──────────────────────────────────────────────────────────────────

async function fetchStatus() {
  try {
    const [statusRes, activityRes] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/activity'),
    ]);
    const status   = await statusRes.json();
    const activity = await activityRes.json();
    updateDashboard(status, activity);
  } catch (e) {
    // Network error — dashboard will retry on next poll
  }
}

// Start polling immediately and repeat
fetchStatus();
setInterval(fetchStatus, POLL_INTERVAL);

// ── Dashboard update ──────────────────────────────────────────────────────────

function updateDashboard(status, activity) {
  updateBotStatus(status.engine);
  updateCounts(status.counts);
  updateSystemStatus(status);
  updateAlerts(status.alerts || []);
  updateActivity(activity);
  updateSessionInfo(status.engine);
}

function updateBotStatus(engine) {
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  const detail = document.getElementById('status-detail');
  const btnStart  = document.getElementById('btn-start');
  const btnStop   = document.getElementById('btn-stop');
  const btnResume = document.getElementById('btn-resume');

  const s = engine.status;

  // Dot colour
  dot.className = 'status-dot ' + (
    s === 'RUNNING' ? 'dot-green' :
    s === 'PAUSED'  ? 'dot-red'   :
    s === 'ERROR'   ? 'dot-red'   : 'dot-grey'
  );

  // Status label
  const labels = { RUNNING: 'Running', STOPPED: 'Stopped', PAUSED: 'Paused — Action Required', ERROR: 'Error' };
  label.textContent = labels[s] || s;

  // Detail line
  if (s === 'RUNNING') {
    const next = engine.next_scan_in != null ? `Next scan in ${engine.next_scan_in}s` : '';
    const dr   = engine.dry_run ? ' · Dry Run ON' : '';
    detail.textContent = `Cycle #${engine.cycle_count}  ·  Last: ${engine.last_cycle_at || '—'}  ·  ${next}${dr}`;
  } else if (s === 'PAUSED') {
    detail.textContent = `${engine.consecutive_failures} consecutive failures. Check alerts.`;
  } else {
    detail.textContent = '—';
  }

  // Buttons
  btnStart.style.display  = (s === 'STOPPED') ? 'inline-flex' : 'none';
  btnStop.style.display   = (s === 'RUNNING') ? 'inline-flex' : 'none';
  btnResume.style.display = (s === 'PAUSED')  ? 'inline-flex' : 'none';
  btnStart.textContent   = engine.dry_run ? '▶ Start Bot (Dry Run)' : '▶ Start Bot (Live)';

  // Dry run toggle and badge
  const drToggle = document.getElementById('dash-dry-run');
  const drLabel  = document.getElementById('dash-dry-run-label');
  if (drToggle && document.activeElement !== drToggle) {
    drToggle.checked = Boolean(engine.dry_run);
  }
  if (drLabel) {
    drLabel.textContent = engine.dry_run ? 'Dry Run (Safe)' : 'Live Mode';
    drLabel.style.color = engine.dry_run ? 'var(--yellow)' : 'var(--green)';
  }

  const drBadge = document.getElementById('dry-run-badge');
  if (drBadge) {
    drBadge.style.display = 'inline-block';
    drBadge.className = 'badge ' + (engine.dry_run ? 'badge-yellow' : 'badge-green');
    drBadge.textContent = engine.dry_run ? 'DRY RUN' : 'LIVE';
  }
}

function updateCounts(counts) {
  if (!counts) return;
  setText('count-flagged', counts.flagged  ?? 0);
  setText('count-pending', counts.pending  ?? 0);
  setText('count-failed',  counts.failed   ?? 0);
  setText('count-error',   (counts.error   ?? 0) + (counts.gone ?? 0));
}

function updateSystemStatus(status) {
  // Outlook
  const outlookBadge  = document.getElementById('outlook-status-badge');
  const reloginBtn    = document.getElementById('btn-relogin');
  const outStatus     = status.outlook_status;

  if (outlookBadge) {
    const classes = { ACTIVE: 'badge-green', EXPIRED: 'badge-red', UNKNOWN: 'badge-grey' };
    const labels  = { ACTIVE: '🟢 Active', EXPIRED: '🔴 Session Expired', UNKNOWN: '⚪ Unknown' };
    outlookBadge.className = 'badge ' + (classes[outStatus] || 'badge-grey');
    outlookBadge.textContent = labels[outStatus] || outStatus;
  }
  if (reloginBtn) reloginBtn.style.display = outStatus === 'EXPIRED' ? 'inline-flex' : 'none';

  // Portal token
  const tokenBadge = document.getElementById('portal-token-badge');
  if (tokenBadge) {
    const hasToken   = status.portal_token_set;
    const hasExpired = (status.alerts || []).some(a => a.title && a.title.includes('Token'));
    tokenBadge.className = 'badge ' + (hasToken && !hasExpired ? 'badge-green' : 'badge-red');
    tokenBadge.textContent = hasToken && !hasExpired ? '🟢 Active' : '🔴 Expired / Not Set';
  }

  // Last scan
  const lastScan = document.getElementById('last-scan');
  if (lastScan && status.engine.last_cycle_at) {
    lastScan.textContent = `Last scan: ${status.engine.last_cycle_at}`;
  }
}

function updateAlerts(alerts) {
  const panel = document.getElementById('alerts-panel');
  if (!panel) return;

  if (!alerts.length) {
    panel.style.display = 'none';
    return;
  }

  panel.style.display = 'flex';
  panel.innerHTML = alerts.map(a => `
    <div class="alert-item alert-${a.urgency === 'critical' ? 'critical' : 'normal'}">
      <span class="alert-icon">${a.urgency === 'critical' ? '🔴' : '🟡'}</span>
      <div class="alert-body">
        <div class="alert-title">${escHtml(a.title)}</div>
        <div class="alert-msg">${escHtml(a.message)}</div>
      </div>
      <button class="alert-dismiss" onclick="dismissAlert(${a.id})" title="Dismiss">✕</button>
    </div>
  `).join('');
}

function updateActivity(items) {
  const feed = document.getElementById('activity-feed');
  if (!feed) return;

  if (!items || !items.length) {
    feed.innerHTML = '<div class="activity-empty">Waiting for first scan…</div>';
    return;
  }

  const icons = {
    FLAGGED:              '✅',
    DRY_RUN_WOULD_FLAG:   '🏳',
    FLAGGED_AFTER_RETRY:  '✅',
    CONFIRMED:            '🔔',
    PENDING:              '⏳',
    STILL_PENDING:        '⏳',
    DISCOVERED:           '🔍',
    FAILED:               '❌',
    EMAIL_GONE:           '🗑',
    FLAG_ERROR:           '⚠',
    OUTLOOK_SESSION_EXPIRED: '🔐',
    PORTAL_TOKEN_EXPIRED: '🔑',
    OUTLOOK_NETWORK_ERROR:'📡',
    PORTAL_NETWORK_ERROR: '📡',
    BOT_STARTED:          '▶',
    BOT_STOPPED:          '⏹',
    CYCLE_ERROR:          '⚠',
  };

  feed.innerHTML = items.map(item => {
    const icon    = icons[item.event] || '•';
    const track   = item.tracking ? item.tracking : (item.event.replace(/_/g,' '));
    const detail  = item.detail  || '';
    return `
      <div class="activity-item">
        <span class="activity-ts">${escHtml(item.ts)}</span>
        <span class="activity-icon">${icon}</span>
        <span class="activity-track">${escHtml(track)}</span>
        <span class="activity-detail">${escHtml(detail)}</span>
      </div>
    `;
  }).join('');
}

function updateSessionInfo(engine) {
  const el = document.getElementById('session-time');
  if (el && engine.session_duration) {
    el.textContent = `Session: ${engine.session_duration}`;
  }
}

// ── Bot control ───────────────────────────────────────────────────────────────

async function toggleDashDryRun(checked) {
  const drLabel = document.getElementById('dash-dry-run-label');
  const btnStart = document.getElementById('btn-start');
  const drBadge = document.getElementById('dry-run-badge');

  if (drLabel) {
    drLabel.textContent = checked ? 'Dry Run (Safe)' : 'Live Mode';
    drLabel.style.color = checked ? 'var(--yellow)' : 'var(--green)';
  }
  if (btnStart) {
    btnStart.textContent = checked ? '▶ Start Bot (Dry Run)' : '▶ Start Bot (Live)';
  }
  if (drBadge) {
    drBadge.className = 'badge ' + (checked ? 'badge-yellow' : 'badge-green');
    drBadge.textContent = checked ? 'DRY RUN' : 'LIVE';
  }

  try {
    await fetch('/api/bot/dry-run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dry_run: checked })
    });
  } catch (e) {
    console.error('Failed to update dry run mode:', e);
  }
  setTimeout(fetchStatus, 300);
}

async function startBot() {
  const drToggle = document.getElementById('dash-dry-run');
  if (drToggle) {
    try {
      await fetch('/api/bot/dry-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: drToggle.checked })
      });
    } catch (e) {
      // non-fatal
    }
  }
  await fetch('/api/bot/start', { method: 'POST' });
  setTimeout(fetchStatus, 500);
}

async function stopBot() {
  if (!confirm('Stop the bot? Any pending emails will be re-discovered on next start.')) return;
  await fetch('/api/bot/stop', { method: 'POST' });
  setTimeout(fetchStatus, 500);
}

async function resumeBot() {
  await fetch('/api/bot/resume', { method: 'POST' });
  setTimeout(fetchStatus, 500);
}

async function relogin() {
  const res = await fetch('/api/relogin', { method: 'POST' });
  const data = await res.json();
  alert(data.message || 'Re-login started. A browser window will open.');
}

// ── Token management ──────────────────────────────────────────────────────────

function showTokenPanel() {
  const panel = document.getElementById('token-panel');
  if (panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

async function testToken() {
  const token  = document.getElementById('token-input').value.trim();
  const result = document.getElementById('token-result');
  if (!token) { result.textContent = '⚠ Please paste a token first.'; result.className = 'token-result error'; return; }
  result.textContent = '⏳ Testing token…'; result.className = 'token-result';
  const res  = await fetch('/api/token/test', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({token}) });
  const data = await res.json();
  result.textContent = (data.valid ? '✅ ' : '❌ ') + data.message;
  result.className   = 'token-result ' + (data.valid ? 'success' : 'error');
}

async function saveToken() {
  const token  = document.getElementById('token-input').value.trim();
  const result = document.getElementById('token-result');
  if (!token) { result.textContent = '⚠ Please paste a token first.'; result.className = 'token-result error'; return; }
  const res  = await fetch('/api/token/save', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({token}) });
  const data = await res.json();
  result.textContent = (data.success ? '✅ ' : '❌ ') + data.message;
  result.className   = 'token-result ' + (data.success ? 'success' : 'error');
  if (data.success) setTimeout(fetchStatus, 800);
}

async function dismissAlert(id) {
  await fetch('/api/alerts/dismiss', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({id}) });
  fetchStatus();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
