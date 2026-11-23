#!/usr/bin/env python3
"""Generate publication-quality SVG for colabctl v0.2 full-stack workflow (504 x 214 pt)."""

from __future__ import annotations

import os
import re
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
ICON_DIR = FIG_DIR / "icons"
OUT_SVG = FIG_DIR / "fig.svg"

FONT_KEY = "helvetica"
FONT_STACK = "'TeX Gyre Heros', 'Helvetica Neue', Helvetica, Arimo, Arial, sans-serif"

W = 504
H = 214

# Strictly 2 stroke widths across the entire SVG (corpus norm: thin 0.65 pt, main 1.15 pt)
SW_THIN = 0.65
SW_MAIN = 1.15

# Blue-orange house palette (max 2 saturated fills: #ed7d31, #c00000)
C_CANVAS = "#ffffff"
C_CONT_BG = "#f7f9fc"
C_CONT_EXT = "#f4f5f7"
C_CONT_STROKE = "#7b8794"
C_EXISTING_BG = "#dae8fc"
C_EXISTING_STROKE = "#4c6e9b"
C_CORE_BG = "#fff2cc"
C_CORE_STROKE = "#a67500"
C_ACCENT_BG = "#ed7d31"
C_ACCENT_STROKE = "#8f3f08"
C_EXT_BG = "#eceff1"
C_EXT_STROKE = "#607d8b"
C_TEXT = "#0d0d0d"
C_TEXT_MUTED = "#4a5568"
C_TEXT_ON_ACCENT_SUB = "#2b1200"
C_ARROW_MAIN = "#1f2937"
C_ARROW_CTRL = "#52606d"
C_ARROW_RED = "#c00000"
C_BADGE_NEUTRAL = "#334155"
C_BADGE_RED = "#c00000"
C_ICON_BLUE = "#244775"
C_ICON_CORE = "#7a5200"
C_ICON_ACCENT = "#1f0e00"
C_ICON_EXT = "#455a64"


def extract_icon_inner(icon_name: str) -> str:
    raw = (ICON_DIR / f"{icon_name}.svg").read_text(encoding="utf-8")
    m = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.DOTALL)
    if not m:
        raise ValueError(f"Could not parse SVG inner markup for {icon_name}")
    inner = m.group(1).strip()
    inner = inner.replace('stroke="currentColor"', "")
    inner = inner.replace('fill="currentColor"', "")
    inner = re.sub(r'stroke-width="[^"]*"', "", inner)
    inner = re.sub(
        r"<(path|rect|circle|line|polyline|polygon)\b",
        r'<\1 vector-effect="non-scaling-stroke"',
        inner,
    )
    return inner


def baseline_in_band(text: str, y_top: float, band_h: float, size: float, bold: bool = False) -> float:
    above, below = K.ink_band(text, size, FONT_KEY, bold)
    mid = y_top + band_h / 2.0
    return round(mid + (above - below) / 2.0, 2)


def draw_icon(icon_name: str, x: float, y: float, size_pt: float, stroke: str) -> str:
    scale = size_pt / 24.0
    inner = extract_icon_inner(icon_name)
    return (
        f'    <g data-symbol="lucide-{icon_name}" '
        f'transform="translate({x:.2f},{y:.2f}) scale({scale:.4f})" '
        f'fill="none" stroke="{stroke}" stroke-width="{SW_THIN}" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</g>'
    )


