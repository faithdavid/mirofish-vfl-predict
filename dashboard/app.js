// ═══════════════════════════════════════════════════════════════════════════════
// MIROFISH SOVEREIGN V7 — Dashboard App
// Clean architecture: single /api/data source, real EV, certainty_score unified
// ═══════════════════════════════════════════════════════════════════════════════

const LIVE_INTERVAL    = 5000;   // Dashboard live refresh
const HISTORY_INTERVAL = 15000;  // History tab refresh
const STATUS_INTERVAL  = 8000;   // Status bar refresh

let liveTimer    = null;
let historyTimer = null;

// ── Utility: format NGN ───────────────────────────────────────────────────────
function fmtNGN(val) {
    const abs = Math.abs(val || 0);
    const s   = abs.toLocaleString('en-NG', { minimumFractionDigits: 2 });
    return val >= 0 ? `+NGN ${s}` : `-NGN ${s}`;
}
function fmtMoney(val) {
    return `NGN ${Math.abs(val || 0).toLocaleString('en-NG', { minimumFractionDigits: 2 })}`;
}

// ── Utility: safe set innerText ───────────────────────────────────────────────
function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.innerText = val;
}
function setClass(id, cls) {
    const el = document.getElementById(id);
    if (el) el.className = cls;
}
function addRemClass(id, add, rem) {
    const el = document.getElementById(id);
    if (!el) return;
    if (rem) el.classList.remove(rem);
    if (add) el.classList.add(add);
}

// ── Prediction label ──────────────────────────────────────────────────────────
function predLabel(code) {
    return { H: 'HOME (1)', D: 'DRAW (X)', A: 'AWAY (2)' }[code] || code || '—';
}

// ── Tier badge HTML ───────────────────────────────────────────────────────────
function tierBadge(tier) {
    return `<span class="tier-badge tier-${tier || 'MOD'}">${tier || 'MOD'}</span>`;
}

// ── Certainty colour class ────────────────────────────────────────────────────
function certClass(cs) {
    if (cs >= 85) return 'cert-lock';
    if (cs >= 70) return 'cert-signal';
    if (cs >= 55) return 'cert-mod';
    return 'cert-weak';
}

// ── EV class ─────────────────────────────────────────────────────────────────
function evClass(ev) {
    if (ev > 0.02) return 'ev-positive';
    if (ev < 0)    return 'ev-negative';
    return 'ev-zero';
}


