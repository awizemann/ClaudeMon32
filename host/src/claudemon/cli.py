"""claudemon CLI entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import logging.handlers
import sys
import webbrowser

from . import (
    cloudflare,
    collect,
    config as configmod,
    daemon,
    github,
    keychain,
    launchd,
    oauth,
    paddle,
    render,
    sources,
    usage,
)
from .collect import _collect_snapshots
from .models import utcnow
from .serial_link import DeviceLink

log = logging.getLogger("claudemon")


def _setup_logging(to_file: bool) -> None:
    """Interactive commands (and `run --foreground`) log to stderr; the
    launchd-managed daemon logs to a rotating file. The plist's stdout/stderr
    capture only crash output (claudemon.out), so nothing is double-logged."""
    if to_file:
        launchd.LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            launchd.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
        )
    else:
        handler = logging.StreamHandler()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
    )


# ---------------------------------------------------------------- commands


def _find_duplicate_org(new_label: str, org_id: str | None) -> str | None:
    """Return the label of an existing account with the same organization id."""
    if not org_id:
        return None
    for label in keychain.list_accounts():
        if label == new_label:
            continue
        try:
            existing = keychain.load_account(label)
        except keychain.KeychainError:
            continue
        if existing.organization_id == org_id:
            return label
    return None


def cmd_login(args: argparse.Namespace) -> int:
    label = args.label
    verifier, challenge = oauth.make_pkce()
    state = oauth.new_state()
    url = oauth.build_authorize_url(challenge, state)

    print(f"Logging in account '{label}'.")
    print("A browser window will open. Sign in to the Claude account you want")
    print("to monitor, then copy the code the page shows (format: code#state).\n")
    if keychain.list_accounts():
        print("NOTE: your browser will silently reuse the claude.ai account it is")
        print("already signed in to. To add a DIFFERENT account, copy the URL below")
        print("into a private/incognito window instead.\n")
    print(f"If the browser doesn't open, visit:\n  {url}\n")
    webbrowser.open(url)

    pasted = input("Paste code here: ").strip()
    if not pasted:
        print("No code entered; aborting.", file=sys.stderr)
        return 1
    try:
        creds = oauth.exchange_code(pasted, verifier, state)
    except oauth.OAuthError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1

    creds.organization_id = usage.fetch_org_id(creds)
    duplicate = _find_duplicate_org(label, creds.organization_id)
    if duplicate:
        print(
            f"\nWARNING: this grant belongs to the same Claude account as "
            f"'{duplicate}' — the browser probably reused its signed-in session.\n"
            f"Storing it anyway as '{label}'. If that wasn't the intent, run\n"
            f"`claudemon logout {label}` and retry from a private window.",
            file=sys.stderr,
        )

    keychain.save_account(label, creds)
    sub = f" ({creds.subscription_type})" if creds.subscription_type else ""
    print(f"Stored credentials for '{label}'{sub} in the Keychain (service 'claudemon').")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    keychain.delete_account(args.label)
    print(f"Removed stored credentials for '{args.label}'.")
    return 0


def cmd_accounts(_args: argparse.Namespace) -> int:
    labels = keychain.list_accounts()
    if not labels:
        print("No accounts configured. Run: claudemon login <label>")
        return 0
    for label in labels:
        print(label)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if args.cached:
        state = daemon.read_state()
        if not state:
            print("No cached state yet (is the daemon running?).", file=sys.stderr)
            return 1
        print(f"(cached at {state.get('written_at')})")
        print(json.dumps(state.get("accounts"), indent=2))
        return 0

    snapshots = _collect_snapshots()
    if not snapshots:
        print("No accounts configured. Run: claudemon login <label>")
        return 1
    print(render.status_table(snapshots, utcnow()))
    agent = "running" if launchd.is_running() else "not installed/running"
    print(f"\nlaunchd agent: {agent}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    labels = [args.label] if args.label else keychain.list_accounts()
    if not labels:
        print("No accounts configured. Run: claudemon login <label>", file=sys.stderr)
        return 1
    for label in labels:
        try:
            creds = oauth.load_fresh(label)
            status_code, headers, body = usage.probe(creds)
        except (keychain.KeychainError, oauth.OAuthError, oauth.OAuthTransientError) as e:
            print(f"== {label}: {e}", file=sys.stderr)
            continue
        print(f"== {label}: HTTP {status_code}")
        for key in sorted(headers):
            if key.lower().startswith(("anthropic", "content-type", "request-id")):
                print(f"   {key}: {headers[key]}")
        try:
            print(json.dumps(json.loads(body), indent=2))
        except json.JSONDecodeError:
            print(body[:2000])
    return 0


def cmd_push_once(_args: argparse.Namespace) -> int:
    snapshots = _collect_snapshots()
    if not snapshots:
        print("No accounts configured.", file=sys.stderr)
        return 1
    print(render.status_table(snapshots, utcnow()))
    link = DeviceLink()
    if not link.connect():
        print("\nNo device found (checked /dev/cu.usbmodem*, usbserial*, SLAB*).", file=sys.stderr)
        return 1
    payload = render.to_device_payload(snapshots, utcnow())
    resp = link.send_command(payload)
    link.close()
    if resp and resp.get("status") == "ok":
        print(f"\nPushed to device on {link.port or 'serial port'}.")
        return 0
    print(f"\nDevice rejected push: {resp}", file=sys.stderr)
    return 1


# ---------------------------------------------------------- dashboard sources


def _collect_dashboard() -> tuple[list, list, list, list]:
    """One-shot fetch of all four dashboard sections via the shared collector.
    A fresh collector per call means discovery isn't cached across CLI
    invocations (the daemon keeps a long-lived collector so its poll loop does
    cache; see collect.DashboardCollector)."""
    return collect.DashboardCollector().collect()


def cmd_set_token(args: argparse.Namespace) -> int:
    token = getpass.getpass(f"Paste the {args.service} token (input hidden): ").strip()
    if not token:
        print("No token entered; aborting.", file=sys.stderr)
        return 1
    keychain.save_secret(args.service, token)
    print(f"Stored the {args.service} token in the Keychain (service 'claudemon').")
    return 0


def cmd_add_zone(args: argparse.Namespace) -> int:
    sources.add_zone(args.zone_id, args.name)
    print(f"Watching Cloudflare zone {args.name or args.zone_id} ({args.zone_id}).")
    return 0


def cmd_add_repo(args: argparse.Namespace) -> int:
    try:
        sources.add_repo(args.repo)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Watching GitHub repo {args.repo}.")
    return 0


def cmd_add_product(args: argparse.Namespace) -> int:
    try:
        sources.add_product(args.name)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Watching Paddle product {args.name}.")
    return 0


def cmd_sources(_args: argparse.Namespace) -> int:
    srcs = sources.load()
    cf_token = "set" if keychain.load_secret("cloudflare") else "MISSING"
    gh_token = "set" if keychain.load_secret("github") else "none (public REST)"
    pd_token = "set" if keychain.load_secret("paddle") else "none (demo data)"
    print(f"Cloudflare token: {cf_token}")
    for z in srcs.cloudflare_zones:
        print(f"  zone {z.name} ({z.id})")
    print(f"Paddle token: {pd_token}")
    for p in srcs.paddle_products:
        print(f"  product {p}")
    print(f"GitHub token: {gh_token}")
    for r in srcs.github_repos:
        print(f"  repo {r}")
    if srcs.empty:
        print(
            "\nNo extra sources yet. Add with `add-zone <id> [name]` / "
            "`add-repo <owner/repo>` / `add-product <name>`."
        )
    return 0


def cmd_zones(_args: argparse.Namespace) -> int:
    """List the Cloudflare zones the token discovers, marking which are shown."""
    token = keychain.load_secret("cloudflare")
    if not token:
        print("No Cloudflare token set. Run: claudemon set-token cloudflare", file=sys.stderr)
        return 1
    discovered = cloudflare.list_zones(token)
    if not discovered:
        print("No zones discovered (token may lack Zone:Read, or none exist).")
        return 0
    cfg = configmod.load()
    ids = [z["id"] for z in discovered]
    shown = set(configmod.resolve_shown(ids, cfg.cloudflare_shown, render.MAX_COCKPIT_ZONES))
    mode = "all" if cfg.cloudflare_shown is None else "selected"
    print(f"Cloudflare zones ({len(discovered)} discovered, showing: {mode}):")
    for z in discovered:
        mark = "*" if z["id"] in shown else " "
        print(f"  [{mark}] {z['name']} ({z['id']})")
    return 0


def cmd_repos(_args: argparse.Namespace) -> int:
    """List the GitHub repos the token discovers, marking which are shown."""
    token = keychain.load_secret("github")
    if not token:
        print("No GitHub token set. Run: claudemon set-token github", file=sys.stderr)
        return 1
    discovered = github.list_repos(token)
    if not discovered:
        print("No repos discovered (token may lack repo scope, or none exist).")
        return 0
    cfg = configmod.load()
    shown = set(configmod.resolve_shown(discovered, cfg.github_shown, render.MAX_COCKPIT_REPOS))
    mode = "all" if cfg.github_shown is None else "selected"
    print(f"GitHub repos ({len(discovered)} discovered, showing: {mode}):")
    for repo in discovered:
        mark = "*" if repo in shown else " "
        print(f"  [{mark}] {repo}")
    return 0


def cmd_products(_args: argparse.Namespace) -> int:
    """List the Paddle products the token discovers, marking which are shown."""
    token = keychain.load_secret("paddle")
    if not token:
        print("No Paddle token set. Run: claudemon set-token paddle", file=sys.stderr)
        return 1
    discovered = paddle.list_products(token)
    if not discovered:
        print("No products discovered (token may be rejected, or none exist).")
        return 0
    cfg = configmod.load()
    shown = set(
        configmod.resolve_shown(discovered, cfg.paddle_shown, render.MAX_COCKPIT_PRODUCTS)
    )
    mode = "all" if cfg.paddle_shown is None else "selected"
    print(f"Paddle products ({len(discovered)} discovered, showing: {mode}):")
    for name in discovered:
        mark = "*" if name in shown else " "
        print(f"  [{mark}] {name}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    claude, cf, pd, gh = _collect_dashboard()
    now = utcnow()
    print(render.status_table(claude, now))
    if cf:
        print("\nCLOUDFLARE")
        for z in cf:
            print(
                f"  {z.name:<16} req {render.fmt_count(z.requests) or '--':>6}  "
                f"cache {z.cache_pct if z.cache_pct is not None else '--'}%  "
                f"visitors {render.fmt_count(z.unique_visitors) or '--':>6}  "
                f"threats {render.fmt_count(z.threats) or '--':>5}  [{z.state.value}]"
            )
    if pd:
        print("\nPADDLE")
        for p in pd:
            print(
                f"  {p.name:<16} buys {render.fmt_count(p.purchases) or '--':>6}  "
                f"custs {render.fmt_count(p.customers) or '--':>6}  "
                f"rev/mo {render.fmt_money(p.revenue_month) or '--':>8}  [{p.state.value}]"
            )
    if gh:
        print("\nGITHUB")
        for r in gh:
            print(
                f"  {r.name:<22} ★{render.fmt_count(r.stars) or '--':>5}  "
                f"forks {render.fmt_count(r.forks) or '--':>5}  "
                f"issues {render.fmt_count(r.open_issues) or '--':>4}  "
                f"PRs {render.fmt_count(r.open_prs) or '--':>4}  [{r.state.value}]"
            )
    if args.legacy:
        # Pre-Cockpit firmware (set_dashboard). The current CrowPanel firmware
        # speaks set_cockpit only, so this is just an escape hatch for old images.
        if args.push:
            return _push_payload(render.to_dashboard_payload(claude, cf, gh, now), args.port)
        return 0
    totals = paddle.combine_totals(pd)
    settings = configmod.load().settings
    payload = render.to_cockpit_payload(
        claude, cf, pd, totals, gh, now,
        usage_threshold=settings.usage_threshold,
        alert_on_down=settings.alert_down,
        alert_on_4xx=settings.alert_4xx,
    )
    print(f"\n[cockpit payload: {len(json.dumps(payload))} bytes]")
    if args.push:
        return _push_payload(payload, args.port)
    return 0


def _push_payload(payload: dict, port: str | None = None) -> int:
    link = DeviceLink(port)
    if not link.connect():
        print("\nNo device found (checked usbmodem*, usbserial*, wchusbserial*, SLAB*).", file=sys.stderr)
        return 1
    resp = link.send_command(payload)
    port = link.port
    link.close()
    if resp and resp.get("status") == "ok":
        print(f"\nPushed to device on {port or 'serial port'}.")
        return 0
    print(f"\nDevice rejected push: {resp}", file=sys.stderr)
    return 1


def cmd_run(_args: argparse.Namespace) -> int:
    daemon.run_loop()
    return 0


def cmd_install_agent(_args: argparse.Namespace) -> int:
    path = launchd.install()
    print(f"Installed and started LaunchAgent: {path}")
    print(f"Logs: {launchd.LOG_FILE}")
    return 0


def cmd_uninstall_agent(_args: argparse.Namespace) -> int:
    launchd.uninstall()
    print("LaunchAgent removed.")
    return 0


# ---------------------------------------------------------------- parser


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claudemon",
        description="Monitor Claude subscription usage limits (5-hour and weekly) "
        "for multiple accounts, on an ESP32 e-paper desk display.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="OAuth login for an account (opens browser)")
    p.add_argument("label", help="short name for this account, e.g. personal, work")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("logout", help="remove an account's stored credentials")
    p.add_argument("label")
    p.set_defaults(func=cmd_logout)

    p = sub.add_parser("accounts", help="list configured accounts")
    p.set_defaults(func=cmd_accounts)

    p = sub.add_parser("status", help="fetch and print usage for all accounts")
    p.add_argument("--cached", action="store_true", help="print the daemon's last snapshot")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("probe", help="dump the raw usage endpoint response (schema check)")
    p.add_argument("label", nargs="?", help="account label (default: all)")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("push-once", help="fetch usage once and push it to the device")
    p.set_defaults(func=cmd_push_once)

    p = sub.add_parser("set-token", help="store a Cloudflare/GitHub/Paddle API token in the Keychain")
    p.add_argument("service", choices=["cloudflare", "github", "paddle"])
    p.set_defaults(func=cmd_set_token)

    p = sub.add_parser("add-zone", help="watch a Cloudflare zone (analytics)")
    p.add_argument("zone_id", help="Cloudflare zone tag/ID")
    p.add_argument("name", nargs="?", help="display name (default: the zone id)")
    p.set_defaults(func=cmd_add_zone)

    p = sub.add_parser("add-repo", help="watch a GitHub repo (owner/repo)")
    p.add_argument("repo")
    p.set_defaults(func=cmd_add_repo)

    p = sub.add_parser("add-product", help="watch a Paddle product (by display name)")
    p.add_argument("name", help="product display name, e.g. PixelPeek")
    p.set_defaults(func=cmd_add_product)

    p = sub.add_parser("sources", help="list configured dashboard sources + token status")
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("zones", help="list Cloudflare zones the token discovers (* = shown)")
    p.set_defaults(func=cmd_zones)

    p = sub.add_parser("repos", help="list GitHub repos the token discovers (* = shown)")
    p.set_defaults(func=cmd_repos)

    p = sub.add_parser("products", help="list Paddle products the token discovers (* = shown)")
    p.set_defaults(func=cmd_products)

    p = sub.add_parser("dashboard", help="fetch Claude + Cloudflare + Paddle + GitHub and print (--push to send)")
    p.add_argument("--push", action="store_true", help="also push the payload to the panel")
    p.add_argument(
        "--legacy",
        action="store_true",
        help="build the older set_dashboard payload (for pre-Cockpit firmware) "
        "instead of the default set_cockpit",
    )
    p.add_argument(
        "--port",
        help="serial port to push to (e.g. /dev/cu.wchusbserial20130); "
        "pins the CrowPanel when the e-paper board is also connected. Default: auto-detect.",
    )
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("run", help="poll/push loop (used by the launchd agent)")
    p.add_argument("--foreground", action="store_true", help="log to stderr instead of the log file")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("install-agent", help="install + start the launchd background agent")
    p.set_defaults(func=cmd_install_agent)

    p = sub.add_parser("uninstall-agent", help="stop + remove the launchd agent")
    p.set_defaults(func=cmd_uninstall_agent)

    args = parser.parse_args()
    _setup_logging(to_file=args.command == "run" and not getattr(args, "foreground", False))
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