def draw_node(
    node_id: str,
    *,
    role: str,
    parent: str,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    stroke: str,
    title_lines: list[str],
    sublabel: str,
    icon_name: str,
    icon_stroke: str,
    sub_color: str = C_TEXT_MUTED,
    center_icon_with_text: bool = False,
) -> str:
    icon_size = 9.0
    icon_y = y + (h - icon_size) / 2.0

    max_title_w = max(width_of(t, FONT_KEY, 6.5, bold=True)[0] for t in title_lines)
    sub_w = width_of(sublabel, FONT_KEY, 6.0, bold=False)[0]
    block_w = max(max_title_w, sub_w)

    if center_icon_with_text:
        gap = 5.0
        total_w = icon_size + gap + block_w
        icon_x = x + (w - total_w) / 2.0
        cx = icon_x + icon_size + gap + block_w / 2.0
    else:
        icon_x = x + 4.5
        text_x0 = x + 15.5
        text_w = w - 18.0
        cx = text_x0 + text_w / 2.0

    lines: list[str] = [
        f'  <g id="n:{node_id}" data-kind="node" data-role="{role}" data-parent="{parent}">',
        f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2.5" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{SW_THIN}"/>',
        draw_icon(icon_name, icon_x, icon_y, icon_size, icon_stroke),
    ]

    if len(title_lines) == 1:
        t1 = title_lines[0]
        y_t = baseline_in_band(t1, y + 3.5, (h - 7.0) * 0.50, 6.5, bold=True)
        y_s = baseline_in_band(sublabel, y + 3.5 + (h - 7.0) * 0.50, (h - 7.0) * 0.50, 6.0, bold=False)
        lines.append(
            f'    <text x="{cx:.2f}" y="{y_t:.2f}" text-anchor="middle" '
            f'font-size="6.5" font-weight="700" fill="{C_TEXT}">{escape(t1)}</text>'
        )
        lines.append(
            f'    <text x="{cx:.2f}" y="{y_s:.2f}" text-anchor="middle" '
            f'font-size="6.0" fill="{sub_color}">{escape(sublabel)}</text>'
        )
    else:
        t1, t2 = title_lines[0], title_lines[1]
        y_t1 = baseline_in_band(t1, y + 2.5, 9.0, 6.5, bold=True)
        y_t2 = baseline_in_band(t2, y + 11.0, 9.0, 6.5, bold=True)
        y_s = baseline_in_band(sublabel, y + 21.5, h - 23.5, 6.0, bold=False)
        lines.append(
            f'    <text x="{cx:.2f}" y="{y_t1:.2f}" text-anchor="middle" '
            f'font-size="6.5" font-weight="700" fill="{C_TEXT}">{escape(t1)}</text>'
        )
        lines.append(
            f'    <text x="{cx:.2f}" y="{y_t2:.2f}" text-anchor="middle" '
            f'font-size="6.5" font-weight="700" fill="{C_TEXT}">{escape(t2)}</text>'
        )
        lines.append(
            f'    <text x="{cx:.2f}" y="{y_s:.2f}" text-anchor="middle" '
            f'font-size="6.0" fill="{sub_color}">{escape(sublabel)}</text>'
        )
    lines.append("  </g>")
    return "\n".join(lines)


def draw_step_badge(n: int, attached_to: str, cx: float, cy: float, *, fill: str = C_BADGE_NEUTRAL) -> str:
    r = 4.6
    y_num = baseline_in_band(str(n), cy - r, 2 * r, 5.5, bold=True)
    return (
        f'  <g id="s:{n}" data-kind="step" data-attached-to="{attached_to}">\n'
        f'    <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"/>\n'
        f'    <text x="{cx:.1f}" y="{y_num:.2f}" text-anchor="middle" '
        f'font-size="5.5" font-weight="700" fill="#ffffff">{n}</text>\n'
        f"  </g>"
    )


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
    step: int | None = None,
    label: str | None = None,
    label_pos: tuple[float, float] | None = None,
    label_anchor: str = "middle",
    label_color: str | None = None,
    label_bold: bool = False,
    label_lines: list[tuple[str, float, float]] | None = None,
) -> str:
    step_attr = f' data-step="{step}"' if step is not None else ""
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    out = [
        f'  <g id="e:{edge_id}" data-kind="edge" data-from="{src}" data-to="{dst}" '
        f'data-edge-kind="{edge_kind}"{step_attr}>',
        f'    <path d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}"'
        f'{dash_attr} marker-end="url(#{marker})"/>',
    ]
    col = label_color or (C_ARROW_RED if stroke == C_ARROW_RED else C_TEXT_MUTED)
    wt = ' font-weight="700"' if label_bold else ""
    if label_lines:
        for txt, lx, ly in label_lines:
            out.append(
                f'    <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{label_anchor}" '
                f'font-size="6.0"{wt} fill="{col}">{escape(txt)}</text>'
            )
    elif label and label_pos:
        lx, ly = label_pos
        out.append(
            f'    <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{label_anchor}" '
            f'font-size="6.0"{wt} fill="{col}">{escape(label)}</text>'
        )
    out.append("  </g>")
    return "\n".join(out)