// ═══════════════════════════════════════════════════════════════════════════════
// LIVE DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════════
async function updateDashboard() {
    try {
        const [dataRes, statusRes] = await Promise.all([
            fetch('/api/data'),
            fetch('/api/status'),
        ]);
        const data   = await dataRes.json();
        const status = await statusRes.json();

        if (data.status !== 'success') return;

        const { season, matchday, pnl, wins, losses, strike_rate, fixtures,
                accounting, daemon } = data;

        // ── Top bar ───────────────────────────────────────────────────────────
        setText('hdr-md',     `MD ${matchday}`);
        setText('hdr-season', String(season).replace('vf:season:', '').slice(-8));
        setText('hdr-status', status.server || 'ONLINE');
        setText('hdr-pnl',    fmtMoney(pnl));
        addRemClass('hdr-pnl', pnl >= 0 ? 'positive' : 'negative', pnl >= 0 ? 'negative' : 'positive');

        const lastSync = daemon?.last_sync ? timeAgo(daemon.last_sync) : '—';
        setText('hdr-sync', lastSync);

        // Pulse dot
        const dot = document.getElementById('pulse-dot');
        if (dot) dot.className = daemon?.status === 'OFFLINE' ? 'pulse-dot offline' : 'pulse-dot';

        // ── Sidebar status ────────────────────────────────────────────────────
        const daemonEl = document.getElementById('ss-daemon');
        if (daemonEl) {
            daemonEl.innerText = daemon?.status || 'OFFLINE';
            daemonEl.className = `ss-val ${(daemon?.status === 'OFFLINE' || !daemon?.status) ? 'offline' : 'online'}`;
        }
        const authEl = document.getElementById('ss-auth');
        if (authEl) {
            authEl.innerText = status.auth || '?';
            authEl.className = `ss-val ${status.auth === 'ACTIVE' ? 'active' : 'offline'}`;
        }
        setText('ss-last-settle', daemon?.last_settle_md ? `MD ${daemon.last_settle_md}` : '—');

        // ── Stat row ──────────────────────────────────────────────────────────
        const pnlEl = document.getElementById('stat-pnl');
        if (pnlEl) {
            pnlEl.innerText = fmtMoney(pnl);
            pnlEl.className = `stat-val ${pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : ''}`;
        }
        setText('stat-strike',  `${strike_rate || 0}% strike rate`);
        setText('stat-wl',      `${wins} / ${losses}`);
        setText('stat-settled', `${wins + losses} settled`);
        setText('stat-md',      `MD ${matchday}`);
        setText('stat-season',  `SEASON ${String(season).slice(-6)}`);

        // Draw quota
        const draws       = accounting?.draws || 0;
        const targetDraws = accounting?.target_draws || 57.3;
        const drawPct     = Math.min(100, (draws / targetDraws) * 100);
        const qBar = document.getElementById('quota-bar');
        if (qBar) qBar.style.width = `${drawPct.toFixed(1)}%`;
        setText('quota-text',  `${draws} / ${targetDraws}`);
        setText('quota-force', `FORCE ${(accounting?.draw_force || 1).toFixed(2)}x`);

        // ── Command cards ─────────────────────────────────────────────────────
        const sorted   = [...(fixtures || [])].sort((a, b) => b.certainty_score - a.certainty_score);
        const topPicks = sorted.filter(f => f.stake > 0).slice(0, 2);

        topPicks.forEach((pick, i) => {
            const idx = i + 1;
            const tierMap = { LOCK: '🔒 LOCK', SIGNAL: '🟡 SIGNAL', MOD: '📊 MOD', WALL: '⚠️ WALL' };
            setText(`cmd-${idx}-tier`,    tierMap[pick.tier] || pick.tier);
            setText(`cmd-${idx}-fixture`, `${pick.home} vs ${pick.away}`);
            setText(`cmd-${idx}-pred`,    `${predLabel(pick.prediction)} | C: ${pick.certainty_score}%`);
            setText(`cmd-${idx}-odds`,    `@${(pick.target_odds || 0).toFixed(2)}`);
            setText(`cmd-${idx}-cert`,    `${pick.certainty_score}%`);
            setText(`cmd-${idx}-stake`,   `STAKE: NGN ${(pick.stake || 0).toLocaleString()}`);
            const evPct = ((pick.ev || 0) * 100).toFixed(1);
            setText(`cmd-${idx}-ev`, `EV: ${evPct > 0 ? '+' : ''}${evPct}%`);

            // Gold glow on LOCK
            const card = document.getElementById(`cmd-${idx}`);
            if (card) {
                card.className = `cmd-card ${pick.tier === 'LOCK' ? 'lock-glow' : ''}`;
            }
        });

        // ── EV Radar table ────────────────────────────────────────────────────
        renderRadar(sorted);

    } catch (e) {
        console.error('[DASHBOARD] Error:', e);
    }
}

