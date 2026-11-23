# Figure Brief: `colabctl` Full-Stack Architecture & End-to-End Workflow (v0.2)

## 1. What this figure is
A double-column (504 pt wide) **systems architecture & request-flow figure** (`meta.family: systems`, `meta.kind: architecture`, `figure_kind: request-path`) illustrating the full-stack architecture of `colabctl v0.2`: a shared local controller driven by both the CLI and a loopback-secured Web / Chromium App dashboard (`EN / 中文`), provisioning GPU VMs across a multi-account Google Colab pool, multiplexing concurrent SSH / IDE / port-forward sessions over Colab's single-slot SSH WebSocket without `HTTP 429`, and preventing idle compute-unit burn via an autonomous VM-side cost-guard watchdog.

## 2. Components
Grouped into three physical/trust regions (10 labelled boxes total, matching the corpus median of 11):

### Container A: Local Host (macOS / Linux) (`solid` outer container)
- **Web / Chromium UI** (`actor`, **novel / core**; icon `layout-dashboard`): FastAPI loopback server (`127.0.0.1` + one-time Session Token), standalone Chromium `--app` window, bilingual `EN / 简体中文`, dark/light themes, async job tracker, and managed `-L` tunnels.
- **CLI & SSH Clients** (`actor`, existing; icon `terminal`): `colabctl` CLI (`up`, `ssh`, `tunnel`, `status`, `extend`, `stop`, `ui`), native `ssh colab-<name>`, VS Code Remote-SSH, and local browsers (`127.0.0.1:8188`).
- **colabctl Controller** (`module`, **novel / core**; icon `workflow`): UI-agnostic core orchestrator (`service.py`), handling GPU allocation, single-shape `High-RAM` stripping (`G4`/`L4`), orphan diff-reaping, and SSH config sync.
- **Multi-Account Pool** (`store`, existing; icon `key-round`): `colab-pool` + OS Keychain (`ultra`, `pro1`, `pro2`), global file lock, primary failover, and Compute Unit balance tracking.
- **SSH Mux & `_proxy`** (`module`, **novel / safeguard accent**; icon `network`): Managed `~/.config/colabctl/ssh_config` (`Include`d in `~/.ssh/config`), `colabctl _proxy` (forbids implicit VM creation), and one pre-warmed OpenSSH `ControlMaster` Unix socket (`ControlPersist 5m`).

### Container B: Google Colab Cloud (`solid` external region, center)
- **Colab Control API** (`external`; icon `cloud`): Official `google-colab-cli` backend (`/assign`, `/unassign`, `/ccu-info`, `/assignments`), Jupyter Kernel WebSocket, and single-slot SSH-over-WS relay.

### Container C: Colab Cloud GPU VM (`solid` outer container, right)
- **GPU Runtime** (`compute`, existing; icon `cpu`): Allocated accelerator (`T4 / L4 / A100 / G4 / H100`), `/content` workspace, and `/dev/pts/*` terminals.
- **TBE Unassign Hook** (`external`; icon `power`): Loopback runtime endpoint (`$TBE_RUNTIME_ADDR/unassign`) that immediately stops VM billing even when the host sleeps or disconnects.
- **VM `sshd` Daemon** (`module`, existing; icon `server`): Terminates the single SSH-over-WS slot (Ed25519 key auth) and serves multiplexed shells, `scp`, `-L` tunnels, and no-PTY control execs.
- **Cost-Guard Watchdog** (`module`, **novel / safeguard accent**; icon `shield-check`): Detached stdlib daemon (`watchdog.py`) inside the VM polling GPU util (`< 5%`), `/dev/pts/*` I/O, heartbeat, and hard deadline (`max_hours`).

## 3. Flows and the main path
- **①** `Web / Chromium UI` & `CLI & SSH Clients` → `colabctl Controller`: invoke `up`/`stop`/`switch`/`extend` via loopback REST+Token API or CLI.
- **②** `colabctl Controller` → `Multi-Account Pool`: acquire global lock and select primary or pinned Google account.
- **⑧** `Multi-Account Pool` → `Colab Control API`: allocate GPU VM (or clean `stop`); on timeout/503, diff-check and auto-reap newly leaked orphan VMs.
- **③** `Colab Control API` → `GPU Runtime` & `Cost-Guard Watchdog`: over Jupyter WS, probe `nvidia-smi`/RAM/CPU and deploy detached `watchdog.py`.
- **④** `colabctl Controller` → `SSH Mux & _proxy`: write `Include`d `ssh_config` and pre-warm 1 `ControlMaster` connection.
- **⑤** `CLI & SSH Clients` → `SSH Mux & _proxy` → `VM sshd` → `GPU Runtime`: multiplex concurrent terminals, VS Code Remote-SSH, and `-L` port forwards over 1 slot (`zero HTTP 429`).
- **⑥** `VM sshd` → `Cost-Guard Watchdog`: fast no-PTY control exec (`~1s`) for live status, `+2h` extend, and guard updates.
- **⑦** `Cost-Guard Watchdog` → `GPU Runtime` (dashed 15s poll) & **red** `POST /unassign` → `TBE Unassign Hook`: autonomously halts billing on `30m` idle or `4h` hard limit.

## 4. The one point the figure argues
A single shared `colabctl` controller bridges both CLI and a loopback-secured Web/Chromium UI with two core safeguards — **pre-warmed single-slot SSH multiplexing** (eliminating `HTTP 429`) and an **autonomous VM-side cost-guard watchdog** (eliminating silent Compute Unit burn even offline).

## 5. Layout and style intent
- `host-device` + `control-data`, left-to-right, double-column (`504 × 214 pt`, white canvas), planar zero-crossing orthogonal routing.
- Closest exemplars: `asplos25-140_fig7`, `nsdi26-087_fig3`, `asplos25-167_fig1`, `asplos25-046_fig13`.
- Palette: `blue-orange` house palette shared with Figure 2 (`#dae8fc` existing, `#fff2cc` colabctl Core/UI, `#ed7d31` safeguards, `#c00000` red auto-unassign). Pure English labels with 10 flat linear Lucide vector icons.

## 6. Confirmed decisions
1. Upgraded from v0.1.0 CLI-only to v0.2 full-stack (including Web / Chromium UI and G4 / H100 GPUs).
2. Generic `Local Host (macOS / Linux)` framing (portable for GitHub README).
3. Pure English labels matching Figure 2's house palette and typography.

## 7. Caption draft
> **Figure 1.** Full-stack architecture and workflow of `colabctl`. ① Both the loopback-secured Web/Chromium UI and CLI invoke the shared controller; ② it locks the multi-account pool and allocates a GPU runtime (T4/L4/A100/G4/H100) via the Colab Control API, auto-reaping newly leaked orphans on timeout. ③ Over Jupyter WebSocket, `colabctl` probes hardware and deploys a detached `watchdog.py` daemon, then ④ writes an `Include`d SSH config and pre-warms a single `ControlMaster` tunnel. ⑤ Concurrent shells, VS Code, and `-L` port forwards multiplex over one SSH-over-WS slot with zero `HTTP 429`, while ⑥ live guard probes/extends run over a fast no-PTY channel (~1s). ⑦ Inside the VM, the Cost-Guard Watchdog polls GPU/PTY activity and autonomously posts `$TBE_RUNTIME_ADDR/unassign` upon idle or deadline expiry; ⑧ `stop` closes the mux, unassigns the VM, and removes the SSH entry.