def build_legend() -> str:
    items = [
        ("leg-existing", "fill", C_EXISTING_BG, C_EXISTING_STROKE, "Existing / Runtime"),
        ("leg-core", "fill", C_CORE_BG, C_CORE_STROKE, "colabctl Core / UI (New)"),
        ("leg-safeguard", "fill", C_ACCENT_BG, C_ACCENT_STROKE, "Safeguards (New)"),
        ("leg-main", "line-solid", C_ARROW_MAIN, "", "UI / CLI / Mux Path"),
        ("leg-control", "line-dashed", C_ARROW_CTRL, "", "Control / Monitor"),
        ("leg-unassign", "line-red", C_ARROW_RED, "", "Auto-Unassign (Stop Billing)"),
    ]
    y_top, h = 4.0, 18.0
    ymid = y_top + h / 2.0
    y_txt = baseline_in_band("Existing / Runtime", y_top, h, 6.0, bold=False)

    swatch_w = {"fill": 8.5, "line-solid": 13.0, "line-dashed": 13.0, "line-red": 13.0}
    gap_swatch = 3.2
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
        elif kind == "line-red":
            parts.append(
                f'      <path d="M{x:.1f} {ymid:.1f} H{x + sw - 2.5:.1f}" fill="none" '
                f'stroke="{c1}" stroke-width="{SW_MAIN}" marker-end="url(#arrow-red)"/>'
            )
        parts.append(
            f'      <text x="{x + sw + gap_swatch:.1f}" y="{y_txt:.2f}" '
            f'font-size="6.0" fill="{C_TEXT}">{escape(label)}</text>'
        )
        parts.append("    </g>")
        x += sw + gap_swatch + width_of(label, FONT_KEY, 6.0)[0] + item_gap
    parts.append("  </g>")
    return "\n".join(parts)


