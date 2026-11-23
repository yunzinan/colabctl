#!/usr/bin/env python3
"""Generate publication-quality SVG for colabctl core mechanisms (504 x 214 pt)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def _find_skill_scripts() -> Path:
    env = os.environ.get("FIGGENIE_SCRIPTS")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    home = Path.home()
    candidates = [
        *home.glob(".t3/userdata/providers/antigravity/*/config/skills/figgenie-paper-diagram/scripts"),
        home / ".claude/skills/figgenie-paper-diagram/scripts",
        home / ".agents/skills/figgenie-paper-diagram/scripts",
    ]
    for cand in candidates:
        if cand.is_dir():
            return cand
    raise RuntimeError(
        "Could not locate figgenie-paper-diagram scripts. Set FIGGENIE_SCRIPTS=/path/to/scripts."
    )


sys.path.insert(0, str(_find_skill_scripts()))

import _svgkit as K  # noqa: E402
from measure_text import width_of  # noqa: E402

FIG_DIR = Path(__file__).resolve().parent
OUT_SVG = FIG_DIR / "fig.svg"

FONT_KEY = "helvetica"
FONT_STACK = "'TeX Gyre Heros', 'Helvetica Neue', Helvetica, Arimo, Arial, sans-serif"

W = 504
H = 214

SW_THIN = 0.65
SW_MAIN = 1.15

# Blue-orange house palette (same visual language as Figure 1)
C_CANVAS = "#ffffff"
C_PANEL_BG = "#f7f9fc"
C_PANEL_STROKE = "#7b8794"
C_EXISTING_BG = "#dae8fc"
C_EXISTING_STROKE = "#4c6e9b"
C_CORE_BG = "#fff2cc"
C_CORE_STROKE = "#a67500"
C_ACCENT_BG = "#ed7d31"
C_ACCENT_STROKE = "#8f3f08"
C_EXT_BG = "#eceff1"
C_EXT_STROKE = "#607d8b"
C_SAFE_BG = "#dcfce7"
C_SAFE_STROKE = "#15803d"
C_STOP_BG = "#fee2e2"
C_STOP_STROKE = "#c00000"
C_TEXT = "#0d0d0d"
C_TEXT_MUTED = "#4a5568"
C_TEXT_ON_ACCENT_SUB = "#2b1200"
C_ARROW_MAIN = "#1f2937"
C_ARROW_CTRL = "#52606d"
C_ARROW_RED = "#c00000"
C_GREEN_TEXT = "#15803d"


def baseline_in_band(text: str, y_top: float, band_h: float, size: float, bold: bool = False) -> float:
    above, below = K.ink_band(text, size, FONT_KEY, bold)
    mid = y_top + band_h / 2.0
    return round(mid + (above - below) / 2.0, 2)


def draw_box(
    node_id: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    stroke: str,
    title: str,
    sublabel: str | None = None,
    title_lines: list[str] | None = None,
    role: str = "existing",
    panel_attr: str | None = None,
    delta_attr: str | None = None,
    sub_color: str = C_TEXT_MUTED,
    rx: float = 2.5,
    double_border: bool = False,
    stroke_w: float = SW_THIN,
    title_size: float = 6.5,
) -> str:
    extra = ""
    if panel_attr:
        extra += f' data-panel="{panel_attr}"'
    if delta_attr:
        extra += f' data-delta="{delta_attr}"'
    cx = x + w / 2.0
    lines = [
        f'    <g id="n:{node_id}" data-kind="node" data-role="{role}"{extra}>',
        f'      <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"/>',
    ]
    if double_border:
        lines.append(
            f'      <rect x="{x + 2.2}" y="{y + 2.2}" width="{w - 4.4}" height="{h - 4.4}" rx="{max(1.0, rx - 0.8)}" '
            f'fill="none" stroke="{stroke}" stroke-width="{SW_THIN}"/>'
        )
    if title_lines:
        y1 = baseline_in_band(title_lines[0], y + 3.0, 9.5, title_size, bold=True)
        y2 = baseline_in_band(title_lines[1], y + 12.0, 9.5, title_size, bold=True)
        lines.append(
            f'      <text x="{cx:.2f}" y="{y1:.2f}" text-anchor="middle" '
            f'font-size="{title_size}" font-weight="700" fill="{C_TEXT}">{escape(title_lines[0])}</text>'
        )
        lines.append(
            f'      <text x="{cx:.2f}" y="{y2:.2f}" text-anchor="middle" '
            f'font-size="{title_size}" font-weight="700" fill="{C_TEXT}">{escape(title_lines[1])}</text>'
        )
        if sublabel:
            ys = baseline_in_band(sublabel, y + 23.0, h - 25.0, 6.0, bold=False)
            lines.append(
                f'      <text x="{cx:.2f}" y="{ys:.2f}" text-anchor="middle" '
                f'font-size="6.0" fill="{sub_color}">{escape(sublabel)}</text>'
            )
    elif sublabel:
        yt = baseline_in_band(title, y + 3.0, (h - 6.0) * 0.50, title_size, bold=True)
        ys = baseline_in_band(sublabel, y + 3.0 + (h - 6.0) * 0.50, (h - 6.0) * 0.50, 6.0, bold=False)
        lines.append(
            f'      <text x="{cx:.2f}" y="{yt:.2f}" text-anchor="middle" '
            f'font-size="{title_size}" font-weight="700" fill="{C_TEXT}">{escape(title)}</text>'
        )
        lines.append(
            f'      <text x="{cx:.2f}" y="{ys:.2f}" text-anchor="middle" '
            f'font-size="6.0" fill="{sub_color}">{escape(sublabel)}</text>'
        )
    else:
        yt = baseline_in_band(title, y, h, title_size, bold=True)
        lines.append(
            f'      <text x="{cx:.2f}" y="{yt:.2f}" text-anchor="middle" '
            f'font-size="{title_size}" font-weight="700" fill="{C_TEXT}">{escape(title)}</text>'
        )
    lines.append("    </g>")
    return "\n".join(lines)


def draw_edge(
    edge_id: str,
    *,
    src: str,
    dst: str,
    edge_kind: str,
    d: str,
    stroke: str,
    stroke_width: float,
    marker: str,
    dash: str | None = None,
    label: str | None = None,
    label_pos: tuple[float, float] | None = None,
    label_anchor: str = "middle",
    label_color: str | None = None,
    label_bold: bool = False,
    label_lines: list[tuple[str, float, float]] | None = None,
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    out = [
        f'    <g id="e:{edge_id}" data-kind="edge" data-from="{src}" data-to="{dst}" data-edge-kind="{edge_kind}">',
        f'      <path d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}"'
        f'{dash_attr} marker-end="url(#{marker})"/>',
    ]
    col = label_color or (C_ARROW_RED if stroke == C_ARROW_RED else C_TEXT_MUTED)
    wt = ' font-weight="700"' if label_bold else ""
    if label_lines:
        for txt, lx, ly in label_lines:
            out.append(
                f'      <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{label_anchor}" '
                f'font-size="6.0"{wt} fill="{col}">{escape(txt)}</text>'
            )
    elif label and label_pos:
        lx, ly = label_pos
        out.append(
            f'      <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{label_anchor}" '
            f'font-size="6.0"{wt} fill="{col}">{escape(label)}</text>'
        )
    out.append("    </g>")
    return "\n".join(out)


def build_legend() -> str:
    items = [
        ("leg-existing", "fill", C_EXISTING_BG, C_EXISTING_STROKE, "Existing / Baseline"),
        ("leg-safeguard", "fill", C_ACCENT_BG, C_ACCENT_STROKE, "colabctl Safeguard"),
        ("leg-safe", "fill", C_SAFE_BG, C_SAFE_STROKE, "Active / Safe"),
        ("leg-stop", "fill", C_STOP_BG, C_STOP_STROKE, "Blocked / Stop Billing"),
        ("leg-auto", "line-solid", C_ARROW_MAIN, "", "Data / Auto Transition"),
        ("leg-control", "line-dashed", C_ARROW_CTRL, "", "User Control (extend)"),
    ]
    y_top, h = 4.0, 18.0
    ymid = y_top + h / 2.0
    y_txt = baseline_in_band("Existing / Baseline", y_top, h, 6.0, bold=False)

    swatch_w = {"fill": 8.5, "line-solid": 13.0, "line-dashed": 13.0}
    gap_swatch = 3.0
    widths = [swatch_w[kind] + gap_swatch + width_of(lbl, FONT_KEY, 6.0)[0] for _, kind, _, _, lbl in items]
    item_gap = (496.0 - 16.0 - sum(widths)) / (len(items) - 1)
    x = 12.0

    parts = [
        '  <g id="legend" data-kind="legend">',
        f'    <rect x="4" y="{y_top}" width="496" height="{h}" rx="3" '
        f'fill="#ffffff" stroke="#cbd2d9" stroke-width="{SW_THIN}"/>',
    ]
    for item_id, kind, c1, c2, label in items:
        sw = swatch_w[kind]
        parts.append(f'    <g id="legend:{item_id}" data-kind="legend-item">')
        if kind == "fill":
            parts.append(
                f'      <rect x="{x:.1f}" y="{ymid - 3.5:.1f}" width="{sw}" height="7.0" rx="1.2" '
                f'fill="{c1}" stroke="{c2}" stroke-width="{SW_THIN}"/>'
            )
        elif kind == "line-solid":
            parts.append(
                f'      <path d="M{x:.1f} {ymid:.1f} H{x + sw - 2.5:.1f}" fill="none" '
                f'stroke="{c1}" stroke-width="{SW_MAIN}" marker-end="url(#arrow-main)"/>'
            )
        elif kind == "line-dashed":
            parts.append(
                f'      <path d="M{x:.1f} {ymid:.1f} H{x + sw - 2.5:.1f}" fill="none" '
                f'stroke="{c1}" stroke-width="{SW_THIN}" stroke-dasharray="2.6 1.8" marker-end="url(#arrow-ctrl)"/>'
            )
        parts.append(
            f'      <text x="{x + sw + gap_swatch:.1f}" y="{y_txt:.2f}" '
            f'font-size="6.0" fill="{C_TEXT}">{escape(label)}</text>'
        )
        parts.append("    </g>")
        x += sw + gap_swatch + width_of(label, FONT_KEY, 6.0)[0] + item_gap
    parts.append("  </g>")
    return "\n".join(parts)


def build_panel_a() -> str:
    # Panel (a): x=4..250 (w=246), y=28..208 (h=180), headroom y=28..45
    y_ptitle = baseline_in_band("(a) Single-Slot SSH Multiplexing (Before vs. After)", 28.0, 17.0, 7.2, bold=True)

    # Sub-panel (a1) Without colabctl: y=46..123 (equal 37pt gaps: 54..91 and 157..194)
    sub1_y = 53.5
    b_edges = "\n".join(
        [
            # Terminal -> ws-gate (slot 1 OK)
            draw_edge(
                "e-b-term",
                src="c-term@mux-before",
                dst="ws-gate",
                edge_kind="data",
                d="M54 66 H89.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label="slot 1",
                label_pos=(72, 63),
            ),
            # VS Code -> ws-gate (blocked 429)
            draw_edge(
                "e-b-vsc",
                src="c-vscode@mux-before",
                dst="ws-gate",
                edge_kind="feedback",
                d="M54 84 H89.8",
                stroke=C_ARROW_RED,
                stroke_width=SW_MAIN,
                marker="arrow-red",
                label="HTTP 429",
                label_pos=(72, 81),
                label_color=C_ARROW_RED,
                label_bold=True,
            ),
            # -L 8188 -> ws-gate (blocked 429)
            draw_edge(
                "e-b-tun",
                src="c-tunnel@mux-before",
                dst="ws-gate",
                edge_kind="feedback",
                d="M54 102 H89.8",
                stroke=C_ARROW_RED,
                stroke_width=SW_MAIN,
                marker="arrow-red",
                label="HTTP 429",
                label_pos=(72, 99),
                label_color=C_ARROW_RED,
                label_bold=True,
            ),
            # ws-gate -> VM sshd (only slot 1 passes)
            draw_edge(
                "e-b-ok",
                src="ws-gate",
                dst="vm-sshd@mux-before",
                edge_kind="data",
                d="M157 66 H192.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label="1 OK",
                label_pos=(175, 63),
                label_color=C_GREEN_TEXT,
                label_bold=True,
            ),
        ]
    )

    # Blocked badge centered cleanly in the 37pt corridor (157..194)
    y_rej = baseline_in_band("429 ×2", 84.0, 18.0, 6.0, bold=True)
    b_nodes = "\n".join(
        [
            draw_box("c-term@mux-before", x=12, y=59, w=42, h=14, fill=C_EXISTING_BG, stroke=C_EXISTING_STROKE, title="Terminal", panel_attr="mux-before", title_size=6.0),
            draw_box("c-vscode@mux-before", x=12, y=77, w=42, h=14, fill=C_EXISTING_BG, stroke=C_EXISTING_STROKE, title="VS Code", panel_attr="mux-before", title_size=6.0),
            draw_box("c-tunnel@mux-before", x=12, y=95, w=42, h=14, fill=C_EXISTING_BG, stroke=C_EXISTING_STROKE, title="-L 8188", panel_attr="mux-before", title_size=6.0),
            draw_box(
                "ws-gate",
                x=91,
                y=59,
                w=66,
                h=50,
                fill=C_EXT_BG,
                stroke=C_EXT_STROKE,
                title="Colab SSH-WS",
                sublabel="1-slot limit",
                role="external",
                panel_attr="mux-before",
                title_size=6.2,
            ),
            draw_box(
                "vm-sshd@mux-before",
                x=194,
                y=59,
                w=48,
                h=50,
                fill=C_EXISTING_BG,
                stroke=C_EXISTING_STROKE,
                title="VM sshd",
                sublabel="1 WS slot",
                panel_attr="mux-before",
                title_size=6.2,
            ),
            f'    <g id="a:b-reject" data-kind="annotation">',
            f'      <rect x="161" y="84" width="29" height="18" rx="2" fill="{C_STOP_BG}" stroke="{C_STOP_STROKE}" stroke-width="{SW_THIN}"/>',
            f'      <text x="175.5" y="{y_rej:.2f}" text-anchor="middle" font-size="6.0" font-weight="700" fill="{C_ARROW_RED}">429 ×2</text>',
            f"    </g>",
        ]
    )

    # Sub-panel (a2) With colabctl: y=126..206
    sub2_y = 134.5
    a_edges = "\n".join(
        [
            draw_edge("e-a-term", src="c-term@mux-after", dst="mux-box", edge_kind="data", d="M54 147 H65 V158 H74.8", stroke=C_ARROW_MAIN, stroke_width=SW_THIN, marker="arrow-main"),
            draw_edge("e-a-vsc", src="c-vscode@mux-after", dst="mux-box", edge_kind="data", d="M54 165 H74.8", stroke=C_ARROW_MAIN, stroke_width=SW_THIN, marker="arrow-main"),
            draw_edge("e-a-tun", src="c-tunnel@mux-after", dst="mux-box", edge_kind="data", d="M54 183 H65 V172 H74.8", stroke=C_ARROW_MAIN, stroke_width=SW_THIN, marker="arrow-main"),
            draw_edge(
                "e-a-ws",
                src="mux-box",
                dst="vm-sshd@mux-after",
                edge_kind="data",
                d="M150 165 H192.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label_lines=[("1 WS slot", 172, 160), ("zero 429", 172, 174)],
                label_color=C_GREEN_TEXT,
                label_bold=True,
            ),
        ]
    )

    a_nodes = "\n".join(
        [
            draw_box("c-term@mux-after", x=12, y=140, w=42, h=14, fill=C_EXISTING_BG, stroke=C_EXISTING_STROKE, title="Terminal", panel_attr="mux-after", title_size=6.0),
            draw_box("c-vscode@mux-after", x=12, y=158, w=42, h=14, fill=C_EXISTING_BG, stroke=C_EXISTING_STROKE, title="VS Code", panel_attr="mux-after", title_size=6.0),
            draw_box("c-tunnel@mux-after", x=12, y=176, w=42, h=14, fill=C_EXISTING_BG, stroke=C_EXISTING_STROKE, title="-L 8188", panel_attr="mux-after", title_size=6.0),
            draw_box(
                "mux-box",
                x=76,
                y=140,
                w=74,
                h=50,
                fill=C_ACCENT_BG,
                stroke=C_ACCENT_STROKE,
                title="ControlMaster Mux",
                title_lines=["ControlMaster", "Mux"],
                sublabel="1 Unix socket · ~1s",
                role="novel",
                panel_attr="mux-after",
                delta_attr="d-mux-added",
                sub_color=C_TEXT_ON_ACCENT_SUB,
                title_size=6.3,
            ),
            draw_box(
                "vm-sshd@mux-after",
                x=194,
                y=140,
                w=48,
                h=50,
                fill=C_SAFE_BG,
                stroke=C_SAFE_STROKE,
                title="VM sshd",
                sublabel="all shared",
                panel_attr="mux-after",
                title_size=6.2,
            ),
        ]
    )

    return f"""  <g id="p:mux-compare" data-kind="panel">
    <rect x="4" y="28" width="246" height="180" rx="3" fill="{C_PANEL_BG}" stroke="{C_PANEL_STROKE}" stroke-width="{SW_THIN}"/>
    <text x="10" y="{y_ptitle:.2f}" font-size="7.2" font-weight="700" fill="{C_TEXT}">(a) Single-Slot SSH Multiplexing (Before vs. After)</text>

    <g id="p:mux-before" data-kind="panel">
      <text x="12" y="{sub1_y:.1f}" font-size="6.0" font-weight="700" fill="{C_TEXT_MUTED}">Without colabctl (Baseline)</text>
{b_edges}
{b_nodes}
      <text x="127" y="119.5" text-anchor="middle" font-size="6.0" font-weight="700" fill="{C_ARROW_RED}">1/3 OK · HTTP 429 on concurrent use</text>
    </g>

    <line x1="12" y1="125" x2="242" y2="125" stroke="#cbd2d9" stroke-width="{SW_THIN}" stroke-dasharray="3 2"/>

    <g id="p:mux-after" data-kind="panel">
      <text x="12" y="{sub2_y:.1f}" font-size="6.0" font-weight="700" fill="{C_TEXT}">With colabctl (Pre-Warmed ControlMaster)</text>
{a_edges}
{a_nodes}
      <text x="127" y="201.5" text-anchor="middle" font-size="6.0" font-weight="700" fill="{C_GREEN_TEXT}">All concurrent clients OK · 0 HTTP 429</text>
    </g>
  </g>"""


def build_panel_b() -> str:
    # Panel (b): x=258..500 (w=242), y=28..208 (h=180), headroom y=28..45
    y_ptitle = baseline_in_band("(b) Autonomous VM Cost-Guard Watchdog (In-VM)", 28.0, 17.0, 7.2, bold=True)

    # 4 states in a clean 2x2 planar layout:
    # st-active:     x=282..366 (w=84), y=64..96 (h=32)
    # st-idle:       x=408..492 (w=84), y=64..96 (h=32)
    # st-unassigned: x=272..366 (w=94), y=144..178 (h=34)
    # st-warn:       x=408..492 (w=84), y=144..178 (h=34)

    edges = "\n".join(
        [
            # Entry dot -> st-active
            f'    <g id="a:fsm-entry" data-kind="annotation">',
            f'      <circle cx="266" cy="80" r="2.6" fill="{C_ARROW_MAIN}"/>',
            f'      <path d="M268.6 80 H280.8" fill="none" stroke="{C_ARROW_MAIN}" stroke-width="{SW_MAIN}" marker-end="url(#arrow-main)"/>',
            f'      <text x="272" y="74.5" text-anchor="middle" font-size="6.0" fill="{C_TEXT_MUTED}">up</text>',
            f"    </g>",
            # Self-loop on st-active (top corridor y=49..64)
            draw_edge(
                "t-busy",
                src="st-active",
                dst="st-active",
                edge_kind="transition",
                d="M312 64 V54 H336 V62.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_THIN,
                marker="arrow-main",
                label="poll 15s: busy",
                label_pos=(324, 51.5),
            ),
            # st-active -> st-idle (upper arrow y=73)
            draw_edge(
                "t-to-idle",
                src="st-active",
                dst="st-idle",
                edge_kind="transition",
                d="M366 73 H406.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label_lines=[("GPU <5%", 387, 62), ("no PTY", 387, 69)],
            ),
            # st-idle -> st-active (lower arrow y=87)
            draw_edge(
                "t-resume",
                src="st-idle",
                dst="st-active",
                edge_kind="transition",
                d="M408 87 H367.2",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_THIN,
                marker="arrow-main",
                label="GPU / PTY",
                label_pos=(387, 95),
            ),
            # st-idle -> st-warn (vertical right x=460)
            draw_edge(
                "t-idle-warn",
                src="st-idle",
                dst="st-warn",
                edge_kind="transition",
                d="M460 96 V142.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label_lines=[("idle", 464, 117), ("≥ 28m", 464, 124)],
                label_anchor="start",
            ),
            # st-active -> st-warn (hard limit upper mid-corridor y=112, strictly above extend!)
            draw_edge(
                "t-hard-warn",
                src="st-active",
                dst="st-warn",
                edge_kind="transition",
                d="M352 96 V112 H436 V142.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_THIN,
                marker="arrow-main",
                label="hard limit T-2m",
                label_pos=(398, 108.5),
            ),
            # st-warn -> st-active (dashed user extend +2h in lower mid-corridor y=126, zero crossing!)
            draw_edge(
                "t-extend",
                src="st-warn",
                dst="st-active",
                edge_kind="transition",
                d="M420 144 V126 H318 V97.2",
                stroke=C_ARROW_CTRL,
                stroke_width=SW_THIN,
                dash="2.6 1.8",
                marker="arrow-ctrl",
                label="extend +2h (user)",
                label_pos=(368, 123),
            ),
            # RED: st-warn -> st-unassigned (offline-safe autonomous unassign!)
            draw_edge(
                "t-unassign",
                src="st-warn",
                dst="st-unassigned",
                edge_kind="transition",
                d="M408 161 H367.2",
                stroke=C_ARROW_RED,
                stroke_width=SW_MAIN,
                marker="arrow-red",
                label_lines=[("2m elapsed", 387, 155), ("/unassign", 387, 170)],
                label_color=C_ARROW_RED,
                label_bold=True,
            ),
        ]
    )

    nodes = "\n".join(
        [
            draw_box(
                "st-active",
                x=282,
                y=64,
                w=84,
                h=32,
                fill=C_SAFE_BG,
                stroke=C_SAFE_STROKE,
                title="Active",
                sublabel="GPU ≥5% / PTY / HB",
                role="existing",
                panel_attr="watchdog-fsm",
                rx=5.0,
            ),
            draw_box(
                "st-idle",
                x=408,
                y=64,
                w=84,
                h=32,
                fill=C_CORE_BG,
                stroke=C_CORE_STROKE,
                title="Idle Countdown",
                sublabel="idle timer (30m)",
                role="novel",
                panel_attr="watchdog-fsm",
                rx=5.0,
            ),
            draw_box(
                "st-warn",
                x=408,
                y=144,
                w=84,
                h=34,
                fill=C_ACCENT_BG,
                stroke=C_ACCENT_STROKE,
                title="Warning (T-2m)",
                sublabel="PTY broadcast",
                role="novel",
                panel_attr="watchdog-fsm",
                sub_color=C_TEXT_ON_ACCENT_SUB,
                rx=5.0,
            ),
            draw_box(
                "st-unassigned",
                x=272,
                y=144,
                w=94,
                h=34,
                fill=C_STOP_BG,
                stroke=C_STOP_STROKE,
                title="Unassigned",
                sublabel="0 CU/hr (offline-safe)",
                role="external",
                panel_attr="watchdog-fsm",
                sub_color=C_ARROW_RED,
                rx=5.0,
                double_border=True,
                stroke_w=SW_MAIN,
            ),
        ]
    )

    return f"""  <g id="p:watchdog-fsm" data-kind="panel">
    <rect x="258" y="28" width="242" height="180" rx="3" fill="{C_PANEL_BG}" stroke="{C_PANEL_STROKE}" stroke-width="{SW_THIN}"/>
    <text x="264" y="{y_ptitle:.2f}" font-size="7.2" font-weight="700" fill="{C_TEXT}">(b) Autonomous VM Cost-Guard Watchdog (In-VM)</text>
{edges}
{nodes}
    <g id="a:fsm-note" data-kind="annotation">
      <text x="379" y="191.5" text-anchor="middle" font-size="6.0" fill="{C_TEXT_MUTED}">POST $TBE_RUNTIME_ADDR/unassign directly from VM</text>
      <text x="379" y="201.0" text-anchor="middle" font-size="6.0" font-weight="700" fill="{C_TEXT}">Stops billing even if laptop sleeps or disconnects</text>
    </g>
  </g>"""


def main() -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}pt" height="{H}pt"
     font-family="{FONT_STACK}" font-size="6.5"
     data-spec="colabctl-fig2" data-spec-version="1">
  <defs>
    <marker id="arrow-main" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="4.2" markerHeight="4.2" orient="auto-start-reverse">
      <path d="M0 1.2 L9 5 L0 8.8 Z" fill="{C_ARROW_MAIN}"/>
    </marker>
    <marker id="arrow-ctrl" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="4.6" markerHeight="4.6" orient="auto-start-reverse">
      <path d="M0 1.2 L9 5 L0 8.8 Z" fill="{C_ARROW_CTRL}"/>
    </marker>
    <marker id="arrow-red" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="4.2" markerHeight="4.2" orient="auto-start-reverse">
      <path d="M0 1.2 L9 5 L0 8.8 Z" fill="{C_ARROW_RED}"/>
    </marker>
  </defs>

  <rect x="0" y="0" width="{W}" height="{H}" fill="{C_CANVAS}"/>

{build_panel_a()}

{build_panel_b()}

{build_legend()}
</svg>
"""
    OUT_SVG.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUT_SVG} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
