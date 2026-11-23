"""Typer + Rich CLI for colabctl."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from colabctl import __version__
from colabctl.models import (
    VALID_GPUS,
    PoolOverview,
    PoolSessionView,
    WatchdogLiveStatus,
    normalize_high_mem,
)
from colabctl.service import ColabController, ColabctlError

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="colabctl",
    help="Multi-account Google Colab GPU launcher, multiplexed SSH manager, and VM cost-guard CLI.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _controller() -> ColabController:
    return ColabController()


def _fail(exc: Exception, *, as_json: bool = False) -> None:
    if as_json:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
    else:
        err_console.print(
            Panel(Text(str(exc)), title="Error", border_style="red", box=box.ROUNDED)
        )
    raise typer.Exit(code=1)


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    secs = max(0, int(seconds))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _fmt_guard_summary(s: PoolSessionView) -> str:
    if s.watchdog_live is not None:
        wl = s.watchdog_live
        if wl.error:
            return f"[red]err[/red]"
        if wl.cancelled or not wl.running:
            return "[yellow]off[/yellow]"
        parts: list[str] = []
        if wl.remaining_idle_s is not None:
            parts.append(f"idle {_fmt_duration(wl.remaining_idle_s)}")
        if wl.remaining_deadline_s is not None:
            parts.append(f"max {_fmt_duration(wl.remaining_deadline_s)}")
        return " / ".join(parts) if parts else "[green]on[/green]"
    if s.watchdog_config is not None:
        wc = s.watchdog_config
        if not wc.enabled:
            return "[yellow]off[/yellow]"
        parts = []
        if wc.idle_timeout_s:
            parts.append(f"idle {wc.idle_timeout_s // 60}m")
        if wc.max_duration_s:
            parts.append(f"max {wc.max_duration_s / 3600:g}h")
        return " / ".join(parts) if parts else "on"
    return "-"


def _render_overview(overview: PoolOverview) -> None:
    # 1. Accounts table
    acc_table = Table(
        title="Colab Accounts",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    acc_table.add_column("", width=3)
    acc_table.add_column("Alias", style="bold")
    acc_table.add_column("Email")
    acc_table.add_column("Balance (CU)", justify="right")
    acc_table.add_column("Burn (CU/hr)", justify="right")
    acc_table.add_column("VMs", justify="right")
    acc_table.add_column("Status")

    for a in overview.accounts:
        marker = ("★" if a.primary else " ") + ("●" if a.active else " ")
        bal = f"{a.balance:.2f}" if a.balance is not None else "?"
        rate = f"{a.hourly_rate:.2f}" if a.hourly_rate is not None else "?"
        vms = str(a.assignments) if a.assignments is not None else "?"
        status = (
            f"[red]disabled ({a.disabled_reason})[/red]"
            if a.disabled
            else "[green]ready[/green]"
        )
        acc_table.add_row(marker, a.name, a.email or "-", bal, rate, vms, status)

    console.print(acc_table)
    total_bal = (
        f"{overview.total.balance:.2f}"
        if overview.total.balance is not None
        else "?"
    )
    total_rate = (
        f"{overview.total.hourly_rate:.2f}"
        if overview.total.hourly_rate is not None
        else "?"
    )
    console.print(
        f"Total: [bold]{total_bal} CU[/bold] | Burn: [bold]{total_rate} CU/hr[/bold] "
        f"| Mode: {overview.usage_mode} | ★ Primary ({overview.primary or 'unset'}) ● Active\n"
    )

    # 2. Active sessions table
    if not overview.sessions:
        console.print(
            Panel(
                "No active pooled sessions.\nStart one with: [cyan]colabctl up dev --gpu t4[/cyan]",
                title="Sessions",
                border_style="dim",
                box=box.ROUNDED,
            )
        )
    else:
        sess_table = Table(
            title="Managed GPU Sessions",
            box=box.ROUNDED,
            header_style="bold green",
        )
        sess_table.add_column("Name", style="bold")
        sess_table.add_column("Account")
        sess_table.add_column("Hardware")
        sess_table.add_column("SSH Host")
        sess_table.add_column("Mux")
        sess_table.add_column("Cost Guard")
        sess_table.add_column("State")

        for s in overview.sessions:
            if s.hardware and s.hardware.gpu_name:
                mem = (
                    f" ({s.hardware.gpu_memory_mib // 1024}GB)"
                    if s.hardware.gpu_memory_mib
                    else ""
                )
                hw = f"{s.hardware.gpu_name}{mem}"
            else:
                hw = s.accelerator or "CPU"
            mux = "[green]up[/green]" if s.ssh_mux_active else "[dim]idle[/dim]"
            state = "[red]vanished[/red]" if s.vanished else "[green]running[/green]"
            sess_table.add_row(
                s.name,
                s.account,
                hw,
                f"ssh {s.ssh_alias}",
                mux,
                _fmt_guard_summary(s),
                state,
            )
        console.print(sess_table)

    # 3. Orphan alerts (critical for preventing silent billing!)
    if overview.orphans:
        orphan_lines = [
            f"• account=[bold]{o.account}[/bold] endpoint=[bold]{o.endpoint}[/bold] hw={o.hardware or '?'}"
            for o in overview.orphans
        ]
        orphan_lines.append("\nStop all orphans: [cyan]colabctl reap --all-orphans[/cyan]")
        console.print(
            Panel(
                "\n".join(orphan_lines),
                title="[bold red]WARNING: Unmanaged Orphan VMs Still Billing![/bold red]",
                border_style="red",
                box=box.ROUNDED,
            )
        )


def _render_watchdog(name: str, wd: WatchdogLiveStatus) -> None:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    state_str = (
        "[green]RUNNING[/green]"
        if wd.running and not wd.cancelled
        else "[yellow]STOPPED / DISABLED[/yellow]"
    )
    grid.add_row("State", state_str)
    if wd.pid:
        grid.add_row("PID", str(wd.pid))
    grid.add_row("Idle timeout", _fmt_duration(wd.idle_timeout_s))
    grid.add_row("Idle so far", _fmt_duration(wd.idle_for_s))
    grid.add_row("Idle remaining", _fmt_duration(wd.remaining_idle_s))
    grid.add_row("Hard limit left", _fmt_duration(wd.remaining_deadline_s))
    if wd.gpu_util_percent is not None:
        grid.add_row("GPU util", f"{wd.gpu_util_percent:.1f}%")
    if wd.last_active_reason:
        grid.add_row("Last activity", wd.last_active_reason)
    if wd.error:
        grid.add_row("Error", f"[red]{wd.error}[/red]")
    console.print(
        Panel(grid, title=f"VM Cost Guard: {name}", border_style="cyan", box=box.ROUNDED)
    )


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"colabctl {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_cb, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Multi-account Google Colab GPU & multiplexed SSH controller."""


