# Figure Brief: `colabctl` Core Safeguard Mechanisms (SSH Multiplexing & VM Cost-Guard FSM)

## 1. What this figure is
A double-column (504 pt wide) **systems composite mechanism figure** (`meta.family: systems`, `meta.kind: mechanism`, `panels: 2`, `axis: part`) pairing `colabctl`'s two primary technical safeguards side by side: **(a)** a before-vs-after comparison showing how a single pre-warmed `ControlMaster` Unix socket eliminates Colab's `HTTP 429` single-slot SSH bottleneck, and **(b)** the autonomous finite-state machine of the VM-side Cost-Guard Watchdog that halts Compute Unit billing even when the host machine sleeps or disconnects.

## 2. What is drawn
Two aligned side-by-side panels (`p:mux-compare` left, `p:watchdog-fsm` right) sharing one top legend and the `blue-orange` house palette from Figure 1:

### Panel (a): Single-Slot SSH Multiplexing (Before vs. After) (`comparison`)
- Shared aligned template repeated in two stacked sub-panels separated by a horizontal dashed rule:
  - Left column: three concurrent local clients (`Terminal`, `VS Code`, `-L 8188`).
  - Right column: `VM sshd` (`1 WS slot`).
- **Without `colabctl` (Baseline)**: all three clients open separate SSH-over-WS connections against `Colab SSH-WS (1-slot limit)`. Only `Terminal` (slot 1) reaches `VM sshd`; `VS Code` and `-L 8188` are rejected in red with `HTTP 429`. Verdict: `1/3 OK · HTTP 429 on concurrent use`.
- **With `colabctl` (ControlMaster Mux)**: all three clients converge into one warm-orange `ControlMaster Mux` (`1 Unix socket · no-PTY ~1s`), occupying exactly one SSH-over-WS slot to `VM sshd`. Verdict: `All concurrent clients OK · 0 HTTP 429`.

### Panel (b): Autonomous VM Cost-Guard Watchdog (`logic` state machine)
- Entry point (`colabctl up`) enters a 4-state directed FSM running entirely inside the Colab VM:
  - **Active** (green tint): `GPU >=5% / PTY / HB`, self-loop `poll 15s: busy`.
  - **Idle Countdown** (cream tint): `idle timer (30m)`.
  - **Warning (T-2m)** (orange accent): `PTY broadcast` to active terminals.
  - **Unassigned (0 CU/hr)** (red terminal state): `POST $TBE_ADDR/unassign`.

## 3. The story
- In **(a)**, compare top vs. bottom left-to-right: replacing direct per-client WebSockets with a single pre-warmed `ControlMaster` socket turns two red `HTTP 429` failures into full concurrent access over one slot.
- In **(b)**, follow every guarded transition: `Active` moves to `Idle Countdown` when `GPU <5% & no PTY` and immediately returns on `GPU / PTY active`; reaching `idle >= 28m` (or `hard limit T-2m` directly from `Active`) enters `Warning (T-2m)`; a user can send dashed `extend +2h` to reset back to `Active`; otherwise after `2m elapsed`, the red autonomous transition posts `$TBE_ADDR/unassign` to enter `Unassigned (0 CU/hr)` offline-safely.

## 4. The one point the figure argues
Left: one pre-warmed `ControlMaster` socket eliminates `HTTP 429` completely. Right: because the watchdog state machine runs inside the VM and calls `$TBE_ADDR/unassign` directly, idle or forgotten GPUs always stop billing even if the laptop sleeps or loses network.

## 5. Layout and style intent
- Composite mechanism figure (`504 × 214 pt`), `panels-row` of two equal-height panels (`(a)` comparison with stacked aligned baseline/ours sub-panels, `(b)` 2×2 planar FSM with zero crossing arrows).
- Closest exemplars: `asplos25-006_fig1`, `asplos25-038_fig1` (comparison verdicts), `asplos26-091_fig2`, `nsdi25-027_fig1`, `nsdi24-031_fig9` (guarded FSM with solid vs. dashed transition roles).
- Same `blue-orange` palette and `helvetica` typography as Figure 1 (≤ 2 saturated fills: orange safeguard + red error/unassign; pale green tint for safe/active state).

## 6. Confirmed decisions
1. Paired side-by-side in one double-column figure (`504 × 214 pt`) for compact GitHub README presentation.
2. Pure English labels matching Figure 1.

## 7. Caption draft
> **Figure 2.** Core safeguards of `colabctl`. **(a)** Pre-warming a single OpenSSH `ControlMaster` Unix socket multiplexes terminals, VS Code Remote-SSH, `-L` port forwards, and fast no-PTY probes over Colab's single SSH-over-WS slot, eliminating `HTTP 429`. **(b)** Inside the VM, a detached Python stdlib watchdog polls GPU utilization, PTY I/O, and hard runtime deadlines, broadcasting a 2-minute warning (extendable via `colabctl extend +2h`) before autonomously calling `$TBE_RUNTIME_ADDR/unassign` to stop billing even if the host is offline.
