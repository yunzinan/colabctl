// colabctl Dashboard Frontend (Vanilla ES Module, zero external dependencies)

import {
  applyStaticTranslations,
  detectInitialLang,
  localizeJobMessage,
  localizeJobStatus,
  localizeJobTitle,
  setLang,
  t,
  tHtml,
  toggleLang,
} from "./i18n.js";

const CFG = window.__COLABCTL_CONFIG__ || {
  token: "",
  version: "0.2.0",
  demoMode: false,
  defaultLang: "auto",
};

// Initialize language BEFORE stripping query params so ?lang=... is honored
setLang(detectInitialLang(CFG.defaultLang), { persist: false });

// Strip ?token=... / ?lang=... from address bar once cookie + config are loaded
if (window.location.search.includes("token=") || window.location.search.includes("lang=")) {
  try {
    window.history.replaceState(null, "", window.location.pathname);
  } catch (_) {}
}

const SINGLE_SHAPE_GPUS = new Set(["l4", "g4"]);

const state = {
  overview: null,
  tunnels: [],
  jobs: [],
  fetchedAtMs: Date.now(),
  sessionFetchedMs: {}, // name -> ms when watchdog_live was last fetched
  loadingLive: false,
  pollingTimer: null,
  healthTimer: null,
  backendDisconnected: false,
  disconnectReason: "",
  pollFailStreak: 0,
  syncStatus: { kind: "syncing", timeText: "" },
  knownRunningJobs: new Set(),
  dismissedJobs: new Set(),
  pendingConfirm: null,
  lastDoctorReport: null,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtCU(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtQuota(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const isInt = Math.abs(n - Math.round(n)) < 1e-6;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: isInt ? 0 : 2,
    maximumFractionDigits: isInt ? 0 : 2,
  });
}

