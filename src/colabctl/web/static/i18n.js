// Zero-dependency bilingual i18n (English & Simplified Chinese) for colabctl Dashboard

export const SUPPORTED_LANGS = ["en", "zh-CN"];

export const MESSAGES = {
  en: {
    "page.title": "colabctl — GPU Control Plane",
    "brand.subtitle": "Multi-Account Colab GPU Pool · Multiplexed SSH · VM Cost Guard",
    "brand.demoBadge": "DEMO MODE · 0 CU",

    "topbar.syncing": "Syncing...",
    "topbar.queryingGoogle": "Querying Google...",
    "topbar.syncedAt": "Synced {time}",
    "topbar.syncError": "Sync error",
    "topbar.disconnected": "Disconnected",
    "topbar.tokenExpired": "Token expired",
    "topbar.syncTitle": "Last overview refresh",
    "topbar.refreshLive": "Refresh Live",
    "topbar.refreshLiveTitle": "Fetch live Compute Units from Google & probe VM watchdogs",
    "topbar.doctor": "Doctor",
    "topbar.doctorTitle": "Environment diagnostics (colabctl doctor)",
    "topbar.themeTitle": "Toggle Dark / Light theme",
    "topbar.langLabel": "EN",
    "topbar.langTitle": "Switch language to 简体中文",
    "topbar.stopAll": "Stop All",
    "topbar.stopAllTitle": "Stop EVERY VM and orphan across all accounts",
    "topbar.launch": "Launch GPU",

    "disconnect.unreachableTitle": "Local colabctl ui Server Disconnected",
    "disconnect.unreachableBody":
      "The local backend process has stopped (this standalone Chrome window stays open independently). Background jobs and live timers are paused — run <code>colabctl ui</code> in your terminal for a fresh session, or check cloud VMs with <code>colabctl ls --live</code>.",
    "disconnect.tokenTitle": "Session Token Expired (colabctl ui Restarted)",
    "disconnect.tokenBody":
      "A new <code>colabctl ui</code> server is running with a different local security token. Close this stale window and use the newly opened window or URL printed in your terminal.",
    "disconnect.retry": "Retry Connection",

    "kpi.balanceLabel": "Total Compute Units",
    "kpi.loadingAccounts": "Loading accounts...",
    "kpi.accountsMeta": "{count} accounts · Primary: {primary}",
    "kpi.unset": "unset",
    "kpi.burnLabel": "Live Burn Rate",
    "kpi.runway": "~{hours} hrs runway across pool",
    "kpi.allIdle": "All idle — 0.00 CU/hr billing",
    "kpi.usageModeMeta": "Usage mode: {mode}",
    "kpi.sessionsLabel": "Active GPU Sessions",
    "kpi.muxReady": "ControlMaster SSH ready",
    "kpi.muxActive": "{mux}/{active} ControlMaster mux active",
    "kpi.noActiveVms": "No active VMs",
    "kpi.tunnelsLabel": "Active Tunnels",
    "kpi.tunnelsMeta": "Shared SSH mux · 0 HTTP 429",

    "orphan.title": "Unmanaged Orphan VMs Detected — Still Billing Compute Units!",
    "orphan.sub": "These Colab runtimes exist outside colab-pool tracking. Reap them to stop silent charges.",
    "orphan.reapAll": "Reap All Orphans",
    "orphan.reap": "Reap",

    "accounts.title": "Account Pool",
    "accounts.sub": "Automatic failover chooses the Primary account unless you pin a specific account.",
    "accounts.empty":
      "No Google accounts found. Run <code>colab-account add &lt;alias&gt;</code> in your terminal.",
    "accounts.primaryBadge": "★ Primary",
    "accounts.ready": "Ready",
    "accounts.disabled": "Disabled",
    "accounts.hourlyRateTitle": "Hourly burn rate",
    "accounts.runningVmsTitle": "Running VMs",
    "accounts.vmSingular": "{count} VM",
    "accounts.vmPlural": "{count} VMs",
    "accounts.quotaBarTitle": "{balance} / {quota} CU ({pct}% of account baseline)",
    "accounts.quotaBarOverBaseTitle": "{balance} / {quota} CU ({pct}% — +{extra} CU above baseline; may include rollover, top-up, or a higher plan)",
    "accounts.overBase": "over base",
    "accounts.quotaEditTitleAuto": "Account quota baseline: {quota} CU (auto-detected). Click to customize.",
    "accounts.quotaEditTitleCustom": "Account quota baseline: {quota} CU (custom). Click to edit.",
    "accounts.defaultForNew": "Default for new GPUs",
    "accounts.setPrimary": "Set Primary",
    "accounts.launchOn": "+ Launch on {name}",

    "mode.cached": "cached",
    "mode.live": "live",
    "mode.demo": "demo",

    "sessions.title": "Managed GPU Sessions",
    "sessions.sub": "Each session runs a detached VM cost-guard watchdog and a pre-warmed ControlMaster SSH channel.",
    "sessions.quickSync": "Quick Sync",
    "sessions.quickSyncTitle": "Quick local/cached refresh",
    "sessions.emptyTitle": "All Clear — Zero Compute Units Burning",
    "sessions.emptyBody":
      "No active Colab GPU runtimes are running right now. Launch a session with one click — SSH multiplexing and the VM cost-guard watchdog are configured automatically.",
    "sessions.quickT4": "Launch T4 (16 GB · Budget)",
    "sessions.quickL4": "Launch L4 (24 GB)",
    "sessions.quickA100": "Launch A100 High-RAM",
    "sessions.accountPrefix": "account:",
    "sessions.copySshTitle": "Copy SSH command",
    "sessions.vanished": "Vanished",
    "sessions.running": "Running",
    "sessions.muxActivePill": "Mux Active",
    "sessions.muxActiveTitle": "OpenSSH ControlMaster socket is warm — instant multi-terminal & tunnels",
    "sessions.muxIdlePill": "Mux Idle",
    "sessions.muxIdleTitle": "ControlMaster connects on first SSH",
    "sessions.hwGpu": "GPU Hardware",
    "sessions.hwSpec": "Host Spec",
    "sessions.hwLoad": "GPU Load / Driver",
    "sessions.probing": "Probing...",
    "sessions.ramCpu": "{ram} RAM · {cores} vCPU",
    "sessions.gpuUtil": "{pct}% util",
    "sessions.driver": "Driver {ver}",

    "guard.title": "VM Cost Guard",
    "guard.notProbed": "Not Probed",
    "guard.probeError": "Probe Error",
    "guard.offPill": "Guard Off",
    "guard.activePill": "Guard Active",
    "guard.configuredPill": "Configured",
    "guard.clickProbe": "Click Probe",
    "guard.disabled": "Disabled",
    "guard.off": "Off",
    "guard.cfgMin": "{min}m cfg",
    "guard.cfgHrs": "{hrs}h cfg",
    "guard.metaNotProbed": "VM watchdog status not probed yet.",
    "guard.metaPaused": "Watchdog is paused — remember to stop manually to save CU!",
    "guard.metaCached": "Cached policy — click Probe for exact VM countdown.",
    "guard.metaRunning": "PID {pid} · Last activity: {reason}{gpu}",
    "guard.metaGpuSuffix": " · GPU {pct}%",
    "guard.probeBtn": "Probe",
    "guard.probeTitle": "Query live watchdog & GPU utilization from VM",
    "guard.extendBtn": "+2h Extend",
    "guard.extendTitle": "Add +2 hours to hard deadline & reset idle timer",
    "guard.settingsBtn": "Settings",
    "guard.idleLabel": "Idle Auto-Stop In",
    "guard.deadlineLabel": "Hard Deadline In",

    "tunnels.label": "Port Forwards:",
    "tunnels.add": "+ Forward Port",
    "tunnels.stopTitle": "Stop tunnel",

    "session.terminal": "Terminal",
    "session.vscode": "VS Code",
    "session.switchGpu": "Switch GPU",
    "session.resetSsh": "Reset SSH",
    "session.resetting": "Resetting...",
    "session.resetSshTitle": "Recover from stale SSH / HTTP 429",
    "session.stop": "Stop",

    "jobs.drawerTitle": "Activity & Background Jobs",
    "jobs.empty": "No background jobs recorded in this UI session yet.",
    "jobs.runningHint": "Running in background — Colab allocation typically takes 10–30s.",
    "jobs.disconnectedPill": "Disconnected",
    "jobs.disconnectedHint":
      "Local <code>colabctl ui</code> server is unreachable — job status can no longer be tracked here. Run <code>colabctl ls --live</code> or restart <code>colabctl ui</code>.",
    "jobs.failedPill": "Failed",
    "jobs.dismiss": "Dismiss",
    "jobs.status.running": "running",
    "jobs.status.succeeded": "succeeded",
    "jobs.status.failed": "failed",
    "jobs.title.up": "Provisioning '{target}' ({gpu}{highMem})",
    "jobs.title.switch": "Switching '{target}' to {gpu}{highMem}",
    "jobs.title.stop": "Stopping '{target}' and ending billing",
    "jobs.title.stop-all": "Stopping ALL VMs across every account",
    "jobs.title.reap": "Reaping orphan {endpoint} on {account}",
    "jobs.title.reap-all": "Reaping all unmanaged orphan VMs",
    "jobs.highMemSuffix": " High-RAM",
    "jobs.msg.running": "{title}...",
    "jobs.msg.completed": "{title} completed.",

    "common.cancel": "Cancel",
    "common.close": "Close",
    "common.confirm": "Confirm",
    "common.autoPrimary": "Auto (Primary: {primary})",
    "common.none": "none",

    "modal.launch.title": "Launch GPU Session",
    "modal.launch.sessionName": "Session Name",
    "modal.launch.aliasHint": "SSH alias will be",
    "modal.launch.account": "Google Account",
    "modal.launch.accountHint": "Pin an account or let colab-pool pick Primary",
    "modal.launch.gpu": "GPU Accelerator",
    "modal.launch.cpuDesc": "No GPU · ~0.1 CU/hr",
    "modal.launch.highMem": "High-RAM Host Shape",
    "modal.launch.highMemHint": "(more system RAM; does not guarantee A100 80GB)",
    "modal.launch.highMemG4": "(G4 / RTX PRO 6000 uses a single fixed host shape — High-RAM flag not supported by Colab)",
    "modal.launch.highMemL4": "(L4 uses a single fixed host shape — High-RAM flag ignored by Colab)",
    "modal.launch.guardTitle": "VM Cost Guard Watchdog",
    "modal.launch.idleLabel": "Idle Auto-Stop (minutes)",
    "modal.launch.idleHint": "0 disables idle detection",
    "modal.launch.maxHoursLabel": "Hard Max Runtime (hours)",
    "modal.launch.maxHoursHint": "0 disables hard deadline",
    "modal.launch.submit": "Provision GPU & Warm SSH",

    "modal.switch.title": "Switch GPU",
    "modal.switch.titleNamed": "Switch GPU — {name}",
    "modal.switch.notice":
      "Colab does not support hot-swapping GPUs in place. This will <strong>stop the existing VM</strong> (unsaved <code>/content</code> files will be lost) and re-provision under the same SSH alias.",
    "modal.switch.targetGpu": "Target GPU",
    "modal.switch.cpuDesc": "No GPU",
    "modal.switch.account": "Account",
    "modal.switch.highMem": "High-RAM Shape",
    "modal.switch.highMemHint": "Optional high-RAM host shape",
    "modal.switch.idleLabel": "Idle Auto-Stop (min)",
    "modal.switch.maxHoursLabel": "Hard Limit (hours)",
    "modal.switch.submit": "Stop Old & Switch GPU",

    "modal.guard.title": "VM Cost Guard",
    "modal.guard.titleNamed": "VM Cost Guard — {name}",
    "modal.guard.enabled": "Cost Guard Enabled",
    "modal.guard.enabledHint": "(unchecking stops watchdog auto-termination)",
    "modal.guard.idleLabel": "Idle Auto-Stop (min)",
    "modal.guard.idleHint": "0 disables idle trigger",
    "modal.guard.maxHoursLabel": "Reset Hard Limit (hrs from now)",
    "modal.guard.maxHoursPlaceholder": "keep current",
    "modal.guard.maxHoursHint": "Leave blank to keep; 0 disables",
    "modal.guard.submit": "Apply to VM",

    "modal.tunnel.title": "Forward VM Port (-L)",
    "modal.tunnel.titleNamed": "Forward VM Port — {name}",
    "modal.tunnel.presets": "Quick Presets",
    "modal.tunnel.remotePort": "Remote VM Port",
    "modal.tunnel.remoteHint": "Port 8080 is reserved by Colab",
    "modal.tunnel.localPort": "Local Port (127.0.0.1)",
    "modal.tunnel.localPlaceholder": "same as remote",
    "modal.tunnel.localHint": "Optional override",
    "modal.tunnel.label": "Label",
    "modal.tunnel.labelPlaceholder": "e.g. ComfyUI",
    "modal.tunnel.submit": "Start Tunnel",

    "modal.doctor.title": "Environment Diagnostics",
    "modal.doctor.running": "Running environment checks...",
    "modal.doctor.ok": "OK",
    "modal.doctor.missing": "MISSING",
    "modal.doctor.sshKey": "SSH Key",
    "modal.doctor.sshInclude": "~/.ssh/config Include",
    "modal.doctor.configured": "Configured",
    "modal.doctor.pendingFirstUp": "Pending first up",
    "modal.doctor.accountsPool": "Accounts Pool",
    "modal.doctor.accountsVal": "{count} accounts (primary: {primary})",
    "modal.doctor.issues": "Issues:",
    "modal.doctor.allHealthy": "✓ All local checks healthy",
    "modal.doctor.failed": "Doctor failed: {err}",

    "modal.quota.title": "Account Cycle Quota",
    "modal.quota.titleNamed": "Cycle Quota — {name}",
    "modal.quota.presets": "Plan Presets",
    "modal.quota.preset100": "100 CU · Pro 1x",
    "modal.quota.preset200": "200 CU · Pro",
    "modal.quota.preset500": "500 CU · Pro+",
    "modal.quota.preset2500": "2,500 CU · Ultra 20x",
    "modal.quota.cuLabel": "Quota Baseline (CU)",
    "modal.quota.cuHint": "Balance above this baseline is highlighted as extra capacity (may come from rollover, pay-as-you-go top-ups, or a higher plan).",
    "modal.quota.autoReset": "Reset to Auto",
    "modal.quota.submit": "Save Quota",

    "confirm.defaultTitle": "Confirm Action",
    "confirm.stopAllTitle": "Stop ALL Colab VMs?",
    "confirm.stopAllMsg":
      "This will terminate EVERY active session and unmanaged orphan VM across all saved Google accounts. Unsaved files in /content will be lost.",
    "confirm.stopAllBtn": "Stop All VMs",
    "confirm.reapAllTitle": "Reap All Orphan VMs?",
    "confirm.reapAllMsg":
      "This will unassign all detected unmanaged orphan VMs across your accounts so they stop consuming Compute Units.",
    "confirm.reapAllBtn": "Reap All Orphans",
    "confirm.stopSessionTitle": "Stop Session '{name}'?",
    "confirm.stopSessionMsg":
      "This will terminate the Colab VM for '{name}', stop Compute Unit billing, close active tunnels, and remove 'colab-{name}' from SSH config.",
    "confirm.stopSessionBtn": "Stop '{name}'",

    "toast.copied": "Copied: {text}",
    "toast.tokenExpired": "colabctl ui restarted with a new session token. Open the new window or URL.",
    "toast.disconnected": "Lost connection to local colabctl ui server. Restart `colabctl ui` to continue.",
    "toast.reconnected": "Reconnected to local colabctl ui server.",
    "toast.loadFailed": "Failed to load overview: {err}",
    "toast.probeSuccess": "Refreshed live status for '{name}'",
    "toast.probeFailed": "Status probe failed for '{name}': {err}",
    "toast.jobDone": "{title} completed.",
    "toast.jobFailed": "{title} failed: {err}",
    "toast.stoppingAll": "Stopping all VMs across every account...",
    "toast.reapingAll": "Reaping all orphan VMs...",
    "toast.provisioning": "Provisioning '{name}' ({gpu})...",
    "toast.launchFailed": "Launch failed: {err}",
    "toast.switching": "Switching '{name}' to {gpu}...",
    "toast.switchFailed": "Switch failed: {err}",
    "toast.guardUpdated": "Updated VM Cost Guard for '{name}'",
    "toast.guardFailed": "Guard update failed: {err}",
    "toast.tunnelStarted": "Tunnel active: {url} → {session}:{port}",
    "toast.tunnelFailed": "Tunnel failed: {err}",
    "toast.tunnelStopped": "Port forward stopped.",
    "toast.tunnelStopFailed": "Failed to stop tunnel: {err}",
    "toast.primarySet": "Primary account set to '{account}'",
    "toast.primaryFailed": "Failed to set primary: {err}",
    "toast.quotaSaved": "Saved cycle quota for '{account}': {quota} CU",
    "toast.quotaReset": "Reset '{account}' quota to auto ({quota} CU)",
    "toast.quotaFailed": "Failed to update quota: {err}",
    "toast.reapingOrphan": "Reaping orphan {endpoint} on {account}...",
    "toast.reapFailed": "Reap failed: {err}",
    "toast.extended": "Extended '{name}' hard deadline by +2h",
    "toast.extendFailed": "Extend failed: {err}",
    "toast.terminalDemo": "Demo: would open SSH terminal to {alias}",
    "toast.terminalOpened": "Opened SSH terminal in {app} ({alias})",
    "toast.terminalFailed": "Could not open terminal: {err}",
    "toast.vscodeDemo": "Demo: would open VS Code Remote-SSH ({alias})",
    "toast.vscodeOpened": "Launched VS Code Remote-SSH → {alias}",
    "toast.vscodeFailed": "Could not open VS Code: {err}",
    "toast.resetSshDone": "SSH reset for '{name}': cleared {count} remote sshd session(s){rewarmed}.",
    "toast.resetSshRewarmed": ", mux re-warmed",
    "toast.resetSshFailed": "Reset SSH failed: {err}",
    "toast.stoppingSession": "Stopping '{name}'...",
    "err.networkUnreachable": "Cannot reach local colabctl ui server — it may have stopped.",
  },

  "zh-CN": {
    "page.title": "colabctl — GPU 算力控制面板",
    "brand.subtitle": "多账号 Colab GPU 算力池 · SSH 多路复用 · VM 防烧卡看门狗",
    "brand.demoBadge": "演示模式 · 0 CU",

    "topbar.syncing": "同步中...",
    "topbar.queryingGoogle": "正在查询 Google...",
    "topbar.syncedAt": "已同步 {time}",
    "topbar.syncError": "同步失败",
    "topbar.disconnected": "已断开连接",
    "topbar.tokenExpired": "令牌已失效",
    "topbar.syncTitle": "上次总览刷新时间",
    "topbar.refreshLive": "实时刷新",
    "topbar.refreshLiveTitle": "从 Google 拉取实时 Compute Units 余额并探测 VM 看门狗状态",
    "topbar.doctor": "环境诊断",
    "topbar.doctorTitle": "本地依赖与账号环境自检 (colabctl doctor)",
    "topbar.themeTitle": "切换深色 / 浅色主题",
    "topbar.langLabel": "中文",
    "topbar.langTitle": "Switch language to English",
    "topbar.stopAll": "全部停止",
    "topbar.stopAllTitle": "停止所有账号下全部运行中 VM 和孤儿实例",
    "topbar.launch": "启动 GPU",

    "disconnect.unreachableTitle": "本地 colabctl ui 服务已断开",
    "disconnect.unreachableBody":
      "本地后端进程已停止（独立 Chrome 窗口不会自动关闭）。后台任务与实时倒计时已暂停 — 请在终端重新运行 <code>colabctl ui</code> 打开新窗口，或用 <code>colabctl ls --live</code> 查看云端 VM 状态。",
    "disconnect.tokenTitle": "会话令牌已失效（colabctl ui 已重启）",
    "disconnect.tokenBody":
      "新的 <code>colabctl ui</code> 服务正在使用不同的本地安全令牌运行。请关闭这个旧窗口，并使用新弹出的窗口或终端里的新链接。",
    "disconnect.retry": "重试连接",

    "kpi.balanceLabel": "总算力余额",
    "kpi.loadingAccounts": "正在加载账号...",
    "kpi.accountsMeta": "{count} 个账号 · 主账号：{primary}",
    "kpi.unset": "未设置",
    "kpi.burnLabel": "实时消耗速率",
    "kpi.runway": "全池预计还可运行约 {hours} 小时",
    "kpi.allIdle": "全部空闲 — 0.00 CU/hr 零计费",
    "kpi.usageModeMeta": "数据模式：{mode}",
    "kpi.sessionsLabel": "活跃 GPU 会话",
    "kpi.muxReady": "ControlMaster SSH 通道就绪",
    "kpi.muxActive": "{mux}/{active} 条 ControlMaster 复用通道活跃",
    "kpi.noActiveVms": "当前无运行中 VM",
    "kpi.tunnelsLabel": "活跃端口转发",
    "kpi.tunnelsMeta": "共享 SSH 多路复用 · 零 HTTP 429",

    "orphan.title": "检测到未托管的孤儿 VM — 仍在持续消耗算力！",
    "orphan.sub": "这些 Colab 实例不在 colab-pool 托管列表中，请及时回收以免静默扣费。",
    "orphan.reapAll": "回收全部孤儿",
    "orphan.reap": "回收",

    "accounts.title": "账号算力池",
    "accounts.sub": "默认优先使用主账号（支持自动故障转移），也可以在启动时手动指定账号。",
    "accounts.empty":
      "未找到已配置的 Google 账号，请在终端运行 <code>colab-account add &lt;别名&gt;</code> 添加。",
    "accounts.primaryBadge": "★ 主账号",
    "accounts.ready": "就绪",
    "accounts.disabled": "已禁用",
    "accounts.hourlyRateTitle": "每小时算力消耗",
    "accounts.runningVmsTitle": "运行中的 VM 数量",
    "accounts.vmSingular": "{count} 台 VM",
    "accounts.vmPlural": "{count} 台 VM",
    "accounts.quotaBarTitle": "{balance} / {quota} CU（占本账号配额基准 {pct}%）",
    "accounts.quotaBarOverBaseTitle": "{balance} / {quota} CU（{pct}%，超出设定基准 +{extra} CU；可能来自跨月结余、加购算力或更高套餐）",
    "accounts.overBase": "超出基准",
    "accounts.quotaEditTitleAuto": "本账号配额基准：{quota} CU（自动识别）。点击自定义",
    "accounts.quotaEditTitleCustom": "本账号配额基准：{quota} CU（自定义）。点击修改",
    "accounts.defaultForNew": "新建 GPU 默认账号",
    "accounts.setPrimary": "设为主账号",
    "accounts.launchOn": "+ 在 {name} 启动",

    "mode.cached": "缓存",
    "mode.live": "实时",
    "mode.demo": "演示",

    "sessions.title": "托管 GPU 会话",
    "sessions.sub": "每个会话自动部署独立 VM 防烧卡看门狗，并预热 ControlMaster SSH 多路复用通道。",
    "sessions.quickSync": "快速同步",
    "sessions.quickSyncTitle": "快速刷新本地缓存状态",
    "sessions.emptyTitle": "一切清爽 — 当前零算力消耗",
    "sessions.emptyBody":
      "目前没有运行中的 Colab GPU 实例。一键即可创建会话，系统会自动配置 SSH 多路复用并部署防烧卡看门狗。",
    "sessions.quickT4": "启动 T4 (16 GB · 经济)",
    "sessions.quickL4": "启动 L4 (24 GB)",
    "sessions.quickA100": "启动 A100 高内存",
    "sessions.accountPrefix": "账号：",
    "sessions.copySshTitle": "复制 SSH 连接命令",
    "sessions.vanished": "已离线",
    "sessions.running": "运行中",
    "sessions.muxActivePill": "复用活跃",
    "sessions.muxActiveTitle": "OpenSSH ControlMaster 通道已预热 — 秒开多终端与端口转发",
    "sessions.muxIdlePill": "复用待机",
    "sessions.muxIdleTitle": "首次 SSH 连接时自动建立 ControlMaster 复用通道",
    "sessions.hwGpu": "GPU 硬件",
    "sessions.hwSpec": "主机规格",
    "sessions.hwLoad": "GPU 负载 / 驱动",
    "sessions.probing": "探测中...",
    "sessions.ramCpu": "{ram} 内存 · {cores} vCPU",
    "sessions.gpuUtil": "{pct}% 占用",
    "sessions.driver": "驱动 {ver}",

    "guard.title": "VM 防烧卡看门狗",
    "guard.notProbed": "未探测",
    "guard.probeError": "探测异常",
    "guard.offPill": "看门狗已关",
    "guard.activePill": "看门狗运行中",
    "guard.configuredPill": "已配置",
    "guard.clickProbe": "点击探测",
    "guard.disabled": "已停用",
    "guard.off": "关闭",
    "guard.cfgMin": "配置 {min}m",
    "guard.cfgHrs": "配置 {hrs}h",
    "guard.metaNotProbed": "尚未探测 VM 看门狗实时状态。",
    "guard.metaPaused": "看门狗已暂停 — 请记得手动停机以免持续消耗算力！",
    "guard.metaCached": "当前为本地缓存策略 — 点击“探测”查看 VM 精确倒计时。",
    "guard.metaRunning": "PID {pid} · 最近活动：{reason}{gpu}",
    "guard.metaGpuSuffix": " · GPU {pct}%",
    "guard.probeBtn": "探测",
    "guard.probeTitle": "查询 VM 端看门狗实时状态与 GPU 利用率",
    "guard.extendBtn": "+2h 续期",
    "guard.extendTitle": "将硬上限延长 2 小时并重置空闲计时",
    "guard.settingsBtn": "策略设置",
    "guard.idleLabel": "空闲自动停机倒计时",
    "guard.deadlineLabel": "硬上限停机倒计时",

    "tunnels.label": "端口转发：",
    "tunnels.add": "+ 转发端口",
    "tunnels.stopTitle": "停止端口转发",

    "session.terminal": "终端",
    "session.vscode": "VS Code",
    "session.switchGpu": "切换 GPU",
    "session.resetSsh": "重置 SSH",
    "session.resetting": "重置中...",
    "session.resetSshTitle": "清理僵尸远程 sshd 会话以修复 SSH 卡顿或 HTTP 429",
    "session.stop": "停止",

    "jobs.drawerTitle": "操作记录与后台任务",
    "jobs.empty": "本次管理会话暂无后台任务记录。",
    "jobs.runningHint": "正在后台执行 — Colab 分配 GPU 通常需要 10–30 秒。",
    "jobs.disconnectedPill": "连接已断开",
    "jobs.disconnectedHint":
      "本地 <code>colabctl ui</code> 服务已不可达 — 当前窗口无法继续跟踪该任务。请在终端运行 <code>colabctl ls --live</code> 或重启 <code>colabctl ui</code>。",
    "jobs.failedPill": "失败",
    "jobs.dismiss": "关闭",
    "jobs.status.running": "进行中",
    "jobs.status.succeeded": "已完成",
    "jobs.status.failed": "失败",
    "jobs.title.up": "正在创建 '{target}' ({gpu}{highMem})",
    "jobs.title.switch": "正在将 '{target}' 切换为 {gpu}{highMem}",
    "jobs.title.stop": "正在停止 '{target}' 并结束计费",
    "jobs.title.stop-all": "正在停止所有账号下的全部 VM",
    "jobs.title.reap": "正在回收 {account} 上的孤儿 VM ({endpoint})",
    "jobs.title.reap-all": "正在回收全部未托管孤儿 VM",
    "jobs.highMemSuffix": " 高内存",
    "jobs.msg.running": "{title}...",
    "jobs.msg.completed": "{title} 已完成。",

    "common.cancel": "取消",
    "common.close": "关闭",
    "common.confirm": "确认",
    "common.autoPrimary": "自动（主账号：{primary}）",
    "common.none": "无",

    "modal.launch.title": "启动 GPU 会话",
    "modal.launch.sessionName": "会话名称",
    "modal.launch.aliasHint": "SSH 别名将为",
    "modal.launch.account": "Google 账号",
    "modal.launch.accountHint": "可指定账号，或交给 colab-pool 自动选主账号",
    "modal.launch.gpu": "GPU 加速卡",
    "modal.launch.cpuDesc": "无 GPU · ~0.1 CU/hr",
    "modal.launch.highMem": "高内存主机规格 (High-RAM)",
    "modal.launch.highMemHint": "（更多系统内存；不保证 A100 一定是 80GB 显存）",
    "modal.launch.highMemG4": "（G4 / RTX PRO 6000 仅提供单一固定内存规格，Colab 不支持 High-RAM 参数）",
    "modal.launch.highMemL4": "（L4 仅提供单一固定内存规格，Colab 会忽略 High-RAM 参数）",
    "modal.launch.guardTitle": "VM 防烧卡看门狗",
    "modal.launch.idleLabel": "空闲自动停机（分钟）",
    "modal.launch.idleHint": "填 0 表示关闭空闲检测",
    "modal.launch.maxHoursLabel": "最长运行硬上限（小时）",
    "modal.launch.maxHoursHint": "填 0 表示不设硬上限",
    "modal.launch.submit": "分配 GPU 并预热 SSH",

    "modal.switch.title": "切换 GPU",
    "modal.switch.titleNamed": "切换 GPU — {name}",
    "modal.switch.notice":
      "Colab 不支持在线热切换 GPU。此操作会先<strong>停止当前 VM</strong>（未保存的 <code>/content</code> 文件将会丢失），再以相同 SSH 别名重新分配新卡。",
    "modal.switch.targetGpu": "目标 GPU",
    "modal.switch.cpuDesc": "无 GPU",
    "modal.switch.account": "目标账号",
    "modal.switch.highMem": "高内存规格",
    "modal.switch.highMemHint": "可选高内存主机规格",
    "modal.switch.idleLabel": "空闲停机（分钟）",
    "modal.switch.maxHoursLabel": "硬上限（小时）",
    "modal.switch.submit": "停止旧机并切换 GPU",

    "modal.guard.title": "VM 防烧卡看门狗",
    "modal.guard.titleNamed": "VM 防烧卡看门狗 — {name}",
    "modal.guard.enabled": "启用防烧卡看门狗",
    "modal.guard.enabledHint": "（取消勾选将暂停自动停机保护）",
    "modal.guard.idleLabel": "空闲自动停机（分钟）",
    "modal.guard.idleHint": "填 0 关闭空闲触发",
    "modal.guard.maxHoursLabel": "重置硬上限（从现在起小时数）",
    "modal.guard.maxHoursPlaceholder": "保持当前设置",
    "modal.guard.maxHoursHint": "留空保持不变；填 0 关闭硬上限",
    "modal.guard.submit": "应用到 VM",

    "modal.tunnel.title": "端口转发 (-L)",
    "modal.tunnel.titleNamed": "端口转发 — {name}",
    "modal.tunnel.presets": "常用预设",
    "modal.tunnel.remotePort": "远程 VM 端口",
    "modal.tunnel.remoteHint": "8080 端口为 Colab 内部保留端口",
    "modal.tunnel.localPort": "本地端口 (127.0.0.1)",
    "modal.tunnel.localPlaceholder": "默认与远程端口一致",
    "modal.tunnel.localHint": "可选自定义",
    "modal.tunnel.label": "名称标签",
    "modal.tunnel.labelPlaceholder": "例如 ComfyUI",
    "modal.tunnel.submit": "开启端口转发",

    "modal.doctor.title": "环境诊断",
    "modal.doctor.running": "正在运行环境检查...",
    "modal.doctor.ok": "正常",
    "modal.doctor.missing": "缺失",
    "modal.doctor.sshKey": "SSH 密钥",
    "modal.doctor.sshInclude": "~/.ssh/config Include 配置",
    "modal.doctor.configured": "已配置",
    "modal.doctor.pendingFirstUp": "首次启动自动配置",
    "modal.doctor.accountsPool": "账号算力池",
    "modal.doctor.accountsVal": "{count} 个账号（主账号：{primary}）",
    "modal.doctor.issues": "检测到以下问题：",
    "modal.doctor.allHealthy": "✓ 全部本地环境检查正常",
    "modal.doctor.failed": "诊断失败：{err}",

    "modal.quota.title": "账号周期配额基准",
    "modal.quota.titleNamed": "周期配额基准 — {name}",
    "modal.quota.presets": "常用套餐预设",
    "modal.quota.preset100": "100 CU · Pro 1x",
    "modal.quota.preset200": "200 CU · Pro",
    "modal.quota.preset500": "500 CU · Pro+",
    "modal.quota.preset2500": "2,500 CU · Ultra 20x",
    "modal.quota.cuLabel": "配额基准（CU）",
    "modal.quota.cuHint": "超出本账号设定基准的部分将高亮显示（可能来自跨月结余、加购算力或更高套餐）。",
    "modal.quota.autoReset": "恢复自动识别",
    "modal.quota.submit": "保存配额",

    "confirm.defaultTitle": "确认操作",
    "confirm.stopAllTitle": "停止全部 Colab VM？",
    "confirm.stopAllMsg":
      "这将会终止所有已保存 Google 账号下的每一个活跃会话和未托管孤儿 VM，/content 中未保存的数据将丢失。",
    "confirm.stopAllBtn": "停止全部 VM",
    "confirm.reapAllTitle": "回收全部孤儿 VM？",
    "confirm.reapAllMsg":
      "这将会释放所有账号下检测到的未托管孤儿 VM，立即停止 Compute Units 消耗。",
    "confirm.reapAllBtn": "回收全部孤儿",
    "confirm.stopSessionTitle": "停止会话 '{name}'？",
    "confirm.stopSessionMsg":
      "这将会终止 '{name}' 对应的 Colab VM、停止计费、关闭相关端口转发，并从 SSH 配置中移除 'colab-{name}'。",
    "confirm.stopSessionBtn": "停止 '{name}'",

    "toast.copied": "已复制：{text}",
    "toast.tokenExpired": "colabctl ui 已使用新令牌重启，请改用新打开的窗口或终端中的新链接。",
    "toast.disconnected": "与本地 colabctl ui 服务断开连接，请重启 `colabctl ui` 后继续。",
    "toast.reconnected": "已重新连接到本地 colabctl ui 服务。",
    "toast.loadFailed": "加载总览失败：{err}",
    "toast.probeSuccess": "已刷新 '{name}' 的实时状态",
    "toast.probeFailed": "探测 '{name}' 状态失败：{err}",
    "toast.jobDone": "{title} 已完成。",
    "toast.jobFailed": "{title} 失败：{err}",
    "toast.stoppingAll": "正在停止所有账号下的全部 VM...",
    "toast.reapingAll": "正在回收全部孤儿 VM...",
    "toast.provisioning": "正在分配 '{name}' ({gpu})...",
    "toast.launchFailed": "启动失败：{err}",
    "toast.switching": "正在将 '{name}' 切换为 {gpu}...",
    "toast.switchFailed": "切换失败：{err}",
    "toast.guardUpdated": "已更新 '{name}' 的防烧卡看门狗策略",
    "toast.guardFailed": "更新看门狗策略失败：{err}",
    "toast.tunnelStarted": "端口转发已开启：{url} → {session}:{port}",
    "toast.tunnelFailed": "开启端口转发失败：{err}",
    "toast.tunnelStopped": "端口转发已停止。",
    "toast.tunnelStopFailed": "停止端口转发失败：{err}",
    "toast.primarySet": "已将主账号切换为 '{account}'",
    "toast.primaryFailed": "设置主账号失败：{err}",
    "toast.quotaSaved": "已保存 '{account}' 的周期配额基准：{quota} CU",
    "toast.quotaReset": "已恢复 '{account}' 自动识别配额（{quota} CU）",
    "toast.quotaFailed": "更新配额基准失败：{err}",
    "toast.reapingOrphan": "正在回收 {account} 上的孤儿 VM ({endpoint})...",
    "toast.reapFailed": "回收失败：{err}",
    "toast.extended": "已为 '{name}' 硬上限续期 +2 小时",
    "toast.extendFailed": "续期失败：{err}",
    "toast.terminalDemo": "演示模式：将打开 SSH 终端连接到 {alias}",
    "toast.terminalOpened": "已在 {app} 中打开 SSH 终端 ({alias})",
    "toast.terminalFailed": "无法打开终端：{err}",
    "toast.vscodeDemo": "演示模式：将打开 VS Code Remote-SSH ({alias})",
    "toast.vscodeOpened": "已启动 VS Code Remote-SSH → {alias}",
    "toast.vscodeFailed": "无法打开 VS Code：{err}",
    "toast.resetSshDone": "已重置 '{name}' 的 SSH：清理了 {count} 个远程 sshd 会话{rewarmed}。",
    "toast.resetSshRewarmed": "，并重新预热了复用通道",
    "toast.resetSshFailed": "重置 SSH 失败：{err}",
    "toast.stoppingSession": "正在停止 '{name}'...",
    "err.networkUnreachable": "无法连接到本地 colabctl ui 服务 — 进程可能已停止。",
  },
};