@app.command()
def doctor(
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Verify local dependencies, SSH keys, SSH config include, and accounts."""
    try:
        report = _controller().doctor()
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
        raise typer.Exit(code=0 if report.ok else 1)

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    for tool, path in report.binaries.items():
        grid.add_row(tool, f"[green]{path}[/green]" if path else "[red]MISSING[/red]")
    grid.add_row(
        "SSH key",
        f"[green]{report.identity_file}[/green]" if report.identity_file else "[red]MISSING[/red]",
    )
    grid.add_row(
        "~/.ssh/config Include",
        "[green]configured[/green]" if report.ssh_config_included else "[yellow]not yet added[/yellow]",
    )
    grid.add_row(
        "Colab accounts",
        f"{report.accounts_count} (primary: {report.primary_account or 'unset'})",
    )
    console.print(
        Panel(
            grid,
            title="colabctl doctor",
            border_style="green" if report.ok else "yellow",
            box=box.ROUNDED,
        )
    )
    if report.issues:
        for issue in report.issues:
            console.print(f"  [yellow]•[/yellow] {issue}")


@app.command(name="ls")
def list_sessions(
    live: Annotated[
        bool, typer.Option("--live", help="Refresh live Compute Unit balances from Google.")
    ] = False,
    probe_guard: Annotated[
        bool, typer.Option("--probe-guard", help="Query live VM watchdog countdowns via exec.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Show all accounts, Compute Units, managed GPU sessions, and orphan alerts."""
    try:
        overview = _controller().list_overview(live=live, probe_guard=probe_guard)
    except (ColabctlError, Exception) as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(overview.model_dump_json(indent=2))
        return
    _render_overview(overview)


@app.command()
def up(
    name: Annotated[str, typer.Argument(help="Session name (SSH alias becomes colab-<name>).")] = "dev",
    gpu: Annotated[
        str,
        typer.Option("--gpu", "-g", help=f"GPU type: {', '.join(VALID_GPUS)}."),
    ] = "t4",
    high_mem: Annotated[
        bool, typer.Option("--high-mem", help="Request High-RAM host machine shape.")
    ] = False,
    account: Annotated[
        str | None, typer.Option("--account", "-a", help="Pin a specific saved account alias.")
    ] = None,
    idle_min: Annotated[
        int, typer.Option("--idle-min", help="Auto-stop after N idle minutes (0 disables idle guard).")
    ] = 30,
    max_hours: Annotated[
        float, typer.Option("--max-hours", help="Hard max runtime in hours (0 disables hard limit).")
    ] = 4.0,
    no_guard: Annotated[
        bool, typer.Option("--no-guard", help="Do not start the VM-side cost-guard watchdog.")
    ] = False,
    identity: Annotated[
        str | None, typer.Option("-i", "--identity", help="Path to Ed25519/ECDSA SSH key.")
    ] = None,
    timeout: Annotated[
        int, typer.Option("--timeout", help="Per-attempt Colab assign HTTP read timeout (seconds).")
    ] = 120,
    retries: Annotated[
        int, typer.Option("--retries", help="Number of retries on transient 503/timeout.")
    ] = 2,
    connect: Annotated[
        bool, typer.Option("--connect", "-c", help="Immediately open an interactive SSH shell after ready.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Provision a Colab GPU VM, enable VM cost guard, and configure multiplexed SSH."""
    ctrl = _controller()
    eff_high_mem = normalize_high_mem(gpu, high_mem)
    if not as_json:
        if high_mem and not eff_high_mem:
            err_console.print(
                f"[yellow]Note: {gpu.upper()} only offers a single fixed host shape on Colab; ignoring --high-mem.[/yellow]"
            )
        err_console.print(
            f"[cyan]Provisioning '{name}' (gpu={gpu.upper()}, high_mem={eff_high_mem}, account={account or 'auto'})...[/cyan]"
        )
    try:
        res = ctrl.up(
            name,
            gpu=gpu,
            high_mem=eff_high_mem,
            account=account,
            idle_minutes=idle_min,
            max_hours=max_hours,
            enable_guard=not no_guard,
            identity_file=identity,
            assign_timeout_s=timeout,
            assign_retries=retries,
        )
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return

    if as_json:
        typer.echo(res.model_dump_json(indent=2))
    else:
        s = res.session
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold")
        grid.add_column()
        grid.add_row("Session", s.name)
        grid.add_row("Account", s.account)
        grid.add_row("Endpoint", s.endpoint or "-")
        if s.hardware and s.hardware.gpu_name:
            mem = (
                f" ({s.hardware.gpu_memory_mib} MiB)"
                if s.hardware.gpu_memory_mib
                else ""
            )
            grid.add_row("GPU", f"{s.hardware.gpu_name}{mem} | Driver {s.hardware.driver_version or '?'}")
            grid.add_row("Host RAM / CPU", f"{s.hardware.ram_total or '?'} / {s.hardware.cpu_cores or '?'} cores")
        grid.add_row("Allocated in", f"{res.allocate_seconds:.1f}s")
        mux_note = " [green](mux pre-warmed)[/green]" if s.ssh_mux_active else ""
        grid.add_row("SSH command", f"[bold green]{res.ssh_command}[/bold green]{mux_note}  (or: colabctl ssh {s.name})")
        grid.add_row("Port forward", f"colabctl tunnel {s.name} 8188")
        if no_guard:
            grid.add_row("Cost guard", "[yellow]disabled (--no-guard)[/yellow]")
        elif res.watchdog_deployed:
            grid.add_row("Cost guard", f"[green]active[/green] ({_fmt_guard_summary(s)})")
        else:
            grid.add_row("Cost guard", f"[red]FAILED: {res.watchdog_error}[/red]")
        console.print(
            Panel(grid, title="Colab GPU Ready", border_style="green", box=box.ROUNDED)
        )

    if connect and not as_json:
        argv = ctrl.ssh.build_interactive_ssh_argv(res.session.ssh_alias)
        raise typer.Exit(code=subprocess.run(argv).returncode)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def ssh(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Session name.")],
) -> None:
    """Open an interactive SSH shell (landing in /content) over the multiplexed connection."""
    ctrl = _controller()
    try:
        meta = ctrl.resolve_ssh_target(name)
    except ColabctlError as exc:
        _fail(exc)
        return
    extra = list(ctx.args)
    if extra and extra[0] == "--":
        extra = extra[1:]
    argv = ctrl.ssh.build_interactive_ssh_argv(meta.ssh_alias, remote_command=extra or None)
    raise typer.Exit(code=subprocess.run(argv).returncode)


@app.command()
def tunnel(
    name: Annotated[str, typer.Argument(help="Session name.")],
    remote_port: Annotated[int, typer.Argument(help="Port inside the Colab VM (e.g. 8188).")],
    local_port: Annotated[
        int | None, typer.Option("--local-port", "-L", help="Local port (defaults to remote_port).")
    ] = None,
) -> None:
    """Forward a remote VM port to 127.0.0.1 over the shared ControlMaster SSH channel."""
    ctrl = _controller()
    try:
        meta = ctrl.resolve_ssh_target(name)
    except ColabctlError as exc:
        _fail(exc)
        return
    lp = local_port or remote_port
    console.print(
        f"[green]Forwarding[/green] http://127.0.0.1:{lp} -> {meta.ssh_alias}:127.0.0.1:{remote_port} (Ctrl-C to stop)"
    )
    argv = ctrl.ssh.build_tunnel_argv(meta.ssh_alias, remote_port, lp)
    raise typer.Exit(code=subprocess.run(argv).returncode)


@app.command()
def status(
    name: Annotated[str, typer.Argument(help="Session name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Show detailed status of one session including live VM cost-guard countdown."""
    try:
        view = _controller().status(name)
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(view.model_dump_json(indent=2))
        return

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("Name", view.name)
    grid.add_row("Account", view.account)
    grid.add_row("Endpoint", view.endpoint or "-")
    grid.add_row("SSH Alias", f"ssh {view.ssh_alias}")
    grid.add_row("SSH Mux", "[green]active[/green]" if view.ssh_mux_active else "[dim]idle[/dim]")
    if view.hardware:
        hw = view.hardware
        if hw.gpu_name:
            grid.add_row("GPU", f"{hw.gpu_name} ({hw.gpu_memory_mib or '?'} MiB)")
        grid.add_row("RAM / CPU", f"{hw.ram_total or '?'} / {hw.cpu_cores or '?'} cores")
    console.print(Panel(grid, title=f"Session: {name}", border_style="green", box=box.ROUNDED))
    if view.watchdog_live:
        _render_watchdog(name, view.watchdog_live)


@app.command()
def extend(
    name: Annotated[str, typer.Argument(help="Session name.")],
    hours: Annotated[float, typer.Option("--hours", "-H", help="Hours to add to hard deadline.")] = 2.0,
    idle_min: Annotated[
        int | None, typer.Option("--idle-min", help="Optionally update idle timeout (minutes).")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Extend a session's VM cost-guard hard deadline (and refresh idle timer)."""
    try:
        wd = _controller().extend(name, add_hours=hours, idle_minutes=idle_min)
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(wd.model_dump_json(indent=2))
        return
    _render_watchdog(name, wd)


@app.command()
def guard(
    name: Annotated[str, typer.Argument(help="Session name.")],
    idle_min: Annotated[
        int | None, typer.Option("--idle-min", help="Set idle auto-stop minutes (0 disables).")
    ] = None,
    max_hours: Annotated[
        float | None, typer.Option("--max-hours", help="Set hard limit hours from now (0 disables).")
    ] = None,
    off: Annotated[bool, typer.Option("--off", help="Disable VM cost guard on this session.")] = False,
    on: Annotated[bool, typer.Option("--on", help="Re-enable VM cost guard on this session.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Inspect or reconfigure the VM-side cost-guard watchdog."""
    try:
        wd = _controller().configure_guard(
            name,
            idle_minutes=idle_min,
            max_hours=max_hours,
            disable=off,
            enable=on,
        )
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(wd.model_dump_json(indent=2))
        return
    _render_watchdog(name, wd)


@app.command()
def stop(
    name: Annotated[str | None, typer.Argument(help="Session name to stop.")] = None,
    all_sessions: Annotated[
        bool, typer.Option("--all", help="Stop EVERY session and orphan VM across all accounts.")
    ] = False,
    forget: Annotated[
        bool, typer.Option("--forget", help="Only remove local registration without contacting Colab.")
    ] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation for --all.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Terminate one session (or all sessions with --all) and stop billing."""
    ctrl = _controller()
    if all_sessions:
        if not yes and not as_json:
            typer.confirm(
                "Stop ALL Colab VMs across every saved account? Unsaved /content data will be lost.",
                abort=True,
            )
        try:
            results = ctrl.stop_all()
        except ColabctlError as exc:
            _fail(exc, as_json=as_json)
            return
        if as_json:
            typer.echo(json.dumps([r.model_dump(mode="json") for r in results], indent=2))
        else:
            console.print("[green]All Colab sessions and orphan VMs stopped across all accounts.[/green]")
        return

    if not name:
        _fail(ColabctlError("Specify a session NAME or pass --all."), as_json=as_json)
        return

    try:
        res = ctrl.stop(name, forget=forget)
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(res.model_dump_json(indent=2))
    else:
        console.print(f"[green]✓[/green] {res.message}")


@app.command()
def switch(
    name: Annotated[str, typer.Argument(help="Session name to replace.")],
    gpu: Annotated[str, typer.Option("--gpu", "-g", help=f"New GPU: {', '.join(VALID_GPUS)}.")],
    high_mem: Annotated[bool, typer.Option("--high-mem", help="Request High-RAM shape.")] = False,
    account: Annotated[str | None, typer.Option("--account", "-a", help="Optional target account.")] = None,
    idle_min: Annotated[int | None, typer.Option("--idle-min", help="Idle auto-stop minutes.")] = None,
    max_hours: Annotated[float | None, typer.Option("--max-hours", help="Hard limit hours.")] = None,
    no_guard: Annotated[bool, typer.Option("--no-guard", help="Disable VM cost guard.")] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation prompt.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Stop session NAME and re-provision it with a new GPU under the same SSH alias."""
    eff_high_mem = normalize_high_mem(gpu, high_mem)
    if not as_json and high_mem and not eff_high_mem:
        err_console.print(
            f"[yellow]Note: {gpu.upper()} only offers a single fixed host shape on Colab; ignoring --high-mem.[/yellow]"
        )
    if not yes and not as_json:
        typer.confirm(
            f"Switch '{name}' to GPU={gpu.upper()}? The old VM will be stopped and unsaved /content files lost.",
            abort=True,
        )
    try:
        res = _controller().switch(
            name,
            gpu=gpu,
            high_mem=eff_high_mem,
            account=account,
            idle_minutes=idle_min,
            max_hours=max_hours,
            enable_guard=not no_guard,
        )
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(res.model_dump_json(indent=2))
    else:
        console.print(
            f"[green]✓[/green] Switched '{name}' to {gpu.upper()} on {res.session.account}. Connect: [bold]{res.ssh_command}[/bold]"
        )


@app.command(name="reset-ssh")
def reset_ssh(
    name: Annotated[str, typer.Argument(help="Session name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Recover from stale SSH / HTTP 429 by clearing local mux & orphaned remote sshd sessions."""
    try:
        result = _controller().reset_ssh(name)
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(json.dumps(result, indent=2))
    else:
        killed = result.get("remote_sessions_terminated", [])
        console.print(
            f"[green]✓[/green] SSH reset for '{name}': local_mux_closed={result['local_mux_closed']}, remote_sshd_cleared={len(killed)}"
        )


@app.command()
def reap(
    account: Annotated[str | None, typer.Option("--account", "-a", help="Account owning the orphan.")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint", "-e", help="Orphan VM endpoint ID.")] = None,
    all_orphans: Annotated[bool, typer.Option("--all-orphans", help="Stop every detected orphan VM.")] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Stop unmanaged orphan VMs that are still billing compute units."""
    ctrl = _controller()
    if all_orphans:
        if not yes and not as_json:
            typer.confirm("Stop ALL orphan VMs across all saved accounts?", abort=True)
        try:
            reaped = ctrl.reap_all_orphans()
        except ColabctlError as exc:
            _fail(exc, as_json=as_json)
            return
        if as_json:
            typer.echo(json.dumps([o.model_dump(mode="json") for o in reaped], indent=2))
        else:
            console.print(f"[green]✓[/green] Reaped {len(reaped)} orphan VM(s).")
        return

    if not account or not endpoint:
        _fail(
            ColabctlError("Pass --account AND --endpoint, or pass --all-orphans."),
            as_json=as_json,
        )
        return
    try:
        ctrl.reap_orphan(account, endpoint)
    except ColabctlError as exc:
        _fail(exc, as_json=as_json)
        return
    if as_json:
        typer.echo(json.dumps({"ok": True, "account": account, "endpoint": endpoint}))
    else:
        console.print(f"[green]✓[/green] Reaped orphan {endpoint} on {account}.")


@app.command()
def primary(
    account: Annotated[str, typer.Argument(help="Account alias to set as primary.")],
    threshold: Annotated[
        float | None,
        typer.Option("--threshold", help="Auto-switch primary when balance drops below this CU."),
    ] = None,
) -> None:
    """Set the primary account used for new GPU sessions."""
    try:
        _controller().set_primary(account, threshold=threshold)
    except ColabctlError as exc:
        _fail(exc)
        return
    console.print(f"[green]✓[/green] Primary account set to '{account}'.")


@app.command(name="mount-drive")
def mount_drive(
    name: Annotated[str, typer.Argument(help="Session name.")],
    path: Annotated[str, typer.Argument(help="Mount point inside VM.")] = "/content/drive",
) -> None:
    """Mount Google Drive inside the Colab VM (interactive OAuth flow)."""
    ctrl = _controller()
    rc = ctrl.pool.drivemount(name, path)
    raise typer.Exit(code=rc)


@app.command()
def ui(
    port: Annotated[
        int, typer.Option("--port", "-p", help="Preferred loopback port (falls back if busy).")
    ] = 18420,
    app_window: Annotated[
        bool,
        typer.Option(
            "--app/--browser",
            help="Launch in standalone Chromium --app window (default) or normal browser tab.",
        ),
    ] = True,
    no_open: Annotated[
        bool, typer.Option("--no-open", help="Start the local server without opening a window.")
    ] = False,
    demo: Annotated[
        bool,
        typer.Option(
            "--demo",
            help="Run with safe in-memory mock data (0 Compute Units spent; no cloud calls).",
        ),
    ] = False,
    lang: Annotated[
        str,
        typer.Option(
            "--lang",
            help="Initial UI language: auto (browser/saved), zh, or en.",
        ),
    ] = "auto",
) -> None:
    """Launch the local Chromium App / Web management dashboard."""
    import secrets
    import socket
    import threading
    import time

    import uvicorn

    from colabctl.web.demo import DemoColabController
    from colabctl.web.launcher import launch_ui_window, pick_free_port
    from colabctl.web.server import create_app

    lang_norm = lang.strip().lower()
    if lang_norm in ("zh", "zh-cn", "zh_cn"):
        ui_lang = "zh-CN"
    elif lang_norm in ("en", "en-us", "en_us"):
        ui_lang = "en"
    elif lang_norm == "auto":
        ui_lang = "auto"
    else:
        _fail(ColabctlError(f"Unsupported --lang {lang!r}. Use: auto, zh, or en."))
        return

    chosen_port = pick_free_port(port)
    token = secrets.token_urlsafe(24)
    ctrl = DemoColabController() if demo else _controller()
    web_app = create_app(ctrl, auth_token=token, demo_mode=demo, default_lang=ui_lang)
    url = f"http://127.0.0.1:{chosen_port}/?token={token}"
    open_mode = "none" if no_open else ("app" if app_window else "browser")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("Bind", f"127.0.0.1:{chosen_port} (loopback only + session token)")
    grid.add_row(
        "Window",
        "Headless (--no-open)"
        if no_open
        else ("Chromium App (--app)" if app_window else "System Browser"),
    )
    if demo:
        grid.add_row("Mode", "[yellow]DEMO MODE (in-memory mock data, 0 CU spent)[/yellow]")
    grid.add_row("Stop", "Press Ctrl-C to stop server & close managed tunnels")
    console.print(
        Panel(
            grid,
            title=f"colabctl Dashboard v{__version__}",
            border_style="yellow" if demo else "cyan",
            box=box.ROUNDED,
        )
    )
    console.print(f"Dashboard URL: [bold cyan]{url}[/bold cyan]", soft_wrap=True)

    if open_mode != "none":
        def _open_when_ready() -> None:
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", chosen_port), timeout=0.25):
                        break
                except OSError:
                    time.sleep(0.1)
            try:
                launched, exe = launch_ui_window(
                    url,
                    mode=open_mode,
                    paths=getattr(ctrl, "paths", None),
                )
                if launched == "chromium-app" and exe:
                    err_console.print(f"[dim]Opened standalone Chromium window ({exe})[/dim]")
                elif launched == "browser":
                    err_console.print("[dim]Opened dashboard in default browser.[/dim]")
            except Exception as exc:
                err_console.print(f"[yellow]Could not auto-open window: {exc}[/yellow]")

        threading.Thread(target=_open_when_ready, name="colabctl-ui-opener", daemon=True).start()

    try:
        uvicorn.run(
            web_app,
            host="127.0.0.1",
            port=chosen_port,
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        pass


@app.command(name="_proxy", hidden=True)
def internal_proxy(
    name: Annotated[str, typer.Argument(help="Session name.")],
) -> None:
    """Internal OpenSSH ProxyCommand bridge (never auto-creates VMs)."""
    try:
        _controller().exec_proxy(name)
    except ColabctlError as exc:
        sys.stderr.write(f"[colabctl] {exc}\n")
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
