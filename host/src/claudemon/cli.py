"""claudemon CLI entry point."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import sys
import webbrowser

from . import daemon, keychain, launchd, oauth, render, usage
from .models import AccountState, AccountUsage, utcnow
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


def _collect_snapshots() -> list[AccountUsage]:
    snapshots: list[AccountUsage] = []
    for label in keychain.list_accounts():
        snap = AccountUsage(label=label)
        try:
            creds = oauth.load_fresh(label)
            snap = usage.fetch_usage(label, creds)
        except (keychain.KeychainError, oauth.OAuthError) as e:
            log.warning("%s: %s", label, e)
            snap.state = AccountState.AUTH
        except (oauth.OAuthTransientError, usage.UsageFetchError) as e:
            log.warning("%s: %s", label, e)
            snap.state = AccountState.ERROR
        snapshots.append(snap)
    return snapshots


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