let currentLang = "en";

export function normalizeLang(raw) {
  if (!raw || raw === "auto") return null;
  const s = String(raw).trim().toLowerCase();
  if (s === "zh" || s.startsWith("zh-")) return "zh-CN";
  if (s === "en" || s.startsWith("en-")) return "en";
  return null;
}

export function detectInitialLang(configDefaultLang = "auto") {
  const params = new URLSearchParams(window.location.search);
  const queryLang = normalizeLang(params.get("lang"));
  if (queryLang) {
    localStorage.setItem("colabctl_lang", queryLang);
    return queryLang;
  }

  const cliLang = normalizeLang(configDefaultLang);
  if (cliLang) return cliLang;

  const saved = normalizeLang(localStorage.getItem("colabctl_lang"));
  if (saved) return saved;

  const nav = normalizeLang(navigator.language || (navigator.languages && navigator.languages[0]));
  return nav || "en";
}

export function getLang() {
  return currentLang;
}

export function setLang(lang, { persist = true } = {}) {
  const norm = normalizeLang(lang) || "en";
  currentLang = norm;
  if (persist) {
    try {
      localStorage.setItem("colabctl_lang", norm);
    } catch (_) {}
  }
  document.documentElement.setAttribute("lang", norm);
  return currentLang;
}