function inferFallbackQuota(name, balance) {
  const lowered = String(name || "").trim().toLowerCase();
  if (/(ultra|20x|2500)/.test(lowered)) return 2500;
  if (/pro[\s._-]*(\+|plus)/.test(lowered)) return 500;
  if (/(^|[^a-z])pro([^a-z]|$|\d)/.test(lowered)) return 200;
  if (/(^|[^a-z])(free|payg)([^a-z]|$|\d)/.test(lowered)) return 100;
  if (balance !== null && balance !== undefined && Number.isFinite(Number(balance))) {
    const b = Number(balance);
    if (b > 1000) return 2500;
    if (b > 350) return 500;
    if (b > 120) return 200;
    return 100;
  }
  return 200;
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "—";
  const s = Math.max(0, Math.floor(Number(seconds)));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s`;
  if (m > 0) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
}

function fmtClock(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setSyncStatus(kind, timeText = "") {
  state.syncStatus = { kind, timeText };
  renderSyncStatus();
}

function renderSyncStatus() {
  const el = $("#sync-status");
  if (!el) return;
  const isDisc = state.backendDisconnected;
  el.classList.toggle("disconnected", isDisc);
  if (isDisc) {
    el.textContent =
      state.disconnectReason === "unauthorized"
        ? t("topbar.tokenExpired")
        : t("topbar.disconnected");
    return;
  }
  const { kind, timeText } = state.syncStatus;
  if (kind === "querying") el.textContent = t("topbar.queryingGoogle");
  else if (kind === "synced") el.textContent = t("topbar.syncedAt", { time: timeText });
  else if (kind === "error") el.textContent = t("topbar.syncError");
  else el.textContent = t("topbar.syncing");
}

async function api(path, options = {}) {
  const { silentDisconnect = false, ...fetchOpts } = options;
  const headers = {
    "X-Colabctl-Token": CFG.token,
    ...(fetchOpts.body ? { "Content-Type": "application/json" } : {}),
    ...(fetchOpts.headers || {}),
  };
  let resp;
  try {
    resp = await fetch(path, {
      ...fetchOpts,
      headers,
      body: fetchOpts.body ? JSON.stringify(fetchOpts.body) : undefined,
    });
  } catch (networkErr) {
    const err = new Error(t("err.networkUnreachable"));
    err.isNetworkError = true;
    err.cause = networkErr;
    if (!silentDisconnect) handleApiConnectionError(err);
    throw err;
  }
  let data = null;
  try {
    data = await resp.json();
  } catch (_) {}
  if (!resp.ok) {
    const msg = (data && (data.detail || data.error)) || `HTTP ${resp.status}`;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = resp.status;
    if (!silentDisconnect && resp.status === 401) handleApiConnectionError(err);
    throw err;
  }
  if (state.backendDisconnected) {
    setBackendDisconnected(false);
  }
  return data;
}

function setBackendDisconnected(disconnected, reason = "unreachable") {
  const changed =
    state.backendDisconnected !== disconnected ||
    (disconnected && state.disconnectReason !== reason);
  state.backendDisconnected = disconnected;
  state.disconnectReason = disconnected ? reason : "";
  if (!disconnected) {
    state.pollFailStreak = 0;
  }

  renderSyncStatus();
  renderDisconnectBanner();
  renderJobs();

  if (changed) {
    if (disconnected) {
      toast(
        reason === "unauthorized" ? t("toast.tokenExpired") : t("toast.disconnected"),
        "error",
        6500
      );
    } else {
      toast(t("toast.reconnected"), "success", 3000);
    }
  }
}

function renderDisconnectBanner() {
  const banner = $("#disconnect-banner");
  if (!banner) return;
  if (!state.backendDisconnected) {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");
  const titleEl = $("#disconnect-title");
  const subEl = $("#disconnect-sub");
  if (state.disconnectReason === "unauthorized") {
    titleEl.textContent = t("disconnect.tokenTitle");
    subEl.innerHTML = tHtml("disconnect.tokenBody");
  } else {
    titleEl.textContent = t("disconnect.unreachableTitle");
    subEl.innerHTML = tHtml("disconnect.unreachableBody");
  }
}

function handleApiConnectionError(err) {
  if (!err) return false;
  if (err.status === 401) {
    setBackendDisconnected(true, "unauthorized");
    return true;
  }
  if (err.isNetworkError) {
    setBackendDisconnected(true, "unreachable");
    return true;
  }
  return false;
}

async function checkBackendHealth({ force = false } = {}) {
  if (!force && state.pollingTimer && !state.backendDisconnected) {
    return;
  }
  const wasDisconnected = state.backendDisconnected;
  try {
    await api("/api/health");
    if (wasDisconnected) {
      await loadOverview({ live: false, probeGuard: false, autoProbeActive: true });
    }
  } catch (err) {
    handleApiConnectionError(err);
  }
}

function toast(message, kind = "info", durationMs = 3800) {
  const stack = $("#toast-stack");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.2s";
    setTimeout(() => el.remove(), 220);
  }, durationMs);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast(t("toast.copied", { text }), "success", 2200);
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    toast(t("toast.copied", { text }), "success", 2200);
  }
}

// ---------------------------------------------------------------------------
// Theme & Language
// ---------------------------------------------------------------------------

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("colabctl_theme", theme);
  const icon = $("#icon-theme");
  if (!icon) return;
  if (theme === "dark") {
    icon.innerHTML = `<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>`;
  } else {
    icon.innerHTML = `<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>`;
  }
}

function refreshLanguageUI() {
  applyStaticTranslations();
  renderSyncStatus();
  renderDisconnectBanner();
  syncHighMemOption("launch");
  syncHighMemOption("switch");
  if (state.overview) {
    renderAll();
  } else {
    renderJobs();
  }
  // Keep dynamic modal titles/doctor content translated if currently open
  if (!$("#modal-switch").classList.contains("hidden")) {
    const s = $("#switch-session").value;
    if (s) $("#modal-switch-title").textContent = t("modal.switch.titleNamed", { name: s });
  }
  if (!$("#modal-guard").classList.contains("hidden")) {
    const s = $("#guard-session").value;
    if (s) $("#modal-guard-title").textContent = t("modal.guard.titleNamed", { name: s });
  }
  if (!$("#modal-tunnel").classList.contains("hidden")) {
    const s = $("#tunnel-session").value;
    if (s) $("#modal-tunnel-title").textContent = t("modal.tunnel.titleNamed", { name: s });
  }
  if (!$("#modal-quota").classList.contains("hidden")) {
    const acc = $("#quota-account").value;
    if (acc) $("#modal-quota-title").textContent = t("modal.quota.titleNamed", { name: acc });
  }
  if (!$("#modal-doctor").classList.contains("hidden") && state.lastDoctorReport) {
    renderDoctorReport(state.lastDoctorReport);
  }
}

// ---------------------------------------------------------------------------
// Data Loading & Background Job Polling
// ---------------------------------------------------------------------------

async function loadOverview({ live = false, probeGuard = false, autoProbeActive = false } = {}) {
  const btnLive = $("#btn-refresh-live");
  const iconRefresh = $("#icon-refresh");
  if (live) {
    state.loadingLive = true;
    btnLive.disabled = true;
    iconRefresh.classList.add("spinning");
    setSyncStatus("querying");
  }
  try {
    const qs = new URLSearchParams({
      live: String(live),
      probe_guard: String(probeGuard),
    });
    const payload = await api(`/api/overview?${qs}`);
    state.overview = payload.overview;
    state.tunnels = payload.tunnels || [];
    state.jobs = payload.jobs || [];
    state.fetchedAtMs = Date.now();
    for (const s of state.overview.sessions || []) {
      if (s.watchdog_live) {
        state.sessionFetchedMs[s.name] = state.fetchedAtMs;
      }
    }
    const timeText = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setSyncStatus("synced", timeText);
    renderAll();
    syncJobPolling();

    // Background-probe live watchdogs for active sessions so timers appear automatically
    if (autoProbeActive && !probeGuard) {
      const toProbe = (state.overview.sessions || []).filter(
        (s) => !s.vanished && !s.watchdog_live
      );
      if (toProbe.length > 0) {
        Promise.allSettled(toProbe.map((s) => probeSingleSession(s.name, { silent: true })));
      }
    }
  } catch (err) {
    if (!handleApiConnectionError(err)) {
      toast(t("toast.loadFailed", { err: err.message }), "error");
      setSyncStatus("error");
    }
  } finally {
    if (live) {
      state.loadingLive = false;
      btnLive.disabled = false;
      iconRefresh.classList.remove("spinning");
    }
  }
}

async function probeSingleSession(name, { silent = false } = {}) {
  try {
    const view = await api(`/api/sessions/${encodeURIComponent(name)}/status`);
    if (state.overview && state.overview.sessions) {
      const idx = state.overview.sessions.findIndex((s) => s.name === name);
      if (idx >= 0) {
        state.overview.sessions[idx] = view;
        state.sessionFetchedMs[name] = Date.now();
        renderSessions();
      }
    }
    if (!silent) toast(t("toast.probeSuccess", { name }), "success", 2200);
  } catch (err) {
    if (!silent) toast(t("toast.probeFailed", { name, err: err.message }), "error");
  }
}

function trackSubmittedJob(job) {
  state.knownRunningJobs.add(job.id);
  const idx = state.jobs.findIndex((j) => j.id === job.id);
  if (idx >= 0) state.jobs[idx] = job;
  else state.jobs.unshift(job);
  renderJobs();
  syncJobPolling();
}

function syncJobPolling() {
  const running = state.jobs.filter((j) => j.status === "running");
  for (const j of running) state.knownRunningJobs.add(j.id);

  if (running.length > 0 && !state.pollingTimer) {
    state.pollingTimer = setInterval(pollJobs, 1500);
  } else if (running.length === 0 && state.pollingTimer) {
    clearInterval(state.pollingTimer);
    state.pollingTimer = null;
  }
}

async function pollJobs() {
  try {
    const latest = await api("/api/jobs", { silentDisconnect: true });
    state.pollFailStreak = 0;
    let finishedAny = false;
    for (const j of latest) {
      if (state.knownRunningJobs.has(j.id) && j.status !== "running") {
        state.knownRunningJobs.delete(j.id);
        finishedAny = true;
        const title = localizeJobTitle(j);
        if (j.status === "succeeded") {
          toast(t("toast.jobDone", { title }), "success", 4200);
        } else {
          toast(
            t("toast.jobFailed", { title, err: j.error || j.message }),
            "error",
            6500
          );
        }
      }
    }
    state.jobs = latest;
    renderJobs();
    syncJobPolling();
    if (finishedAny) {
      await loadOverview({ live: false, probeGuard: false, autoProbeActive: true });
    }
  } catch (err) {
    if (err && err.status === 401) {
      setBackendDisconnected(true, "unauthorized");
    } else if (err && err.isNetworkError) {
      state.pollFailStreak += 1;
      if (state.pollFailStreak >= 2) {
        setBackendDisconnected(true, "unreachable");
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderAll() {
  if (!state.overview) return;
  renderKpis();
  renderOrphans();
  renderAccounts();
  renderSessions();
  renderJobs();
  populateAccountSelects();
}

function localizedUsageMode(mode) {
  const m = (mode || "cached").toLowerCase();
  if (m === "live") return t("mode.live");
  if (m === "demo") return t("mode.demo");
  return t("mode.cached");
}

function renderKpis() {
  const ov = state.overview;
  const total = ov.total || {};
  const balEl = $("#kpi-balance");
  balEl.textContent = total.balance !== null && total.balance !== undefined ? `${fmtCU(total.balance)} CU` : "—";
  $("#kpi-accounts-meta").textContent = t("kpi.accountsMeta", {
    count: (ov.accounts || []).length,
    primary: ov.primary || t("kpi.unset"),
  });

  const rate = Number(total.hourly_rate || 0);
  const burnEl = $("#kpi-burn");
  burnEl.textContent = total.hourly_rate !== null && total.hourly_rate !== undefined ? `${fmtCU(rate)} CU/hr` : "—";
  burnEl.classList.toggle("burning", rate > 0);
  burnEl.classList.toggle("zero-burn", rate === 0);

  if (rate > 0 && total.hours_remaining) {
    $("#kpi-hours-meta").textContent = t("kpi.runway", { hours: Number(total.hours_remaining).toFixed(1) });
  } else if (rate === 0) {
    $("#kpi-hours-meta").textContent = t("kpi.allIdle");
  } else {
    $("#kpi-hours-meta").textContent = t("kpi.usageModeMeta", { mode: localizedUsageMode(ov.usage_mode) });
  }

  const sessions = ov.sessions || [];
  const activeCount = sessions.filter((s) => !s.vanished).length;
  const muxCount = sessions.filter((s) => s.ssh_mux_active).length;
  $("#kpi-sessions").textContent = String(activeCount);
  $("#kpi-mux-meta").textContent =
    activeCount > 0
      ? t("kpi.muxActive", { mux: muxCount, active: activeCount })
      : t("kpi.noActiveVms");

  const runningTunnels = state.tunnels.filter((tItem) => tItem.status === "running").length;
  $("#kpi-tunnels").textContent = String(runningTunnels);

  const modePill = $("#usage-mode-pill");
  modePill.textContent = localizedUsageMode(ov.usage_mode);
  modePill.className = `pill mono ${ov.usage_mode === "live" ? "pill-green" : "pill-muted"}`;

  // Disable Stop All if nothing running and no orphans
  const hasAnything = sessions.length > 0 || (ov.orphans || []).length > 0;
  $("#btn-stop-all").disabled = !hasAnything;
}

function renderOrphans() {
  const orphans = (state.overview && state.overview.orphans) || [];
  const banner = $("#orphan-banner");
  if (orphans.length === 0) {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");
  $("#orphan-list").innerHTML = orphans
    .map(
      (o) => `
      <div class="orphan-chip">
        <span class="mono"><strong>${esc(o.account)}</strong> · ${esc(o.endpoint)}</span>
        ${o.hardware ? `<span class="pill pill-red">${esc(o.hardware)}</span>` : ""}
        <button class="btn btn-danger-outline btn-xs" data-reap-account="${esc(o.account)}" data-reap-endpoint="${esc(o.endpoint)}">${esc(t("orphan.reap"))}</button>
      </div>`
    )
    .join("");
}

function renderAccounts() {
  const accounts = [...((state.overview && state.overview.accounts) || [])].sort((a, b) => {
    if (Boolean(a.primary) !== Boolean(b.primary)) return a.primary ? -1 : 1;
    return (Number(b.balance) || 0) - (Number(a.balance) || 0);
  });
  const grid = $("#accounts-grid");
  if (accounts.length === 0) {
    grid.innerHTML = `<div class="empty-inline">${tHtml("accounts.empty")}</div>`;
    return;
  }
  grid.innerHTML = accounts
    .map((a) => {
      const hasBalance = a.balance !== null && a.balance !== undefined && !Number.isNaN(Number(a.balance));
      const balance = hasBalance ? Number(a.balance) : null;
      const quota =
        Number(a.quota_cu) > 0 ? Number(a.quota_cu) : inferFallbackQuota(a.name, balance);
      const rawPct = hasBalance ? Math.round((balance / quota) * 100) : null;
      const hasExtra = hasBalance && balance > quota + 0.005;
      const extraCu = hasExtra ? balance - quota : 0;
      const isLow = hasBalance && rawPct <= 15;
      const rate = Number(a.hourly_rate || 0);
      const vms = a.assignments ?? a.pool_sessions ?? 0;
      const vmText = vms === 1 ? t("accounts.vmSingular", { count: vms }) : t("accounts.vmPlural", { count: vms });
      const baseColorCls = rate > 0 ? "amber" : isLow ? "red" : a.primary ? "" : "green";

      let barInnerHtml = "";
      if (hasExtra) {
        const baseSharePct = Math.max(25, Math.min(94, (quota / balance) * 100));
        const extraSharePct = Math.max(6, 100 - baseSharePct);
        barInnerHtml =
          `<div class="bar-fill has-rollover ${baseColorCls}" style="width: ${baseSharePct.toFixed(1)}%"></div>` +
          `<div class="bar-fill-rollover" style="width: ${extraSharePct.toFixed(1)}%"></div>`;
      } else {
        const fillPct =
          hasBalance && balance > 0 ? Math.min(100, Math.max(2, (balance / quota) * 100)) : 0;
        barInnerHtml = `<div class="bar-fill ${baseColorCls}" style="width: ${fillPct.toFixed(1)}%"></div>`;
      }

      const barTitle = hasBalance
        ? hasExtra
          ? t("accounts.quotaBarOverBaseTitle", {
              balance: fmtCU(balance),
              quota: fmtQuota(quota),
              pct: rawPct,
              extra: fmtCU(extraCu),
            })
          : t("accounts.quotaBarTitle", {
              balance: fmtCU(balance),
              quota: fmtQuota(quota),
              pct: rawPct,
            })
        : "";
      const editTitle =
        a.quota_source === "custom"
          ? t("accounts.quotaEditTitleCustom", { quota: fmtQuota(quota) })
          : t("accounts.quotaEditTitleAuto", { quota: fmtQuota(quota) });

      const cls = [
        "account-card",
        a.primary ? "is-primary" : "",
        a.disabled ? "is-disabled" : "",
      ].join(" ");
      return `
      <article class="${cls}">
        <div class="account-top">
          <div>
            <div class="account-name">
              <span>${esc(a.name)}</span>
              ${a.primary ? `<span class="pill pill-primary">${esc(t("accounts.primaryBadge"))}</span>` : ""}
            </div>
            <div class="account-email">${esc(a.email || "—")}</div>
          </div>
          <div class="account-badges">
            ${
              a.disabled
                ? `<span class="pill pill-red">${esc(t("accounts.disabled"))}</span>`
                : `<span class="pill pill-green"><span class="dot"></span>${esc(t("accounts.ready"))}</span>`
            }
          </div>
        </div>

        <div class="account-metrics">
          <div class="account-cu mono">${fmtCU(a.balance)} <small>CU</small></div>
          <div class="account-stats mono">
            <span title="${esc(t("accounts.hourlyRateTitle"))}">${fmtCU(rate)}/hr</span>
            <span>·</span>
            <span title="${esc(t("accounts.runningVmsTitle"))}">${esc(vmText)}</span>
          </div>
        </div>

        <div class="account-quota-wrap">
          <div class="bar-track" title="${esc(barTitle)}">
            ${barInnerHtml}
          </div>
          <div class="account-quota-row mono">
            <span class="account-quota-pct ${isLow ? "is-low" : ""}">
              <span>${hasBalance ? `${rawPct}%` : "—"}</span>
              ${
                hasExtra
                  ? `<span class="quota-rollover-tag">+${fmtCU(extraCu)} ${esc(t("accounts.overBase"))}</span>`
                  : ""
              }
            </span>
            <button type="button" class="quota-edit-btn mono" data-edit-quota="${esc(a.name)}" title="${esc(editTitle)}">
              <span>/ ${fmtQuota(quota)} CU</span>
              <svg viewBox="0 0 24 24" class="icon icon-edit" aria-hidden="true">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
            </button>
          </div>
        </div>

        <div class="account-actions">
          ${
            a.primary
              ? `<span class="muted" style="font-size:12px;">${esc(t("accounts.defaultForNew"))}</span>`
              : `<button class="btn btn-ghost btn-xs" data-set-primary="${esc(a.name)}">${esc(t("accounts.setPrimary"))}</button>`
          }
          <button class="btn btn-secondary btn-xs" data-launch-account="${esc(a.name)}">${esc(t("accounts.launchOn", { name: a.name }))}</button>
        </div>
      </article>`;
    })
    .join("");
}

function renderSessions() {
  const container = $("#sessions-container");
  const sessions = (state.overview && state.overview.sessions) || [];
  if (sessions.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" class="icon">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
        </div>
        <h3>${esc(t("sessions.emptyTitle"))}</h3>
        <p>${esc(t("sessions.emptyBody"))}</p>
        <div class="empty-actions">
          <button class="btn btn-primary" data-quick-launch="t4,false">${esc(t("sessions.quickT4"))}</button>
          <button class="btn btn-secondary" data-quick-launch="l4,false">${esc(t("sessions.quickL4"))}</button>
          <button class="btn btn-secondary" data-quick-launch="a100,true">${esc(t("sessions.quickA100"))}</button>
        </div>
      </div>`;
    return;
  }

  container.innerHTML = `<div class="sessions-grid">${sessions.map(renderSessionCard).join("")}</div>`;
  tickCountdowns();
}

