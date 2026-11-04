#!/usr/bin/env python3
"""
hirschmann_ssh_runner.py  -  v1.0

Log in over SSH to a list of Hirschmann HiOS switches, enter privileged
mode with 'enable' (no enable password), run a list of CLI commands and
save the output of every device to its own log file.

    devices file  : one switch per line  ->  IP / hostname, optional ":port"
    commands file : one CLI command per line
    username/pass : asked interactively when the script starts
                    (password is read with getpass, never echoed or logged)

Typical HiOS session this script automates:

    (Hirschmann GRS1042) >enable
    (Hirschmann GRS1042) #cli numlines 0      <- disable paging (optional)
    (Hirschmann GRS1042) #show system info
    ...
    (Hirschmann GRS1042) #logout

Security notes (IEC 62443 mindset - secure by default):
  * SSH host keys are VERIFIED against a known_hosts file. Unknown keys are
    rejected unless you explicitly pass --accept-new-hostkeys (trust on first
    use; the new key is then saved so later runs are verified).
  * Credentials live only in memory and are never written to the logs.
  * No SSH agent / local key files are offered to the switch.

Requires: Python 3.8+, paramiko  (pip install paramiko)
Reference: paramiko documentation, https://docs.paramiko.org
"""

import argparse
import getpass
import os
import re
import sys
import time
from datetime import datetime

try:
    import paramiko
except ImportError:
    sys.exit("paramiko is not installed. Install it with:  pip install paramiko")

VERSION = "1.0"

# Prompt at the end of the buffer: "...>" (user mode) or "...#" (privileged).
# HiOS example: "(Hirschmann GRS1042) >"  /  "(Hirschmann GRS1042) #"
PROMPT_RE = re.compile(r"[>#]\s*$")
PRIV_PROMPT_RE = re.compile(r"#\s*$")

# Paging prompts - if paging is still active we press SPACE to continue.
MORE_RE = re.compile(r"--More--|Press any key|\(q\)uit", re.IGNORECASE)

# Same, for removing the leftover paging prompt text from the saved log.
MORE_PROMPT_LINE_RE = re.compile(r"--More--( or \(q\)uit)?|Press any key[^\r\n]*",
                                 re.IGNORECASE)

# Questions we must NOT answer automatically (e.g. reboot / overwrite).
CONFIRM_RE = re.compile(r"\(y/n\)|\[y/n\]|\(yes/no\)", re.IGNORECASE)

# ANSI escape sequences some CLIs emit (cursor moves, colours).
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
def read_list_file(path):
    """Return non-empty lines of a text file, ignoring '#' comment lines."""
    if not os.path.isfile(path):
        sys.exit(f"ERROR: file not found: {path}")
    items = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
    if not items:
        sys.exit(f"ERROR: no usable lines in {path}")
    return items


def parse_device(entry, default_port):
    """'10.0.0.1' -> ('10.0.0.1', 22);  '10.0.0.1:2222' -> ('10.0.0.1', 2222)."""
    if entry.count(":") == 1:  # host:port (plain IPv6 has several colons)
        host, port = entry.split(":")
        return host.strip(), int(port)
    return entry, default_port


def clean(text):
    """Remove ANSI codes, paging prompts and normalise line endings."""
    text = ANSI_RE.sub("", text)
    text = MORE_PROMPT_LINE_RE.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "")


def read_until_prompt(chan, timeout, prompt_re=PROMPT_RE):
    """
    Read from the interactive shell until the switch shows a prompt.

    * presses SPACE on '--More--' style paging prompts
    * stops (without answering) on y/n confirmation questions
    * raises TimeoutError if no prompt appears within 'timeout' seconds
    Returns the collected text.
    """
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            buf += chan.recv(65535).decode("utf-8", errors="replace")
            deadline = time.time() + timeout  # data is flowing -> extend
            raw_tail = ANSI_RE.sub("", buf)[-200:]
            if MORE_RE.search(raw_tail.splitlines()[-1] if raw_tail.splitlines() else ""):
                chan.send(" ")
                continue
            tail = clean(buf)[-200:]
            if CONFIRM_RE.search(tail):
                raise RuntimeError("switch asked for a y/n confirmation - "
                                   "not answered automatically:\n" + tail)
            if prompt_re.search(tail):
                # short quiet period to be sure the prompt is really the end
                time.sleep(0.2)
                if not chan.recv_ready():
                    return clean(buf)
        elif chan.closed or chan.exit_status_ready():
            raise ConnectionError("SSH channel closed by the switch")
        else:
            time.sleep(0.05)
    raise TimeoutError("no prompt received within %ss. Last output:\n%s"
                       % (timeout, clean(buf)[-300:]))