function renderRadar(fixtures) {
    const body = document.getElementById('radar-body');
    if (!body) return;
    body.innerHTML = '';

    if (!fixtures || fixtures.length === 0) {
        body.innerHTML = '<div class="radar-empty">No fixture data. Daemon may be initialising...</div>';
        return;
    }

    fixtures.forEach(f => {
        const cs   = f.certainty_score || 0;
        const ev   = f.ev || 0;
        const row  = document.createElement('div');
        row.className = 'radar-row';

        const matchId = f.match_id || `${f.home}_${f.away}`;
        const predHtml = `<span class="pred-badge pred-${f.prediction}">${predLabel(f.prediction)}</span>`;
        const certHtml = `<span class="cert-cell ${certClass(cs)}">${cs}%</span>`;
        const evPct    = (ev * 100).toFixed(1);
        const evHtml   = `<span class="${evClass(ev)}">${ev > 0 ? '+' : ''}${evPct}%</span>`;

        row.innerHTML = `
            <span class="fixture-name">${f.home} vs ${f.away}</span>
            <span>${predHtml} ${tierBadge(f.tier)}</span>
            ${certHtml}
            <span style="font-family:var(--mono)">${(f.target_odds || 0).toFixed(2)}</span>
            ${evHtml}
            <span style="font-family:var(--mono)">NGN ${(f.stake || 0).toLocaleString()}</span>
            <div class="settle-btns">
                <button class="btn-win"  data-mid="${matchId}" onclick="manualSettle('${matchId}','win',this)">W</button>
                <button class="btn-loss" data-mid="${matchId}" onclick="manualSettle('${matchId}','loss',this)">L</button>
            </div>
        `;
        body.appendChild(row);
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// HISTORY TAB
// ═══════════════════════════════════════════════════════════════════════════════
async function loadHistory() {
    try {
        const res  = await fetch('/api/history');
        const data = await res.json();

        setText('hist-strike', `${data.strike_rate || 0}%`);
        const hpnl = document.getElementById('hist-pnl');
        if (hpnl) {
            hpnl.innerText = fmtMoney(data.total_pnl || 0);
            hpnl.className = `stat-val ${(data.total_pnl || 0) >= 0 ? 'positive' : 'negative'}`;
        }
        setText('hist-wl',    `${data.wins || 0}W / ${data.losses || 0}L`);
        setText('hist-count', `${data.total || 0} settled bets`);

        // Best tier
        const lockWins = (data.history || []).filter(h => (h.profit || 0) > 0 && h.tier === 'LOCK').length;
        setText('hist-tier', lockWins > 0 ? `LOCK (${lockWins}W)` : 'SIGNAL');

        // Pending section
        renderPending(data.pending || []);

        // Settled section
        renderSettled(data.history || []);

    } catch (e) {
        console.error('[HISTORY]', e);
    }
}

function renderPending(pending) {
    const body = document.getElementById('pending-body');
    if (!body) return;
    body.innerHTML = '';
    if (pending.length === 0) {
        body.innerHTML = '<div class="radar-empty">No pending predictions.</div>';
        return;
    }
    pending.forEach(p => {
        const row = document.createElement('div');
        row.className = 'pending-row';
        row.innerHTML = `
            <span class="fixture-name">${p.fixture}</span>
            <span>MD ${p.matchday}</span>
            <span><span class="pred-badge pred-${p.prediction}">${predLabel(p.prediction)}</span></span>
            <span style="font-family:var(--mono)">${(p.odds || 0).toFixed(2)}</span>
            <span style="font-family:var(--mono)">NGN ${p.stake || 0}</span>
        `;
        body.appendChild(row);
    });
}

function renderSettled(settled) {
    const body = document.getElementById('hist-body');
    if (!body) return;
    body.innerHTML = '';
    if (settled.length === 0) {
        body.innerHTML = '<div class="radar-empty">No settled bets yet. Predictions appear here once matched.</div>';
        return;
    }
    settled.forEach(h => {
        const won     = (h.profit || 0) > 0;
        const row     = document.createElement('div');
        row.className = `hist-row ${won ? 'win-row' : 'loss-row'}`;
        const outcomeHtml = h.outcome
            ? `<span class="outcome-${won ? 'win' : 'loss'}">${h.outcome}</span>`
            : `<span class="outcome-pending">N/A</span>`;
        const profitColor = won ? 'var(--green)' : 'var(--red)';
        const profitSign  = (h.profit || 0) >= 0 ? '+' : '';
        row.innerHTML = `
            <span class="fixture-name">${h.fixture}</span>
            <span>MD ${h.matchday}</span>
            <span><span class="pred-badge pred-${h.prediction}">${predLabel(h.prediction)}</span></span>
            ${outcomeHtml}
            <span style="font-family:var(--mono)">${(h.odds || 0).toFixed(2)}</span>
            <span style="font-family:var(--mono)">NGN ${h.stake || 0}</span>
            <span style="font-family:var(--mono);color:${profitColor};font-weight:700">
                ${profitSign}NGN ${Math.abs(h.profit || 0).toFixed(2)}
            </span>
        `;
        body.appendChild(row);
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// MANUAL SETTLE
// ═══════════════════════════════════════════════════════════════════════════════
async function manualSettle(matchId, outcome, btn) {
    btn.parentElement.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    try {
        await fetch('/api/score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ matchId, outcome }),
        });
        setTimeout(updateDashboard, 1000);
    } catch (e) { console.error('[SETTLE]', e); }
}


// ═══════════════════════════════════════════════════════════════════════════════
// MANUAL INJECTION
// ═══════════════════════════════════════════════════════════════════════════════
document.getElementById('btn-predict')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-predict');
    const raw = document.getElementById('odds-input')?.value.trim();
    if (!raw) return;

    btn.disabled = true; btn.innerText = '⏳ PROCESSING...';
    try {
        const res  = await fetch('/api/predict', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: raw,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'API error');

        renderRadar([...(data.fixtures || [])].sort((a, b) => b.certainty_score - a.certainty_score));
        showInjectOutput('✅ Prediction Complete', data);
        btn.innerText = '✓ SUCCESS';
        setTimeout(() => { btn.innerText = '⚡ DECODE & PREDICT'; btn.disabled = false; }, 30000);
    } catch (e) {
        alert('Error: ' + e.message);
        btn.innerText = '⚡ DECODE & PREDICT'; btn.disabled = false;
    }
});

document.getElementById('btn-audit')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-audit');
    const raw = document.getElementById('results-input')?.value.trim();
    if (!raw) return alert('Paste Results JSON first!');

    btn.disabled = true; btn.innerText = '⏳ SETTLING...';
    try {
        const res  = await fetch('/api/audit', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: raw,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Audit error');

        showInjectOutput('✅ Audit Complete', {
            settled: data.settled_count,
            matchday: data.matchday,
            profit: data.total_profit,
        });
        btn.innerText = '✓ SETTLED';
        document.getElementById('results-input').value = '';
        setTimeout(() => { btn.innerText = '📥 SETTLE MATCHDAY'; btn.disabled = false; updateDashboard(); }, 4000);
    } catch (e) {
        alert('Audit Error: ' + e.message);
        btn.innerText = '📥 SETTLE MATCHDAY'; btn.disabled = false;
    }
});

function showInjectOutput(title, data) {
    const el = document.getElementById('inject-output');
    if (!el) return;
    el.style.display = 'block';
    setText('inject-out-title', title);
    document.getElementById('inject-out-body').innerText = JSON.stringify(data, null, 2);
}


// ═══════════════════════════════════════════════════════════════════════════════
// AUTH UPDATE
// ═══════════════════════════════════════════════════════════════════════════════
document.getElementById('btn-auth')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-auth');
    const raw = document.getElementById('auth-input')?.value.trim();
    if (!raw) return alert('Paste header/cookie JSON first!');
    btn.disabled = true; btn.innerText = '⏳ UPDATING...';
    try {
        const payload = JSON.parse(raw);
        const res = await fetch('/api/sync/auth', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('Auth failed');
        btn.innerText = '✓ AUTH UPDATED';
        setTimeout(() => { btn.innerText = '🔐 UPDATE AUTH'; btn.disabled = false; }, 4000);
    } catch (e) {
        alert('Error: ' + e.message);
        btn.innerText = '🔐 UPDATE AUTH'; btn.disabled = false;
    }
});


// ═══════════════════════════════════════════════════════════════════════════════
// SUPABASE STATUS CHECK (settings page)
// ═══════════════════════════════════════════════════════════════════════════════
async function checkSupabase() {
    try {
        const res  = await fetch('/api/sync/status');
        const data = await res.json();
        const el   = document.getElementById('set-supabase');
        if (el) { el.innerText = data.status; el.className = `mono ${data.status === 'ACTIVE' ? '' : 'danger'}`; }
    } catch {}
}


// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════════
function initNav() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const view = link.getAttribute('data-view');

            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            link.classList.add('active');
            document.getElementById(`view-${view}`)?.classList.add('active');

            // Start/stop appropriate timers
            clearInterval(historyTimer);
            historyTimer = null;

            if (view === 'history') {
                loadHistory();
                historyTimer = setInterval(loadHistory, HISTORY_INTERVAL);
            } else if (view === 'settings') {
                checkSupabase();
            }
        });
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// TIME AGO helper
// ═══════════════════════════════════════════════════════════════════════════════
function timeAgo(iso) {
    if (!iso) return '—';
    const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (secs < 5)   return 'now';
    if (secs < 60)  return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
}


// ═══════════════════════════════════════════════════════════════════════════════
// BOOT
// ═══════════════════════════════════════════════════════════════════════════════
initNav();
updateDashboard();
liveTimer = setInterval(updateDashboard, LIVE_INTERVAL);