function renderSessionCard(s) {
  const hw = s.hardware || {};
  const hasGbInName = hw.gpu_name && /\b\d+\s*gb\b/i.test(hw.gpu_name);
  const gpuTitle = hw.gpu_name
    ? `${hw.gpu_name}${hw.gpu_memory_mib && !hasGbInName ? ` · ${Math.round(hw.gpu_memory_mib / 1024)} GB` : ""}`
    : s.accelerator || "CPU";
  const ramCpu =
    hw.ram_total || hw.cpu_cores
      ? t("sessions.ramCpu", { ram: hw.ram_total || "?", cores: hw.cpu_cores || "?" })
      : t("sessions.probing");
  const wd = s.watchdog_live;
  const wc = s.watchdog_config;
  const sessionTunnels = state.tunnels.filter((tItem) => tItem.session === s.name && tItem.status === "running");

  let guardBadge = `<span class="pill pill-muted">${esc(t("guard.notProbed"))}</span>`;
  let idleHtml = `<span class="muted">${esc(t("guard.clickProbe"))}</span>`;
  let deadHtml = `<span class="muted">${esc(t("guard.clickProbe"))}</span>`;
  let guardMeta = t("guard.metaNotProbed");
  let gpuUtilHtml = "";

  if (wd) {
    if (wd.error) {
      guardBadge = `<span class="pill pill-red">${esc(t("guard.probeError"))}</span>`;
      guardMeta = wd.error;
    } else if (wd.cancelled || !wd.running) {
      guardBadge = `<span class="pill pill-amber">${esc(t("guard.offPill"))}</span>`;
      idleHtml = `<span class="muted">${esc(t("guard.disabled"))}</span>`;
      deadHtml = `<span class="muted">${esc(t("guard.disabled"))}</span>`;
      guardMeta = t("guard.metaPaused");
    } else {
      guardBadge = `<span class="pill pill-green"><span class="dot"></span>${esc(t("guard.activePill"))}</span>`;
      idleHtml =
        wd.remaining_idle_s !== null && wd.remaining_idle_s !== undefined
          ? `<span data-countdown-session="${esc(s.name)}" data-countdown-field="remaining_idle_s">${fmtDuration(wd.remaining_idle_s)}</span>`
          : `<span class="muted">${esc(t("guard.off"))}</span>`;
      deadHtml =
        wd.remaining_deadline_s !== null && wd.remaining_deadline_s !== undefined
          ? `<span data-countdown-session="${esc(s.name)}" data-countdown-field="remaining_deadline_s">${fmtDuration(wd.remaining_deadline_s)}</span>`
          : `<span class="muted">${esc(t("guard.off"))}</span>`;
      const gpuSuffix =
        wd.gpu_util_percent !== null && wd.gpu_util_percent !== undefined
          ? t("guard.metaGpuSuffix", { pct: Number(wd.gpu_util_percent).toFixed(0) })
          : "";
      guardMeta = t("guard.metaRunning", {
        pid: wd.pid || "?",
        reason: wd.last_active_reason || "ok",
        gpu: gpuSuffix,
      });
    }
    if (wd.gpu_util_percent !== null && wd.gpu_util_percent !== undefined) {
      gpuUtilHtml = t("sessions.gpuUtil", { pct: Number(wd.gpu_util_percent).toFixed(0) });
    }
  } else if (wc) {
    guardBadge = wc.enabled
      ? `<span class="pill pill-green">${esc(t("guard.configuredPill"))}</span>`
      : `<span class="pill pill-amber">${esc(t("guard.offPill"))}</span>`;
    idleHtml = wc.idle_timeout_s
      ? esc(t("guard.cfgMin", { min: Math.round(wc.idle_timeout_s / 60) }))
      : `<span class="muted">${esc(t("guard.off"))}</span>`;
    deadHtml = wc.max_duration_s
      ? esc(t("guard.cfgHrs", { hrs: (wc.max_duration_s / 3600).toFixed(1) }))
      : `<span class="muted">${esc(t("guard.off"))}</span>`;
    guardMeta = t("guard.metaCached");
  }

  return `
  <article class="session-card ${s.vanished ? "vanished" : ""}">
    <div class="session-head">
      <div class="session-title-wrap">
        <div class="session-name-row">
          <span class="session-name">${esc(s.name)}</span>
          <button class="ssh-copy-btn mono" data-copy="ssh ${esc(s.ssh_alias)}" title="${esc(t("sessions.copySshTitle"))}">
            <span>ssh ${esc(s.ssh_alias)}</span>
            <svg viewBox="0 0 24 24" class="icon icon-xs">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          </button>
        </div>
        <div class="session-meta-row mono">
          <span>${esc(t("sessions.accountPrefix"))} <strong>${esc(s.account)}</strong></span>
          ${s.endpoint ? `<span>· ${esc(s.endpoint)}</span>` : ""}
        </div>
      </div>

      <div class="session-pills">
        ${
          s.vanished
            ? `<span class="pill pill-red"><span class="dot"></span>${esc(t("sessions.vanished"))}</span>`
            : `<span class="pill pill-green"><span class="dot"></span>${esc(t("sessions.running"))}</span>`
        }
        ${
          s.ssh_mux_active
            ? `<span class="pill pill-primary" title="${esc(t("sessions.muxActiveTitle"))}">${esc(t("sessions.muxActivePill"))}</span>`
            : `<span class="pill pill-muted" title="${esc(t("sessions.muxIdleTitle"))}">${esc(t("sessions.muxIdlePill"))}</span>`
        }
      </div>
    </div>

    <div class="hw-strip">
      <div>
        <div class="hw-item-label">${esc(t("sessions.hwGpu"))}</div>
        <div class="hw-item-val" title="${esc(gpuTitle)}">${esc(gpuTitle)}</div>
      </div>
      <div>
        <div class="hw-item-label">${esc(t("sessions.hwSpec"))}</div>
        <div class="hw-item-val mono">${esc(ramCpu)}</div>
      </div>
      <div>
        <div class="hw-item-label">${esc(t("sessions.hwLoad"))}</div>
        <div class="hw-item-val mono">${esc(gpuUtilHtml || (hw.driver_version ? t("sessions.driver", { ver: hw.driver_version }) : "—"))}</div>
      </div>
    </div>

    <div class="guard-box">
      <div class="guard-top">
        <div class="action-group">
          <strong style="font-size:12.5px;">${esc(t("guard.title"))}</strong>
          ${guardBadge}
        </div>
        <div class="action-group">
          <button class="btn btn-ghost btn-xs" data-probe="${esc(s.name)}" title="${esc(t("guard.probeTitle"))}">${esc(t("guard.probeBtn"))}</button>
          <button class="btn btn-secondary btn-xs" data-extend="${esc(s.name)}" title="${esc(t("guard.extendTitle"))}">${esc(t("guard.extendBtn"))}</button>
          <button class="btn btn-secondary btn-xs" data-open-guard="${esc(s.name)}">${esc(t("guard.settingsBtn"))}</button>
        </div>
      </div>

      <div class="guard-timers">
        <div class="timer-cell">
          <div class="timer-label">${esc(t("guard.idleLabel"))}</div>
          <div class="timer-val mono">${idleHtml}</div>
        </div>
        <div class="timer-cell">
          <div class="timer-label">${esc(t("guard.deadlineLabel"))}</div>
          <div class="timer-val mono">${deadHtml}</div>
        </div>
      </div>

      <div class="guard-foot">
        <span class="mono">${esc(guardMeta)}</span>
      </div>
    </div>

    <div class="tunnels-row">
      <span class="muted" style="font-size:12px;">${esc(t("tunnels.label"))}</span>
      ${sessionTunnels
        .map(
          (tItem) => `
        <span class="tunnel-chip mono">
          <a href="${esc(tItem.url)}" target="_blank" rel="noopener">${esc(tItem.label)} :${esc(tItem.local_port)} ↗</a>
          <button class="tunnel-stop" data-stop-tunnel="${esc(tItem.id)}" title="${esc(t("tunnels.stopTitle"))}">×</button>
        </span>`
        )
        .join("")}
      <button class="btn btn-ghost btn-xs" data-open-tunnel="${esc(s.name)}">${esc(t("tunnels.add"))}</button>
    </div>

    <div class="session-actions">
      <div class="action-group">
        <button class="btn btn-primary btn-sm" data-open-terminal="${esc(s.name)}">
          <svg viewBox="0 0 24 24" class="icon icon-xs">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" y1="19" x2="20" y2="19" />
          </svg>
          <span>${esc(t("session.terminal"))}</span>
        </button>
        <button class="btn btn-secondary btn-sm" data-open-vscode="${esc(s.name)}">${esc(t("session.vscode"))}</button>
      </div>
      <div class="action-group">
        <button class="btn btn-secondary btn-sm" data-open-switch="${esc(s.name)}">${esc(t("session.switchGpu"))}</button>
        <button class="btn btn-ghost btn-sm" data-reset-ssh="${esc(s.name)}" title="${esc(t("session.resetSshTitle"))}">${esc(t("session.resetSsh"))}</button>
        <button class="btn btn-danger-outline btn-sm" data-stop-session="${esc(s.name)}">${esc(t("session.stop"))}</button>
      </div>
    </div>
  </article>`;
}