def send_command(chan, cmd, timeout):
    """Send one CLI command and return its output (including echo + prompt)."""
    chan.send(cmd + "\n")
    return read_until_prompt(chan, timeout)


# --------------------------------------------------------------------------
# Per-device work
# --------------------------------------------------------------------------
def run_device(host, port, username, password, commands, args):
    """Connect to one switch, run all commands, write the log file."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_host = re.sub(r"[^A-Za-z0-9._-]", "_", host)
    port_tag = "" if port == 22 else f"_p{port}"
    log_path = os.path.join(args.output, f"{safe_host}{port_tag}_{stamp}.txt")

    client = paramiko.SSHClient()
    # Host key handling - verify by default
    if os.path.isfile(args.known_hosts):
        client.load_host_keys(args.known_hosts)
    if args.accept_new_hostkeys:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"# Device : {host}:{port}\n# User   : {username}\n"
                  f"# Time   : {stamp}\n# Script : hirschmann_ssh_runner.py v{VERSION}\n\n")
        try:
            # paramiko tries 'password' auth and automatically falls back to
            # 'keyboard-interactive' (often used with RADIUS) if needed.
            client.connect(host, port=port, username=username, password=password,
                           timeout=args.connect_timeout,
                           banner_timeout=args.connect_timeout,
                           auth_timeout=args.connect_timeout,
                           look_for_keys=False, allow_agent=False)
            if args.accept_new_hostkeys:
                # store newly accepted keys so the next run is verified
                os.makedirs(os.path.dirname(os.path.abspath(args.known_hosts)),
                            exist_ok=True)
                client.save_host_keys(args.known_hosts)

            chan = client.invoke_shell(term="vt100", width=511, height=1000)
            chan.settimeout(args.timeout)

            # 1) wait for the login prompt '>'
            log.write(read_until_prompt(chan, args.timeout))

            # 2) privileged mode - 'enable' has no password on these switches
            out = send_command(chan, "enable", args.timeout)
            log.write(out)
            if not PRIV_PROMPT_RE.search(out):
                raise RuntimeError("'enable' did not give a '#' prompt")

            # 3) disable paging (optional; '--More--' is handled anyway)
            if args.paging_cmd:
                log.write(send_command(chan, args.paging_cmd, args.timeout))

            # 4) the user's commands
            for cmd in commands:
                print(f"  [{host}] {cmd}")
                log.write(send_command(chan, cmd, args.timeout))
                log.flush()

            # 5) leave cleanly
            chan.send("logout\n")
            time.sleep(0.5)
            log.write("\n# --- finished OK ---\n")
            return True, log_path

        except paramiko.BadHostKeyException:
            msg = ("HOST KEY MISMATCH - the key differs from known_hosts. "
                   "Possible man-in-the-middle; NOT connecting.")
        except paramiko.AuthenticationException:
            msg = "authentication failed (wrong user/password or RADIUS reject)"
        except paramiko.SSHException as exc:
            if "not found in known_hosts" in str(exc):
                msg = (f"unknown host key ({exc}). Verify the switch fingerprint, "
                       "then rerun with --accept-new-hostkeys.")
            else:
                msg = f"SSH error: {exc}"
        except Exception as exc:  # timeouts, socket errors, enable failure ...
            msg = f"{type(exc).__name__}: {exc}"
        finally:
            client.close()

        log.write(f"\n# --- FAILED: {msg} ---\n")
        return False, msg


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="hirschmann_ssh_runner.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Run CLI commands on Hirschmann HiOS switches over SSH.\n\n"
            "Logs in to every switch in the devices file, runs 'enable'\n"
            "(no password), optionally disables paging, executes every\n"
            "line of the commands file and saves one log per device.\n"
            "Username and password are asked for at start-up."),
        epilog=(
            "FILE FORMATS\n"
            "  devices.txt   one switch per line, optional :port\n"
            "                    10.10.10.11\n"
            "                    grs1042-lab.local:2222\n"
            "  commands.txt  one command per line (run in '#' mode)\n"
            "                    show system info\n"
            "                    show vlan brief\n"
            "  Empty lines and lines starting with '#' are ignored.\n\n"
            "EXAMPLES\n"
            "  First run (switch keys not yet known - check fingerprints!):\n"
            "    python hirschmann_ssh_runner.py -d devices.txt -c commands.txt "
            "--accept-new-hostkeys\n"
            "  Normal run (keys verified):\n"
            "    python hirschmann_ssh_runner.py -d devices.txt -c commands.txt\n"
            "  Without paging command, longer timeout:\n"
            "    python hirschmann_ssh_runner.py -d devices.txt -c commands.txt "
            "--paging-cmd \"\" -t 60\n\n"
            "EXIT CODES\n"
            "  0 all devices OK, 1 at least one device failed, 2 aborted by user\n\n"
            "NOTES\n"
            "  * Commands that ask (y/n) are NOT confirmed automatically; the\n"
            "    device is marked failed so nothing destructive happens silently.\n"
            "  * Config commands work too: put 'configure' ... 'exit' in the\n"
            "    commands file. Remember 'save' if changes must survive reboot."))
    p.add_argument("-d", "--devices", default="devices.txt",
                   help="file with switch IPs/hostnames (default: devices.txt)")
    p.add_argument("-c", "--commands", default="commands.txt",
                   help="file with CLI commands (default: commands.txt)")
    p.add_argument("-o", "--output", default="output",
                   help="folder for per-device logs (default: ./output)")
    p.add_argument("-p", "--port", type=int, default=22,
                   help="default SSH port if not given in devices file (default: 22)")
    p.add_argument("-t", "--timeout", type=float, default=30,
                   help="seconds to wait for a prompt after a command (default: 30)")
    p.add_argument("--connect-timeout", type=float, default=15,
                   help="seconds for TCP/SSH/auth handshake (default: 15)")
    p.add_argument("--paging-cmd", default="cli numlines 0",
                   help="command sent after enable to disable paging; "
                        "use \"\" to skip (default: 'cli numlines 0')")
    p.add_argument("--known-hosts",
                   default=os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts"),
                   help="known_hosts file for host key verification "
                        "(default: ~/.ssh/known_hosts)")
    p.add_argument("--accept-new-hostkeys", action="store_true",
                   help="trust and save UNKNOWN host keys (first run only). "
                        "Changed keys are still rejected.")
    p.add_argument("-u", "--username",
                   help="username (if omitted you are asked at start-up)")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")
    return p


def main():
    args = build_parser().parse_args()

    devices = [parse_device(d, args.port) for d in read_list_file(args.devices)]
    commands = read_list_file(args.commands)
    os.makedirs(args.output, exist_ok=True)

    print(f"{len(devices)} device(s), {len(commands)} command(s)")
    try:
        username = args.username or input("Username: ").strip()
        password = getpass.getpass("Password: ")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return 2
    if not username or not password:
        print("Username and password are required.")
        return 2

    results = []
    try:
        for host, port in devices:
            print(f"\n=== {host}:{port} ===")
            ok, info = run_device(host, port, username, password, commands, args)
            print(f"  -> {'OK, log: ' if ok else 'FAILED: '}{info}")
            results.append((f"{host}:{port}", ok, info))
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 2
    finally:
        password = None  # drop the reference as soon as we are done

    print("\n=== SUMMARY ===")
    for host, ok, info in results:
        print(f"  {'OK    ' if ok else 'FAILED'}  {host}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"{len(results) - failed} OK, {failed} failed. Logs in: "
          f"{os.path.abspath(args.output)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
