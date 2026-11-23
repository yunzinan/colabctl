# Drawing Plan: `colabctl-fig2` (Core Safeguard Mechanisms)

## 1. Canvas & Grid
- Double-column composite mechanism figure: **504 × 214 pt** (matching Figure 1's exact canvas size and `helvetica` typography).
- Top legend bar (`x = 4..500, y = 4..22`, h=18) decoding 4 fill roles and 2 arrow classes.
- Two equal-height panels (`y = 28..208`, h=180, 18 pt headroom `y = 28..46`):
  - **Panel (a)** `p:mux-compare`: `x = 4..250` (w=246) — stacked aligned comparison (`mux-before` top `y = 46..124`, horizontal dashed divider at `y = 125`, `mux-after` bottom `y = 126..206`).
  - **Panel (b)** `p:watchdog-fsm`: `x = 258..500` (w=242) — planar 2×2 finite-state machine with explicit guards on every transition and an offline-safe footer caption.

## 2. What Repeats & What Differs (Panel a)
- **Repeats identically**: 3 local client boxes (`Terminal`, `VS Code`, `-L 8188`, `x = 12..54`, w=42, h=14) and `VM sshd` (`x = 194..242`, w=48, h=50).
- **Differs (marked by colour)**: In `mux-before`, `Colab SSH-WS` (`x = 96..158`, grey) blocks clients #2 and #3 with bold red `HTTP 429` rejections; in `mux-after`, one warm-orange `ControlMaster Mux` (`x = 76..148`) aggregates all three local clients onto a single thick `1 WS slot` arrow to `VM sshd`.

## 3. Reading Path (Panel b)
- Entry dot at left of `Active` (`x = 266, y = 78`) → clockwise progression `Active` → `Idle Countdown` → `Warning (T-2m)` → red terminal `Unassigned (0 CU/hr)`.
- Planar center corridor separates `Active → Warning` (`y = 110`, `hard limit T-2m`) strictly above `Warning → Active` (`y = 124`, dashed `extend +2h`) with zero crossings.

## 4. Check List for `fig.png`
1. Panel (a)'s left clients and right `VM sshd` align vertically across Baseline and Ours.
2. Red `HTTP 429` rejections vs. warm-orange `ControlMaster Mux` + green verdict make the before/after delta readable in 3 seconds.
3. Every transition in Panel (b) carries an unambiguous guard label with zero arrow crossings or text collisions.
4. Palette strictly respects ≤ 2 saturated fills (`#ed7d31` orange, `#c00000` red) alongside pale tints; `lint.py` reports 0 errors.
