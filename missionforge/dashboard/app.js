/**
 * app.js — MissionForge Dashboard JavaScript
 *
 * Polls the MissionForge adapter REST API and updates the UI in real time.
 * No framework required — plain browser JavaScript.
 */

'use strict';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// In Docker Compose the adapter is accessible at http://localhost:8000
// In standalone mode, change this to the adapter URL.
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : `http://${window.location.hostname}:8000`;

const POLL_INTERVAL_MS = 1500;   // telemetry refresh
const ALERT_POLL_MS    = 2000;   // alert refresh
const STATUS_POLL_MS   = 3000;   // system status refresh
const HISTORY_LIMIT    = 20;     // rows shown in history table

// ---------------------------------------------------------------------------
// Telemetry range definitions for normalised bars and colour coding
// ---------------------------------------------------------------------------
const RANGES = {
  engine_temp:  { min: 150,  warn: 200,  crit: 220,  max: 300  },
  vibration:    { min: 0,    warn: 0.5,  crit: 0.75, max: 2.0  },
  fuel_flow:    { min: 60,   warn: 70,   crit: 60,   max: 100  },
  oil_pressure: { min: 0,    warn: 30,   crit: 25,   max: 60,  invert: true },
  cpu_usage:    { min: 0,    warn: 70,   crit: 85,   max: 100  },
  memory_usage: { min: 0,    warn: 70,   crit: 85,   max: 100  },
};

// Severity → colour map
const SEV_COLORS = {
  CRITICAL: '#ff2244',
  HIGH:     '#ff8800',
  MEDIUM:   '#ffcc00',
  LOW:      '#44aaff',
};

// ---------------------------------------------------------------------------
// Polling loops
// ---------------------------------------------------------------------------

let _connected = false;

function setConnected(ok) {
  if (_connected === ok) return;
  _connected = ok;
  const dot = document.getElementById('conn-indicator');
  dot.className = 'conn-dot ' + (ok ? 'connected' : 'disconnected');
  dot.title = ok ? 'Connected to adapter' : 'Cannot reach adapter';
}