def main() -> None:
    # 3 aligned outer containers (y=28..208, h=180; 18pt headroom y=28..46)
    c_host = (4, 28, 208, 180)    # x=4..212
    c_cloud = (220, 28, 88, 180)  # x=220..308
    c_vm = (316, 28, 184, 180)    # x=316..500

    y_ctitle = baseline_in_band("Local Host (macOS / Linux)", 28.0, 18.0, 7.5, bold=True)

    containers_svg = "\n".join(
        [
            '  <g id="c:local-host" data-kind="container" data-role="existing">',
            f'    <rect x="{c_host[0]}" y="{c_host[1]}" width="{c_host[2]}" height="{c_host[3]}" rx="3" '
            f'fill="{C_CONT_BG}" stroke="{C_CONT_STROKE}" stroke-width="{SW_THIN}"/>',
            f'    <text x="{c_host[0] + 6}" y="{y_ctitle:.2f}" font-size="7.5" font-weight="700" '
            f'fill="{C_TEXT}">Local Host (macOS / Linux)</text>',
            "  </g>",
            '  <g id="c:colab-cloud" data-kind="container" data-role="external">',
            f'    <rect x="{c_cloud[0]}" y="{c_cloud[1]}" width="{c_cloud[2]}" height="{c_cloud[3]}" rx="3" '
            f'fill="{C_CONT_EXT}" stroke="{C_CONT_STROKE}" stroke-width="{SW_THIN}"/>',
            f'    <text x="{c_cloud[0] + 6}" y="{y_ctitle:.2f}" font-size="7.5" font-weight="700" '
            f'fill="{C_TEXT}">Google Colab Cloud</text>',
            "  </g>",
            '  <g id="c:gpu-vm" data-kind="container" data-role="existing">',
            f'    <rect x="{c_vm[0]}" y="{c_vm[1]}" width="{c_vm[2]}" height="{c_vm[3]}" rx="3" '
            f'fill="{C_CONT_BG}" stroke="{C_CONT_STROKE}" stroke-width="{SW_THIN}"/>',
            f'    <text x="{c_vm[0] + 6}" y="{y_ctitle:.2f}" font-size="7.5" font-weight="700" '
            f'fill="{C_TEXT}">Colab Cloud GPU VM</text>',
            "  </g>",
        ]
    )

    # Top row y=46..80 (h=34); mid row y=104..138 (h=34); bottom row y=166..202 (h=36)
    nodes_svg = "\n".join(
        [
            draw_node(
                "web-ui",
                role="novel",
                parent="local-host",
                x=10,
                y=46,
                w=84,
                h=34,
                fill=C_CORE_BG,
                stroke=C_CORE_STROKE,
                title_lines=["Web / Chromium UI"],
                sublabel="127.0.0.1 · EN/ZH",
                icon_name="layout-dashboard",
                icon_stroke=C_ICON_CORE,
            ),
            draw_node(
                "cli-clients",
                role="existing",
                parent="local-host",
                x=10,
                y=104,
                w=84,
                h=34,
                fill=C_EXISTING_BG,
                stroke=C_EXISTING_STROKE,
                title_lines=["CLI & SSH Clients"],
                sublabel="up · ssh · VS Code",
                icon_name="terminal",
                icon_stroke=C_ICON_BLUE,
            ),
            draw_node(
                "colabctl-controller",
                role="novel",
                parent="local-host",
                x=120,
                y=46,
                w=86,
                h=34,
                fill=C_CORE_BG,
                stroke=C_CORE_STROKE,
                title_lines=["colabctl Controller"],
                sublabel="reap · sync · jobs",
                icon_name="workflow",
                icon_stroke=C_ICON_CORE,
            ),
            draw_node(
                "account-pool",
                role="existing",
                parent="local-host",
                x=120,
                y=104,
                w=86,
                h=34,
                fill=C_EXISTING_BG,
                stroke=C_EXISTING_STROKE,
                title_lines=["Multi-Account Pool"],
                sublabel="ultra · pro1 · pro2",
                icon_name="key-round",
                icon_stroke=C_ICON_BLUE,
            ),
            draw_node(
                "ssh-mux",
                role="novel",
                parent="local-host",
                x=10,
                y=166,
                w=196,
                h=36,
                fill=C_ACCENT_BG,
                stroke=C_ACCENT_STROKE,
                title_lines=["SSH Mux & _proxy"],
                sublabel="Include ssh_config · ControlMaster · no auto-create",
                icon_name="network",
                icon_stroke=C_ICON_ACCENT,
                sub_color=C_TEXT_ON_ACCENT_SUB,
                center_icon_with_text=True,
            ),
            draw_node(
                "colab-api",
                role="external",
                parent="colab-cloud",
                x=225,
                y=46,
                w=78,
                h=34,
                fill=C_EXT_BG,
                stroke=C_EXT_STROKE,
                title_lines=["Colab Control API"],
                sublabel="/assign · /unassign",
                icon_name="cloud",
                icon_stroke=C_ICON_EXT,
            ),
            draw_node(
                "gpu-runtime",
                role="existing",
                parent="gpu-vm",
                x=322,
                y=46,
                w=80,
                h=34,
                fill=C_EXISTING_BG,
                stroke=C_EXISTING_STROKE,
                title_lines=["GPU Runtime"],
                sublabel="T4/L4/A100/G4/H100",
                icon_name="cpu",
                icon_stroke=C_ICON_BLUE,
            ),
            draw_node(
                "tbe-hook",
                role="external",
                parent="gpu-vm",
                x=414,
                y=46,
                w=80,
                h=34,
                fill=C_EXT_BG,
                stroke=C_EXT_STROKE,
                title_lines=["TBE Unassign", "Hook"],
                sublabel="$TBE_ADDR /unassign",
                icon_name="power",
                icon_stroke=C_ICON_EXT,
            ),
            draw_node(
                "vm-sshd",
                role="existing",
                parent="gpu-vm",
                x=322,
                y=166,
                w=80,
                h=36,
                fill=C_EXISTING_BG,
                stroke=C_EXISTING_STROKE,
                title_lines=["VM sshd Daemon"],
                sublabel="Ed25519 · 1 WS slot",
                icon_name="server",
                icon_stroke=C_ICON_BLUE,
            ),
            draw_node(
                "cost-watchdog",
                role="novel",
                parent="gpu-vm",
                x=414,
                y=166,
                w=80,
                h=36,
                fill=C_ACCENT_BG,
                stroke=C_ACCENT_STROKE,
                title_lines=["Cost-Guard", "Watchdog"],
                sublabel="GPU <5% · PTY · 4h",
                icon_name="shield-check",
                icon_stroke=C_ICON_ACCENT,
                sub_color=C_TEXT_ON_ACCENT_SUB,
            ),
        ]
    )

    edges_svg = "\n".join(
        [
            # 1: web-ui -> colabctl-controller (straight right at y=63)
            draw_edge(
                "e-web-ctrl",
                src="web-ui",
                dst="colabctl-controller",
                edge_kind="data",
                d="M94 63 H118.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                step=1,
                label="API / UI",
                label_pos=(107, 73),
            ),
            # cli-clients -> colabctl-controller (planar route strictly above e-ctrl-mux!)
            draw_edge(
                "e-cli-ctrl",
                src="cli-clients",
                dst="colabctl-controller",
                edge_kind="data",
                d="M78 104 V88 H125 V81.2",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label="up/stop",
                label_pos=(74, 96),
                label_anchor="end",
            ),
            # 2: colabctl-controller -> account-pool
            draw_edge(
                "e-ctrl-pool",
                src="colabctl-controller",
                dst="account-pool",
                edge_kind="control",
                d="M163 80 V102.8",
                stroke=C_ARROW_CTRL,
                stroke_width=SW_THIN,
                dash="2.6 1.8",
                marker="arrow-ctrl",
                step=2,
                label="lock & pick",
                label_pos=(167, 94),
                label_anchor="start",
            ),
            # 8: account-pool -> colab-api (routed cleanly inside Google Colab Cloud x=220..308)
            draw_edge(
                "e-pool-api",
                src="account-pool",
                dst="colab-api",
                edge_kind="control",
                d="M206 121 H250 V81.2",
                stroke=C_ARROW_CTRL,
                stroke_width=SW_THIN,
                dash="2.6 1.8",
                marker="arrow-ctrl",
                step=8,
                label_lines=[("assign /", 247, 96), ("stop", 247, 103)],
                label_anchor="end",
            ),
            # 3: colab-api -> gpu-runtime
            draw_edge(
                "e-api-deploy",
                src="colab-api",
                dst="gpu-runtime",
                edge_kind="control",
                d="M303 63 H320.8",
                stroke=C_ARROW_CTRL,
                stroke_width=SW_THIN,
                dash="2.6 1.8",
                marker="arrow-ctrl",
                step=3,
                label_lines=[("Jupyter WS:", 268, 94), ("probe GPU", 268, 101)],
                label_anchor="start",
            ),
            # colab-api -> cost-watchdog
            draw_edge(
                "e-api-watchdog",
                src="colab-api",
                dst="cost-watchdog",
                edge_kind="control",
                d="M264 80 V138 H422 V164.8",
                stroke=C_ARROW_CTRL,
                stroke_width=SW_THIN,
                dash="2.6 1.8",
                marker="arrow-ctrl",
                label_lines=[("deploy", 268, 125), ("watchdog.py", 268, 132)],
                label_anchor="start",
            ),
            # 4: colabctl-controller -> ssh-mux (clean corridor x=107, zero crossings!)
            draw_edge(
                "e-ctrl-mux",
                src="colabctl-controller",
                dst="ssh-mux",
                edge_kind="data",
                d="M136 80 V95 H107 V164.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                step=4,
                label_lines=[("sync &", 112, 150), ("pre-warm", 112, 157)],
                label_anchor="start",
            ),
            # 5: cli-clients -> ssh-mux (straight vertical down x=42)
            draw_edge(
                "e-clients-mux",
                src="cli-clients",
                dst="ssh-mux",
                edge_kind="data",
                d="M42 138 V164.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                step=5,
                label_lines=[("N× ssh, -L", 46, 150), ("VS Code", 46, 157)],
                label_anchor="start",
            ),
            # ssh-mux -> vm-sshd (single SSH-over-WS slot)
            draw_edge(
                "e-mux-sshd",
                src="ssh-mux",
                dst="vm-sshd",
                edge_kind="data",
                d="M206 184 H320.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label_lines=[
                    ("SSH-over-WS (1 slot)", 264, 178),
                    ("zero HTTP 429", 264, 194),
                ],
                label_color=C_TEXT,
            ),
            # vm-sshd -> gpu-runtime
            draw_edge(
                "e-sshd-gpu",
                src="vm-sshd",
                dst="gpu-runtime",
                edge_kind="data",
                d="M336 166 V81.2",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                label_lines=[("shells · scp", 340, 110), ("-L 8188", 340, 117)],
                label_anchor="start",
            ),
            # 6: vm-sshd -> cost-watchdog (no-PTY fast control ~1s)
            draw_edge(
                "e-sshd-wd",
                src="vm-sshd",
                dst="cost-watchdog",
                edge_kind="data",
                d="M402 184 H412.8",
                stroke=C_ARROW_MAIN,
                stroke_width=SW_MAIN,
                marker="arrow-main",
                step=6,
                label_lines=[("no-PTY", 408, 153), ("~1s", 408, 160)],
            ),
            # 7: cost-watchdog -> gpu-runtime (poll 15s)
            draw_edge(
                "e-wd-poll",
                src="cost-watchdog",
                dst="gpu-runtime",
                edge_kind="control",
                d="M438 166 V112 H384 V81.2",
                stroke=C_ARROW_CTRL,
                stroke_width=SW_THIN,
                dash="2.6 1.8",
                marker="arrow-ctrl",
                step=7,
                label="poll 15s (GPU/PTY)",
                label_pos=(412, 107.5),
            ),
            # RED: cost-watchdog -> tbe-hook
            draw_edge(
                "e-wd-unassign",
                src="cost-watchdog",
                dst="tbe-hook",
                edge_kind="feedback",
                d="M456 166 V81.2",
                stroke=C_ARROW_RED,
                stroke_width=SW_MAIN,
                marker="arrow-red",
                label_lines=[
                    ("POST", 460, 114),
                    ("/unassign", 460, 121),
                    ("idle 30m", 460, 129),
                    ("or 4h max", 460, 136),
                ],
                label_anchor="start",
                label_color=C_ARROW_RED,
                label_bold=True,
            ),
        ]
    )

    steps_svg = "\n".join(
        [
            draw_step_badge(1, "e-web-ctrl", 107.0, 55.0),
            draw_step_badge(2, "e-ctrl-pool", 153.5, 92.0),
            draw_step_badge(3, "e-api-deploy", 312.5, 55.0),
            draw_step_badge(4, "e-ctrl-mux", 107.0, 118.0),
            draw_step_badge(5, "e-clients-mux", 32.0, 152.0),
            draw_step_badge(6, "e-sshd-wd", 408.0, 195.0),
            draw_step_badge(7, "e-wd-poll", 447.0, 124.0, fill=C_BADGE_RED),
            draw_step_badge(8, "e-pool-api", 238.0, 113.0),
        ]
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}pt" height="{H}pt"
     font-family="{FONT_STACK}" font-size="6.5"
     data-spec="colabctl-fig1" data-spec-version="2">
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

{containers_svg}

{edges_svg}

{nodes_svg}

{steps_svg}

{build_legend()}
</svg>
"""
    OUT_SVG.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUT_SVG} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
