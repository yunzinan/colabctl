# Drawing Plan: `colabctl-fig1` (v0.2 Full-Stack Architecture)

## 1. Canvas
- Double-column systems figure: **504 × 214 pt** (aspect ratio 2.36, margins ≥ 4 pt).
- Font: `helvetica` (`TeX Gyre Heros` stack declared once on `<svg>`), pure English:
  - Container titles: **7.5 pt bold**
  - Node titles: **6.5 pt bold**
  - Node sublabels, edge labels & legend labels: **6.0 pt regular**
  - Circled step badge digits: **5.5 pt bold**

## 2. Regions (`y = 28..208`, height 180 pt, 18 pt headroom `y = 28..46`)
- **Top Legend Pill** (`x = 4..500, y = 4..22`): single horizontal bar decoding 3 fill roles and 3 arrow classes.
- **Local Host (macOS / Linux)** (`c:local-host`, `x = 4..212`, w=208): 2×2 upper grid (`Web / Chromium UI`, `colabctl Controller`, `CLI & SSH Clients`, `Multi-Account Pool`) above the wide `SSH Mux & _proxy` safeguard bar.
- **Google Colab Cloud** (`c:colab-cloud`, `x = 220..308`, w=88): `Colab Control API` in the upper band; open WebSocket interconnect corridor below.
- **Colab Cloud GPU VM** (`c:gpu-vm`, `x = 316..500`, w=184): `GPU Runtime` + `TBE Unassign Hook` on top row (`y = 46..80`), `VM sshd Daemon` + `Cost-Guard Watchdog` on bottom row (`y = 166..202`).

## 3. Planar Routing (Zero Edge Crossings)
- Placing `Web / Chromium UI` top-left (`y = 46..80`) and `CLI & SSH Clients` mid-left (`y = 104..138`) keeps `e-web-ctrl` (`y = 63` straight right), `e-cli-ctrl` (`y = 88` horizontal step above `e-ctrl-mux`), `e-ctrl-mux` (`y = 95` horizontal step down `x = 107` corridor), and `e-clients-mux` (`x = 46` straight down) completely planar with zero crossings.

## 4. Check List for `fig.png`
1. Every label is pure English, ≥ 6.0 pt, crisp and legible at 100%, with zero overlap against boxes, icons, or arrows.
2. Both `Web / Chromium UI` and `colabctl Controller` read clearly as the warm-cream core layer; `SSH Mux & _proxy` and `Cost-Guard Watchdog` stand out in warm orange; red is reserved strictly for `POST /unassign`.
3. All 10 flat linear Lucide icons render with uniform `0.65 pt` strokes and clean padding.
4. Zero edge crossings anywhere on the canvas; `lint.py` reports 0 errors.
5. `GPU Runtime` cleanly lists `T4/L4/A100/G4/H100` without overflowing its box.