async function fetchJSON(path) {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Telemetry latest
async function pollTelemetry() {
  try {
    const data = await fetchJSON('/telemetry/latest');
    setConnected(true);
    updateTelemetryCards(data);
    appendHistory(data);
  } catch {
    setConnected(false);
  }
  setTimeout(pollTelemetry, POLL_INTERVAL_MS);
}

// Alerts
async function pollAlerts() {
  try {
    const alerts = await fetchJSON('/alerts?limit=20');
    updateAlertsList(alerts);
  } catch { /* ignore */ }
  setTimeout(pollAlerts, ALERT_POLL_MS);
}

// Health
async function pollHealth() {
  try {
    const h = await fetchJSON('/health');
    updateHealthGauge(h);
  } catch { /* ignore */ }
  setTimeout(pollHealth, ALERT_POLL_MS);
}

// Status
async function pollStatus() {
  try {
    const s = await fetchJSON('/status');
    updateStatus(s);
  } catch { /* ignore */ }
  setTimeout(pollStatus, STATUS_POLL_MS);
}

// ---------------------------------------------------------------------------
// UI update helpers
// ---------------------------------------------------------------------------

function updateTelemetryCards(data) {
  const fields = ['engine_temp', 'vibration', 'fuel_flow', 'oil_pressure',
                  'cpu_usage', 'memory_usage'];
  for (const f of fields) {
    const val = data[f];
    if (val === undefined) continue;

    const tvEl = document.getElementById('tv-' + f);
    const tbEl = document.getElementById('tb-' + f);
    const tcEl = document.getElementById('tc-' + f);

    if (tvEl) tvEl.textContent = typeof val === 'number' ? val.toFixed(2) : val;

    const range = RANGES[f];
    if (!range || !tbEl) continue;

    const pct = Math.min(100, Math.max(0,
      ((val - range.min) / (range.max - range.min)) * 100));
    tbEl.style.width = pct + '%';

    // Colour coding
    let color = '#00ff88';
    const invert = range.invert;
    if (invert) {
      if (val <= range.crit) color = '#ff2244';
      else if (val <= range.warn) color = '#ff8800';
    } else {
      if (val >= range.crit) color = '#ff2244';
      else if (val >= range.warn) color = '#ff8800';
    }
    tbEl.style.background = color;
    if (tcEl) {
      tcEl.className = 'tcard';
      if (color === '#ff2244') tcEl.classList.add('alert-critical');
      else if (color === '#ff8800') tcEl.classList.add('alert-high');
    }
  }

  // Sensor status
  const ssEl = document.getElementById('tv-sensor_status');
  const ssTc = document.getElementById('tc-sensor_status');
  if (ssEl && data.sensor_status) {
    ssEl.textContent = data.sensor_status;
    ssTc.className = 'tcard';
    if (data.sensor_status === 'FAILED')   ssTc.classList.add('alert-critical');
    else if (data.sensor_status === 'DEGRADED') ssTc.classList.add('alert-high');
  }

  // Last update
  const lsEl = document.getElementById('sys-lastupdate');
  if (lsEl && data.timestamp) lsEl.textContent = data.timestamp.replace('T', ' ');
}

// ---------------------------------------------------------------------------
// Health gauge
// ---------------------------------------------------------------------------

function updateHealthGauge(health) {
  const score = Math.round(health.score);
  const arc   = document.getElementById('gauge-arc');
  const txt   = document.getElementById('gauge-text');
  const badge = document.getElementById('health-status');
  const meta  = document.getElementById('health-alerts');

  // Arc: total half-circle length = π × r = π × 80 ≈ 251.2
  const total  = 251.2;
  const offset = total * (1 - score / 100);
  arc.setAttribute('stroke-dashoffset', offset.toFixed(1));

  // Colour
  let color = '#00ff88';
  if (score < 50) color = '#ff2244';
  else if (score < 80) color = '#ff8800';
  arc.setAttribute('stroke', color);
  txt.setAttribute('fill', color);

  txt.textContent = score;
  badge.textContent = health.status;
  badge.className = 'status-badge ' + health.status.toLowerCase();
  meta.textContent = health.active_alert_count + ' active alert' +
    (health.active_alert_count !== 1 ? 's' : '');
}

// ---------------------------------------------------------------------------
// Alerts list
// ---------------------------------------------------------------------------

function updateAlertsList(alerts) {
  const container = document.getElementById('alerts-list');
  if (!alerts || alerts.length === 0) {
    container.innerHTML = '<div class="no-alerts">No active alerts — system nominal</div>';
    return;
  }
  container.innerHTML = alerts.slice(0, 10).map(a => {
    const color = SEV_COLORS[a.severity] || '#aaa';
    const signals = (a.contributing_signals || []).join(', ');
    return `
      <div class="alert-card" style="border-left-color:${color}">
        <div class="alert-header">
          <span class="alert-type" style="color:${color}">${a.alert_type}</span>
          <span class="alert-sev" style="background:${color}">${a.severity}</span>
          <span class="alert-ts">${a.timestamp.replace('T',' ')}</span>
        </div>
        <div class="alert-body">${a.explanation}</div>
        ${signals ? `<div class="alert-signals">Signals: ${signals}</div>` : ''}
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

const _historyRows = [];

function appendHistory(data) {
  _historyRows.unshift(data);
  if (_historyRows.length > HISTORY_LIMIT) _historyRows.pop();

  const tbody = document.getElementById('history-tbody');
  tbody.innerHTML = _historyRows.map(r => {
    const eng  = r.engine_temp.toFixed(1);
    const vib  = r.vibration.toFixed(3);
    const oil  = r.oil_pressure.toFixed(1);
    const fuel = r.fuel_flow.toFixed(1);
    const cpu  = r.cpu_usage.toFixed(1);
    const mem  = r.memory_usage.toFixed(1);
    const ts   = r.timestamp.replace('T',' ').replace('Z','');
    const ssCls = r.sensor_status === 'FAILED'   ? 'ss-failed' :
                  r.sensor_status === 'DEGRADED' ? 'ss-degraded' : 'ss-ok';
    return `<tr>
      <td>${ts}</td>
      <td>${eng}</td>
      <td>${vib}</td>
      <td>${oil}</td>
      <td>${fuel}</td>
      <td>${cpu}</td>
      <td>${mem}</td>
      <td><span class="${ssCls}">${r.sensor_status}</span></td>
    </tr>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Status panel
// ---------------------------------------------------------------------------

function updateStatus(s) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('sys-mode', s.mode ? s.mode.toUpperCase() : '—');
  set('sys-count', s.telemetry_count);
  set('sys-uptime', formatUptime(s.uptime_seconds));
  const faultEl = document.getElementById('sys-fault');
  if (faultEl) {
    faultEl.textContent = s.fault_active ? '⚠ YES' : 'No';
    faultEl.style.color = s.fault_active ? '#ff2244' : '#00ff88';
  }
}

function formatUptime(secs) {
  if (!secs) return '0s';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// ---------------------------------------------------------------------------
// Demo controls
// ---------------------------------------------------------------------------

async function injectFault() {
  const msg = document.getElementById('demo-msg');
  try {
    const r = await fetch(API_BASE + '/demo/inject-fault', { method: 'POST' });
    const d = await r.json();
    msg.textContent = '⚠ ' + d.message;
    msg.className = 'demo-msg warn';
  } catch (e) {
    msg.textContent = 'Error: ' + e.message;
    msg.className = 'demo-msg error';
  }
}

async function resetDemo() {
  const msg = document.getElementById('demo-msg');
  try {
    const r = await fetch(API_BASE + '/demo/reset', { method: 'POST' });
    const d = await r.json();
    msg.textContent = '✓ ' + d.message;
    msg.className = 'demo-msg ok';
    _historyRows.length = 0;
  } catch (e) {
    msg.textContent = 'Error: ' + e.message;
    msg.className = 'demo-msg error';
  }
}

// ---------------------------------------------------------------------------
// Kick off all polling loops on page load
// ---------------------------------------------------------------------------
window.addEventListener('DOMContentLoaded', () => {
  pollTelemetry();
  pollAlerts();
  pollHealth();
  pollStatus();
});