function renderJobs() {
  const jobs = state.jobs || [];
  $("#jobs-count-pill").textContent = String(jobs.length);

  // Active & recently failed jobs banner
  const activeBanner = $("#active-jobs-bar");
  const prominent = jobs.filter(
    (j) =>
      !state.dismissedJobs.has(j.id) &&
      (j.status === "running" || (j.status === "failed" && isRecent(j.finished_at, 120000)))
  );
  if (prominent.length === 0) {
    activeBanner.classList.add("hidden");
    activeBanner.innerHTML = "";
  } else {
    activeBanner.classList.remove("hidden");
    activeBanner.innerHTML = prominent
      .map((j) => {
        const title = localizeJobTitle(j);
        if (j.status === "running") {
          if (state.backendDisconnected) {
            return `
            <div class="job-live-row disconnected">
              <div class="job-live-left">
                <span class="pill pill-amber">${esc(t("jobs.disconnectedPill"))}</span>
                <div>
                  <strong>${esc(title)}</strong>
                  <div class="muted" style="font-size:12px;">${tHtml("jobs.disconnectedHint")}</div>
                </div>
              </div>
              <button class="btn btn-ghost btn-xs" data-dismiss-job="${esc(j.id)}">${esc(t("jobs.dismiss"))}</button>
            </div>`;
          }
          return `
          <div class="job-live-row">
            <div class="job-live-left">
              <div class="job-spinner"></div>
              <div>
                <strong>${esc(title)}</strong>
                <div class="muted" style="font-size:12px;">${esc(t("jobs.runningHint"))}</div>
              </div>
            </div>
            <span class="pill pill-primary mono" data-job-elapsed="${esc(j.started_at)}">0s</span>
          </div>`;
        }
        return `
        <div class="job-live-row failed">
          <div class="job-live-left">
            <span class="pill pill-red">${esc(t("jobs.failedPill"))}</span>
            <div>
              <strong>${esc(title)}</strong>
              <div class="muted" style="font-size:12px;">${esc(j.error || localizeJobMessage(j))}</div>
            </div>
          </div>
          <button class="btn btn-ghost btn-xs" data-dismiss-job="${esc(j.id)}">${esc(t("jobs.dismiss"))}</button>
        </div>`;
      })
      .join("");
  }

  // Drawer history
  const hist = $("#jobs-history");
  if (jobs.length === 0) {
    hist.innerHTML = `<div class="empty-inline">${esc(t("jobs.empty"))}</div>`;
    return;
  }
  hist.innerHTML = jobs
    .map((j) => {
      const pillCls =
        j.status === "succeeded" ? "pill-green" : j.status === "failed" ? "pill-red" : "pill-primary";
      return `
      <div class="job-item">
        <div>
          <div class="job-item-title">${esc(localizeJobTitle(j))}</div>
          <div class="job-item-msg">${esc(localizeJobMessage(j))}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">
          <span class="muted mono">${esc(fmtClock(j.started_at))}</span>
          <span class="pill ${pillCls}">${esc(localizeJobStatus(j.status))}</span>
        </div>
      </div>`;
    })
    .join("");
}