export function toggleLang() {
  return setLang(currentLang === "zh-CN" ? "en" : "zh-CN");
}

function interpolate(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (_, k) =>
    vars[k] !== undefined && vars[k] !== null ? String(vars[k]) : ""
  );
}

export function t(key, vars = {}) {
  const dict = MESSAGES[currentLang] || MESSAGES.en;
  const raw = dict[key] ?? MESSAGES.en[key] ?? key;
  return interpolate(raw, vars);
}

export function tHtml(key, vars = {}) {
  const dict = MESSAGES[currentLang] || MESSAGES.en;
  const raw = dict[key] ?? MESSAGES.en[key] ?? key;
  return interpolate(raw, vars);
}

export function localizeJobTitle(job) {
  if (!job) return "";
  const kind = job.kind;
  const meta = job.meta || {};
  if (kind === "up" && meta.gpu) {
    return t("jobs.title.up", {
      target: job.target || "",
      gpu: meta.gpu,
      highMem: meta.high_mem ? t("jobs.highMemSuffix") : "",
    });
  }
  if (kind === "switch" && meta.gpu) {
    return t("jobs.title.switch", {
      target: job.target || "",
      gpu: meta.gpu,
      highMem: meta.high_mem ? t("jobs.highMemSuffix") : "",
    });
  }
  if (kind === "stop" && job.target) {
    return t("jobs.title.stop", { target: job.target });
  }
  if (kind === "stop-all") {
    return t("jobs.title.stop-all");
  }
  if (kind === "reap" && meta.account && meta.endpoint) {
    return t("jobs.title.reap", {
      account: meta.account,
      endpoint: meta.endpoint,
    });
  }
  if (kind === "reap-all") {
    return t("jobs.title.reap-all");
  }
  return job.title || "";
}

export function localizeJobMessage(job) {
  if (!job) return "";
  if (job.error) return job.error;
  const title = localizeJobTitle(job);
  if (job.status === "running") return t("jobs.msg.running", { title });
  if (job.status === "succeeded") return t("jobs.msg.completed", { title });
  return job.message || title;
}

export function localizeJobStatus(status) {
  return t(`jobs.status.${status}`) || status;
}

export function applyStaticTranslations(root = document) {
  document.title = t("page.title");
  for (const el of root.querySelectorAll("[data-i18n]")) {
    el.textContent = t(el.getAttribute("data-i18n"));
  }
  for (const el of root.querySelectorAll("[data-i18n-html]")) {
    el.innerHTML = tHtml(el.getAttribute("data-i18n-html"));
  }
  for (const el of root.querySelectorAll("[data-i18n-title]")) {
    el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
  }
  for (const el of root.querySelectorAll("[data-i18n-placeholder]")) {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
  }
  for (const el of root.querySelectorAll("[data-i18n-aria]")) {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
  }
}