function isRecent(iso, windowMs) {
  if (!iso) return false;
  const tMs = new Date(iso).getTime();
  return !Number.isNaN(tMs) && Date.now() - tMs < windowMs;
}

function populateAccountSelects() {
  const accounts = (state.overview && state.overview.accounts) || [];
  const primary = (state.overview && state.overview.primary) || "";
  const opts = [
    `<option value="">${esc(t("common.autoPrimary", { primary: primary || t("common.none") }))}</option>`,
    ...accounts.map(
      (a) =>
        `<option value="${esc(a.name)}">${esc(a.name)} — ${fmtCU(a.balance)} CU${a.primary ? " ★" : ""}</option>`
    ),
  ].join("");
  for (const id of ["#launch-account", "#switch-account"]) {
    const sel = $(id);
    if (!sel) continue;
    const prev = sel.value;
    sel.innerHTML = opts;
    if (prev && accounts.some((a) => a.name === prev)) sel.value = prev;
  }
}

// ---------------------------------------------------------------------------
// 1-Second Live Countdown Ticker (no DOM rebuilds!)
// ---------------------------------------------------------------------------

function tickCountdowns() {
  if (state.backendDisconnected) return;
  const now = Date.now();
  if (state.overview && state.overview.sessions) {
    for (const s of state.overview.sessions) {
      const wd = s.watchdog_live;
      if (!wd || !wd.running || wd.cancelled) continue;
      const baseMs = state.sessionFetchedMs[s.name] || state.fetchedAtMs;
      const elapsedS = Math.max(0, (now - baseMs) / 1000);
      for (const field of ["remaining_idle_s", "remaining_deadline_s"]) {
        if (wd[field] === null || wd[field] === undefined) continue;
        const el = document.querySelector(
          `[data-countdown-session="${CSS.escape(s.name)}"][data-countdown-field="${field}"]`
        );
        if (!el) continue;
        const rem = Math.max(0, Number(wd[field]) - elapsedS);
        el.textContent = fmtDuration(rem);
        const parent = el.closest(".timer-val");
        if (parent) {
          parent.classList.toggle("urgent", rem <= 120);
          parent.classList.toggle("warn", rem > 120 && rem <= 600);
        }
      }
    }
  }

  for (const el of $$("[data-job-elapsed]")) {
    const started = new Date(el.getAttribute("data-job-elapsed")).getTime();
    if (!Number.isNaN(started)) {
      el.textContent = fmtDuration((now - started) / 1000);
    }
  }
}

// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------

function openModal(id) {
  $(id).classList.remove("hidden");
}

function closeAllModals() {
  for (const m of $$(".modal-backdrop")) m.classList.add("hidden");
  state.pendingConfirm = null;
}

function suggestSessionName() {
  const used = new Set(((state.overview && state.overview.sessions) || []).map((s) => s.name));
  if (!used.has("dev")) return "dev";
  for (let i = 2; i <= 20; i++) {
    const candidate = `gpu${i}`;
    if (!used.has(candidate)) return candidate;
  }
  return `gpu-${Math.floor(Math.random() * 900 + 100)}`;
}

function syncHighMemOption(kind) {
  const checked = $(`#${kind}-gpu-picker input[name="gpu"]:checked`);
  const gpu = (checked ? checked.value : "").toLowerCase();
  const cb = $(`#${kind}-high-mem`);
  const label = $(`#${kind}-high-mem-label`);
  const hint = $(`#${kind}-high-mem-hint`);
  if (!cb) return;

  const isSingleShape = SINGLE_SHAPE_GPUS.has(gpu);
  if (isSingleShape) {
    cb.checked = false;
    cb.disabled = true;
    if (label) label.classList.add("is-disabled");
    if (hint) {
      hint.textContent =
        gpu === "g4" ? t("modal.launch.highMemG4") : t("modal.launch.highMemL4");
    }
  } else {
    cb.disabled = false;
    if (label) label.classList.remove("is-disabled");
    if (hint) {
      hint.textContent =
        kind === "launch" ? t("modal.launch.highMemHint") : t("modal.switch.highMemHint");
    }
  }
}

function openLaunchModal({ account = "", gpu = "t4", highMem = false } = {}) {
  const suggested = suggestSessionName();
  $("#launch-name").value = suggested;
  $("#launch-alias-preview").textContent = `colab-${suggested}`;
  $("#launch-account").value = account;
  const radio = $(`#launch-gpu-picker input[value="${gpu}"]`);
  if (radio) radio.checked = true;
  $("#launch-high-mem").checked = Boolean(highMem) && !SINGLE_SHAPE_GPUS.has(gpu);
  syncHighMemOption("launch");
  $("#launch-enable-guard").checked = true;
  $("#launch-guard-fields").style.opacity = "1";
  openModal("#modal-launch");
  setTimeout(() => $("#launch-name").select(), 30);
}

function openSwitchModal(sessionName) {
  const s = (state.overview.sessions || []).find((x) => x.name === sessionName);
  $("#switch-session").value = sessionName;
  $("#modal-switch-title").textContent = t("modal.switch.titleNamed", { name: sessionName });
  $("#switch-account").value = (s && s.account) || "";
  $("#switch-high-mem").checked = false;
  syncHighMemOption("switch");
  openModal("#modal-switch");
}

function openGuardModal(sessionName) {
  const s = (state.overview.sessions || []).find((x) => x.name === sessionName);
  const wd = s && s.watchdog_live;
  const wc = s && s.watchdog_config;
  $("#guard-session").value = sessionName;
  $("#modal-guard-title").textContent = t("modal.guard.titleNamed", { name: sessionName });
  const isEnabled = wd ? wd.running && !wd.cancelled : wc ? wc.enabled : true;
  $("#guard-enabled").checked = Boolean(isEnabled);
  const idleS = (wd && wd.idle_timeout_s) ?? (wc && wc.idle_timeout_s) ?? 1800;
  $("#guard-idle-min").value = idleS ? Math.round(idleS / 60) : 0;
  $("#guard-max-hours").value = "";
  openModal("#modal-guard");
}

function openTunnelModal(sessionName) {
  $("#tunnel-session").value = sessionName;
  $("#modal-tunnel-title").textContent = t("modal.tunnel.titleNamed", { name: sessionName });
  $("#tunnel-remote-port").value = "8188";
  $("#tunnel-local-port").value = "";
  $("#tunnel-label").value = "ComfyUI";
  openModal("#modal-tunnel");
}

function openQuotaModal(accountName) {
  const acc = ((state.overview && state.overview.accounts) || []).find((x) => x.name === accountName);
  const currentQuota =
    acc && Number(acc.quota_cu) > 0
      ? Number(acc.quota_cu)
      : inferFallbackQuota(accountName, acc ? acc.balance : null);
  $("#quota-account").value = accountName;
  $("#modal-quota-title").textContent = t("modal.quota.titleNamed", { name: accountName });
  $("#quota-value").value = String(currentQuota);
  openModal("#modal-quota");
  setTimeout(() => $("#quota-value").select(), 30);
}

function confirmDanger({ title, message, buttonLabel = t("common.confirm"), onConfirm }) {
  $("#modal-confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  $("#btn-confirm-ok").textContent = buttonLabel;
  state.pendingConfirm = onConfirm;
  openModal("#modal-confirm");
}

function renderDoctorReport(rep) {
  const rows = [
    ...Object.entries(rep.binaries || {}).map(
      ([k, v]) => `
      <div class="diag-row">
        <strong class="mono">${esc(k)}</strong>
        <span class="diag-val mono ${v ? "" : "muted"}" title="${esc(v || t("modal.doctor.missing"))}">
          ${v ? `<span class="pill pill-green">${esc(t("modal.doctor.ok"))}</span> ${esc(v)}` : `<span class="pill pill-red">${esc(t("modal.doctor.missing"))}</span>`}
        </span>
      </div>`
    ),
    `<div class="diag-row"><strong>${esc(t("modal.doctor.sshKey"))}</strong><span class="diag-val mono">${rep.identity_file ? esc(rep.identity_file) : `<span class="pill pill-red">${esc(t("modal.doctor.missing"))}</span>`}</span></div>`,
    `<div class="diag-row"><strong>${esc(t("modal.doctor.sshInclude"))}</strong><span>${rep.ssh_config_included ? `<span class="pill pill-green">${esc(t("modal.doctor.configured"))}</span>` : `<span class="pill pill-amber">${esc(t("modal.doctor.pendingFirstUp"))}</span>`}</span></div>`,
    `<div class="diag-row"><strong>${esc(t("modal.doctor.accountsPool"))}</strong><span class="mono">${esc(t("modal.doctor.accountsVal", { count: rep.accounts_count, primary: rep.primary_account || t("kpi.unset") }))}</span></div>`,
  ];
  const issuesHtml = (rep.issues || []).length
    ? `<div class="notice notice-amber"><strong>${esc(t("modal.doctor.issues"))}</strong><ul style="margin:6px 0 0 18px;padding:0;">${rep.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`
    : `<div class="pill pill-green" style="align-self:flex-start;">${esc(t("modal.doctor.allHealthy"))}</div>`;
  $("#doctor-body").innerHTML = `${issuesHtml}<div class="diag-list">${rows.join("")}</div>`;
}

async function openDoctorModal() {
  openModal("#modal-doctor");
  $("#doctor-body").innerHTML = `<div class="empty-inline">${esc(t("modal.doctor.running"))}</div>`;
  try {
    const rep = await api("/api/doctor");
    state.lastDoctorReport = rep;
    renderDoctorReport(rep);
  } catch (err) {
    $("#doctor-body").innerHTML = `<div class="notice notice-amber">${esc(t("modal.doctor.failed", { err: err.message }))}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Event Wiring
// ---------------------------------------------------------------------------

function bindEvents() {
  if (CFG.demoMode) {
    $("#demo-badge").classList.remove("hidden");
  }

  // Theme
  const savedTheme = localStorage.getItem("colabctl_theme") || "dark";
  applyTheme(savedTheme);
  $("#btn-theme").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(cur === "dark" ? "light" : "dark");
  });

  // Language toggle (EN <-> 简体中文)
  $("#btn-lang").addEventListener("click", () => {
    toggleLang();
    refreshLanguageUI();
  });

  // Topbar buttons & disconnect retry
  $("#btn-retry-connection").addEventListener("click", () => checkBackendHealth({ force: true }));
  $("#btn-refresh-live").addEventListener("click", () =>
    loadOverview({ live: true, probeGuard: true })
  );
  $("#btn-refresh-cached").addEventListener("click", () =>
    loadOverview({ live: false, probeGuard: false, autoProbeActive: true })
  );
  $("#btn-doctor").addEventListener("click", openDoctorModal);
  $("#btn-launch").addEventListener("click", () => openLaunchModal());

  $("#btn-stop-all").addEventListener("click", () => {
    confirmDanger({
      title: t("confirm.stopAllTitle"),
      message: t("confirm.stopAllMsg"),
      buttonLabel: t("confirm.stopAllBtn"),
      onConfirm: async () => {
        const job = await api("/api/sessions/stop-all", { method: "POST" });
        trackSubmittedJob(job);
        toast(t("toast.stoppingAll"), "warn");
      },
    });
  });

  $("#btn-reap-all").addEventListener("click", () => {
    confirmDanger({
      title: t("confirm.reapAllTitle"),
      message: t("confirm.reapAllMsg"),
      buttonLabel: t("confirm.reapAllBtn"),
      onConfirm: async () => {
        const job = await api("/api/orphans/reap-all", { method: "POST" });
        trackSubmittedJob(job);
        toast(t("toast.reapingAll"), "warn");
      },
    });
  });

  // Confirm modal OK
  $("#btn-confirm-ok").addEventListener("click", async () => {
    const fn = state.pendingConfirm;
    closeAllModals();
    if (fn) {
      try {
        await fn();
      } catch (err) {
        toast(err.message, "error");
      }
    }
  });

  // Modal close buttons & backdrop click
  document.addEventListener("click", (e) => {
    if (e.target.matches("[data-close-modal]") || e.target.classList.contains("modal-backdrop")) {
      closeAllModals();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAllModals();
      return;
    }
    const tag = (e.target && e.target.tagName) || "";
    const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(tag);
    const anyModalOpen = $$(".modal-backdrop").some((m) => !m.classList.contains("hidden"));
    if (!inInput && !anyModalOpen) {
      if (e.key === "n") {
        e.preventDefault();
        openLaunchModal();
      } else if (e.key === "r") {
        e.preventDefault();
        loadOverview({ live: false, probeGuard: false, autoProbeActive: true });
      }
    }
  });

  // Launch & Switch modal GPU picker -> High-RAM eligibility sync
  $("#launch-gpu-picker").addEventListener("change", () => syncHighMemOption("launch"));
  $("#switch-gpu-picker").addEventListener("change", () => syncHighMemOption("switch"));

  // Launch modal live alias preview + guard toggle + presets
  $("#launch-name").addEventListener("input", (e) => {
    $("#launch-alias-preview").textContent = `colab-${e.target.value.trim() || "dev"}`;
  });
  $("#launch-enable-guard").addEventListener("change", (e) => {
    $("#launch-guard-fields").style.opacity = e.target.checked ? "1" : "0.45";
  });
  for (const chip of $$("[data-guard-preset]")) {
    chip.addEventListener("click", () => {
      const [idle, hrs] = chip.getAttribute("data-guard-preset").split(",");
      $("#launch-enable-guard").checked = true;
      $("#launch-guard-fields").style.opacity = "1";
      $("#launch-idle-min").value = idle;
      $("#launch-max-hours").value = hrs;
    });
  }

  // Tunnel modal presets
  for (const chip of $$("[data-tunnel-preset]")) {
    chip.addEventListener("click", () => {
      const [port, label] = chip.getAttribute("data-tunnel-preset").split(",");
      $("#tunnel-remote-port").value = port;
      $("#tunnel-local-port").value = "";
      $("#tunnel-label").value = label;
    });
  }

  // Quota modal presets & auto reset
  for (const chip of $$("[data-quota-preset]")) {
    chip.addEventListener("click", () => {
      $("#quota-value").value = chip.getAttribute("data-quota-preset");
    });
  }

  $("#btn-quota-auto").addEventListener("click", async () => {
    const account = $("#quota-account").value;
    if (!account) return;
    closeAllModals();
    try {
      const res = await api(`/api/accounts/${encodeURIComponent(account)}/quota`, {
        method: "POST",
        body: { quota_cu: null },
      });
      toast(t("toast.quotaReset", { account, quota: fmtQuota(res.quota_cu) }), "info");
      await loadOverview({ live: false, probeGuard: false });
    } catch (err) {
      toast(t("toast.quotaFailed", { err: err.message }), "error");
    }
  });

  $("#form-quota").addEventListener("submit", async (e) => {
    e.preventDefault();
    const account = $("#quota-account").value;
    const val = Number($("#quota-value").value);
    if (!account || !Number.isFinite(val) || val <= 0) return;
    closeAllModals();
    try {
      const res = await api(`/api/accounts/${encodeURIComponent(account)}/quota`, {
        method: "POST",
        body: { quota_cu: val },
      });
      toast(t("toast.quotaSaved", { account, quota: fmtQuota(res.quota_cu) }), "success");
      await loadOverview({ live: false, probeGuard: false });
    } catch (err) {
      toast(t("toast.quotaFailed", { err: err.message }), "error");
    }
  });

  // Form submissions
  $("#form-launch").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const gpu = String(fd.get("gpu") || "t4").toLowerCase();
    const body = {
      name: String(fd.get("name") || "").trim(),
      gpu,
      high_mem: !SINGLE_SHAPE_GPUS.has(gpu) && Boolean(fd.get("high_mem")),
      account: String(fd.get("account") || "") || null,
      enable_guard: Boolean(fd.get("enable_guard")),
      idle_min: Number(fd.get("idle_min") || 0),
      max_hours: Number(fd.get("max_hours") || 0),
    };
    closeAllModals();
    try {
      const job = await api("/api/sessions", { method: "POST", body });
      trackSubmittedJob(job);
      toast(t("toast.provisioning", { name: body.name, gpu: body.gpu.toUpperCase() }), "info");
    } catch (err) {
      if (!handleApiConnectionError(err)) {
        toast(t("toast.launchFailed", { err: err.message }), "error");
      }
    }
  });

  $("#form-switch").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const session = String(fd.get("session"));
    const gpu = String(fd.get("gpu") || "l4").toLowerCase();
    const body = {
      gpu,
      high_mem: !SINGLE_SHAPE_GPUS.has(gpu) && Boolean(fd.get("high_mem")),
      account: String(fd.get("account") || "") || null,
      idle_min: Number(fd.get("idle_min") || 0),
      max_hours: Number(fd.get("max_hours") || 0),
      enable_guard: true,
    };
    closeAllModals();
    try {
      const job = await api(`/api/sessions/${encodeURIComponent(session)}/switch`, {
        method: "POST",
        body,
      });
      trackSubmittedJob(job);
      toast(t("toast.switching", { name: session, gpu: body.gpu.toUpperCase() }), "warn");
    } catch (err) {
      if (!handleApiConnectionError(err)) {
        toast(t("toast.switchFailed", { err: err.message }), "error");
      }
    }
  });

  $("#form-guard").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const session = String(fd.get("session"));
    const enabled = Boolean(fd.get("enabled"));
    const maxRaw = String(fd.get("max_hours") || "").trim();
    const body = {
      idle_min: Number(fd.get("idle_min") || 0),
      max_hours: maxRaw === "" ? null : Number(maxRaw),
      enable: enabled,
      disable: !enabled,
    };
    closeAllModals();
    try {
      const wd = await api(`/api/sessions/${encodeURIComponent(session)}/guard`, {
        method: "POST",
        body,
      });
      updateSessionWatchdog(session, wd);
      toast(t("toast.guardUpdated", { name: session }), "success");
    } catch (err) {
      toast(t("toast.guardFailed", { err: err.message }), "error");
    }
  });

  $("#form-tunnel").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const lpRaw = String(fd.get("local_port") || "").trim();
    const body = {
      session: String(fd.get("session")),
      remote_port: Number(fd.get("remote_port")),
      local_port: lpRaw === "" ? null : Number(lpRaw),
      label: String(fd.get("label") || "").trim() || null,
    };
    closeAllModals();
    try {
      const tItem = await api("/api/tunnels", { method: "POST", body });
      state.tunnels = [...state.tunnels.filter((x) => x.id !== tItem.id), tItem];
      renderKpis();
      renderSessions();
      toast(
        t("toast.tunnelStarted", {
          url: tItem.url,
          session: tItem.session,
          port: tItem.remote_port,
        }),
        "success"
      );
    } catch (err) {
      toast(t("toast.tunnelFailed", { err: err.message }), "error", 5500);
    }
  });

  // Delegated click handlers across cards & banners
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;

    if (btn.dataset.copy) {
      copyText(btn.dataset.copy);
      return;
    }
    if (btn.dataset.dismissJob) {
      state.dismissedJobs.add(btn.dataset.dismissJob);
      renderJobs();
      return;
    }
    if (btn.dataset.quickLaunch) {
      const [gpu, highMem] = btn.dataset.quickLaunch.split(",");
      openLaunchModal({ gpu, highMem: highMem === "true" });
      return;
    }
    if (btn.dataset.launchAccount) {
      openLaunchModal({ account: btn.dataset.launchAccount });
      return;
    }
    if (btn.dataset.editQuota) {
      openQuotaModal(btn.dataset.editQuota);
      return;
    }
    if (btn.dataset.setPrimary) {
      const acc = btn.dataset.setPrimary;
      btn.disabled = true;
      try {
        await api("/api/accounts/primary", { method: "POST", body: { account: acc } });
        toast(t("toast.primarySet", { account: acc }), "success");
        await loadOverview({ live: false, probeGuard: false });
      } catch (err) {
        toast(t("toast.primaryFailed", { err: err.message }), "error");
        btn.disabled = false;
      }
      return;
    }
    if (btn.dataset.reapAccount && btn.dataset.reapEndpoint) {
      const account = btn.dataset.reapAccount;
      const endpoint = btn.dataset.reapEndpoint;
      btn.disabled = true;
      try {
        const job = await api("/api/orphans/reap", {
          method: "POST",
          body: { account, endpoint },
        });
        trackSubmittedJob(job);
        toast(t("toast.reapingOrphan", { endpoint, account }), "warn");
      } catch (err) {
        toast(t("toast.reapFailed", { err: err.message }), "error");
        btn.disabled = false;
      }
      return;
    }
    if (btn.dataset.probe) {
      const name = btn.dataset.probe;
      btn.disabled = true;
      await probeSingleSession(name);
      btn.disabled = false;
      return;
    }
    if (btn.dataset.extend) {
      const name = btn.dataset.extend;
      btn.disabled = true;
      try {
        const wd = await api(`/api/sessions/${encodeURIComponent(name)}/extend`, {
          method: "POST",
          body: { hours: 2.0 },
        });
        updateSessionWatchdog(name, wd);
        toast(t("toast.extended", { name }), "success");
      } catch (err) {
        toast(t("toast.extendFailed", { err: err.message }), "error");
      } finally {
        btn.disabled = false;
      }
      return;
    }
    if (btn.dataset.openGuard) {
      openGuardModal(btn.dataset.openGuard);
      return;
    }
    if (btn.dataset.openTunnel) {
      openTunnelModal(btn.dataset.openTunnel);
      return;
    }
    if (btn.dataset.stopTunnel) {
      const tid = btn.dataset.stopTunnel;
      btn.disabled = true;
      try {
        await api(`/api/tunnels/${encodeURIComponent(tid)}`, { method: "DELETE" });
        state.tunnels = state.tunnels.filter((x) => x.id !== tid);
        renderKpis();
        renderSessions();
        toast(t("toast.tunnelStopped"), "info", 2200);
      } catch (err) {
        toast(t("toast.tunnelStopFailed", { err: err.message }), "error");
      }
      return;
    }
    if (btn.dataset.openTerminal) {
      const name = btn.dataset.openTerminal;
      btn.disabled = true;
      try {
        const res = await api(`/api/sessions/${encodeURIComponent(name)}/open-terminal`, {
          method: "POST",
        });
        toast(
          res.demo
            ? t("toast.terminalDemo", { alias: res.ssh_alias })
            : t("toast.terminalOpened", { app: res.opened_in, alias: res.ssh_alias }),
          "success"
        );
      } catch (err) {
        toast(t("toast.terminalFailed", { err: err.message }), "error");
      } finally {
        btn.disabled = false;
      }
      return;
    }
    if (btn.dataset.openVscode) {
      const name = btn.dataset.openVscode;
      btn.disabled = true;
      try {
        const res = await api(`/api/sessions/${encodeURIComponent(name)}/open-vscode`, {
          method: "POST",
        });
        toast(
          res.demo
            ? t("toast.vscodeDemo", { alias: res.ssh_alias })
            : t("toast.vscodeOpened", { alias: res.ssh_alias }),
          "success"
        );
      } catch (err) {
        toast(t("toast.vscodeFailed", { err: err.message }), "error");
      } finally {
        btn.disabled = false;
      }
      return;
    }
    if (btn.dataset.openSwitch) {
      openSwitchModal(btn.dataset.openSwitch);
      return;
    }
    if (btn.dataset.resetSsh) {
      const name = btn.dataset.resetSsh;
      btn.disabled = true;
      btn.textContent = t("session.resetting");
      try {
        const res = await api(`/api/sessions/${encodeURIComponent(name)}/reset-ssh`, {
          method: "POST",
        });
        const cleared = (res.remote_sessions_terminated || []).length;
        toast(
          t("toast.resetSshDone", {
            name,
            count: cleared,
            rewarmed: res.rewarmed ? t("toast.resetSshRewarmed") : "",
          }),
          "success"
        );
        await loadOverview({ live: false, probeGuard: false });
      } catch (err) {
        toast(t("toast.resetSshFailed", { err: err.message }), "error");
      } finally {
        btn.disabled = false;
        btn.textContent = t("session.resetSsh");
      }
      return;
    }
    if (btn.dataset.stopSession) {
      const name = btn.dataset.stopSession;
      confirmDanger({
        title: t("confirm.stopSessionTitle", { name }),
        message: t("confirm.stopSessionMsg", { name }),
        buttonLabel: t("confirm.stopSessionBtn", { name }),
        onConfirm: async () => {
          const job = await api(`/api/sessions/${encodeURIComponent(name)}`, {
            method: "DELETE",
          });
          trackSubmittedJob(job);
          toast(t("toast.stoppingSession", { name }), "warn");
        },
      });
    }
  });
}

function updateSessionWatchdog(sessionName, wd) {
  if (!state.overview || !state.overview.sessions) return;
  const sess = state.overview.sessions.find((s) => s.name === sessionName);
  if (!sess) return;
  sess.watchdog_live = wd;
  state.sessionFetchedMs[sessionName] = Date.now();
  renderSessions();
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

bindEvents();
refreshLanguageUI();
setInterval(tickCountdowns, 1000);
state.healthTimer = setInterval(checkBackendHealth, 8000);
loadOverview({ live: false, probeGuard: false, autoProbeActive: true });
