# Hirschmann SSH Runner – User Manual

| | |
|---|---|
| **Tool** | `hirschmann_ssh_runner.py` / `hirschmann_ssh_runner.exe` |
| **Tool version** | 1.0 |
| **Manual version** | 1.0 |
| **Target devices** | Hirschmann switches running HiOS (tested against simulated HiOS 10.3.09) |
| **Author** | PaDv |

---

## 1. What the tool does

The tool logs in over SSH to a list of Hirschmann switches and runs the same list of CLI commands on each of them. For every switch it:

1. Connects over SSH and verifies the switch's host key.
2. Logs in with the username and password you enter at start-up.
3. Waits for the user-mode prompt `>`.
4. Sends `enable` (no enable password) and checks that the privileged prompt `#` appears.
5. Disables paging (by default with `cli numlines 0`).
6. Runs every command from the commands file.
7. Logs out.
8. Saves the whole session to its own log file.

Switches are processed one after another. If a switch fails, the tool records the reason and continues with the next one. A summary is printed at the end.

---

## 2. Requirements

**Running the Python script**
- Python 3.8 or newer
- paramiko (`pip install paramiko`)

**Running the .exe**
- Windows, no Python needed
- The exe must be started from a console (cmd or PowerShell)

**Network**
- SSH (TCP 22, or the port you set) reachable from your PC to each switch
- An account that can log in to the switches (local or RADIUS)

---

## 3. Files

| File | Purpose |
|---|---|
| `hirschmann_ssh_runner.py` | The script |
| `devices.txt` | List of switches |
| `commands.txt` | List of commands to run |
| `output\` | Created automatically; holds one log file per switch per run |
| `known_hosts` | Trusted switch host keys (location: see section 8) |

### 3.1 devices.txt

One switch per line: an IP address or hostname, optionally followed by `:port`.

```
# Lab switches
10.10.10.11
10.10.10.12
grs1042-lab.local:2222
```

- Empty lines and lines starting with `#` are ignored.
- Without `:port`, the port from `-p` is used (default 22).
- Plain IPv6 addresses (several colons) are taken as-is with the default port; `IPv6:port` notation is not supported.

### 3.2 commands.txt

One CLI command per line. Commands run in privileged (`#`) mode.

```
# Commands run in privileged (#) mode
show system info
show interface status
show vlan brief
```

- Empty lines and lines starting with `#` are ignored.
- Configuration commands work too. Put the mode changes in the file yourself, for example:

  ```
  configure
  <config commands>
  exit
  save
  ```

- Commands that ask a yes/no question are **not** confirmed automatically (see section 10).

---

## 4. Quick start

**First run** – the switches' host keys are not yet known. Check the fingerprints if you can, then run:

```
python hirschmann_ssh_runner.py -d devices.txt -c commands.txt --accept-new-hostkeys
```

**Every later run** – keys are verified against the saved file:

```
python hirschmann_ssh_runner.py -d devices.txt -c commands.txt
```

With the exe, replace `python hirschmann_ssh_runner.py` with `hirschmann_ssh_runner.exe`.

At start-up the tool prints the number of devices and commands, then asks:

```
2 device(s), 4 command(s)
Username: payo
Password:
```

The password is not shown while you type it.

---

## 5. Command-line options

| Option | Default | Description |
|---|---|---|
| `-d`, `--devices FILE` | `devices.txt` | File with the list of switches |
| `-c`, `--commands FILE` | `commands.txt` | File with the list of commands |
| `-o`, `--output DIR` | `output` | Folder for the log files (created if missing) |
| `-p`, `--port N` | `22` | SSH port for switches without `:port` in the devices file |
| `-t`, `--timeout SEC` | `30` | Idle time to wait for a prompt after each command (see section 7) |
| `--connect-timeout SEC` | `15` | Time allowed for TCP connect, SSH handshake and authentication |
| `--paging-cmd "CMD"` | `cli numlines 0` | Command sent after `enable` to disable paging; `""` skips it |
| `--known-hosts FILE` | `~/.ssh/known_hosts` | File with trusted host keys |
| `--accept-new-hostkeys` | off | Trust and save keys of switches not yet in the known_hosts file |
| `-u`, `--username NAME` | asked | Username; if omitted, you are asked at start-up |
| `-V`, `--version` | | Print the version and exit |
| `-h`, `--help` | | Print the full help and exit |

Relative paths (`devices.txt`, `output`, `.\known_hosts`) are relative to the **folder you run the command from**, not the folder of the script or exe.

There is no option for the password. It is always asked interactively so that it does not end up in shell history or scripts.

### Examples

```
# Different input files and output folder
hirschmann_ssh_runner.exe -d site_A_switches.txt -c audit_cmds.txt -o logs_site_A

# Slow devices or long outputs
hirschmann_ssh_runner.exe -d devices.txt -c commands.txt -t 60 --connect-timeout 30

# Skip the paging command
hirschmann_ssh_runner.exe -d devices.txt -c commands.txt --paging-cmd ""

# Separate known_hosts file for this tool
hirschmann_ssh_runner.exe -d devices.txt -c commands.txt --known-hosts .\hirschmann_known_hosts
```

---

## 6. Output and log files

### 6.1 Console output

The console shows each command as it runs and the result per switch:

```
=== 10.10.10.11:22 ===
  [10.10.10.11] show system info
  [10.10.10.11] show vlan brief
  -> OK, log: output\10.10.10.11_20261023_101530.txt

=== SUMMARY ===
  OK      10.10.10.11:22
  FAILED  10.10.10.12:22
1 OK, 1 failed. Logs in: C:\tools\output
```

### 6.2 Log file names

```
<host>_<YYYYMMDD_HHMMSS>.txt          port 22
<host>_p<port>_<YYYYMMDD_HHMMSS>.txt  any other port
```

A new file is created on every run, so older logs are never overwritten.

### 6.3 Log file content

Each log is a full session transcript:

- a header (device, user, time, script version)
- the login banner and prompts
- every command as echoed by the switch, followed by its output
- a final status line: `# --- finished OK ---` or `# --- FAILED: <reason> ---`

Terminal escape codes and `--More--` paging prompts are removed. The password never appears in the log. The file is saved after every command, so a run that breaks halfway still leaves a log with everything up to that point.

Example:

```
# Device : 10.10.10.11:22
# User   : payo
# Time   : 20261023_101530
# Script : hirschmann_ssh_runner.py v1.0

(Hirschmann GRS1042) >enable
(Hirschmann GRS1042) #cli numlines 0
(Hirschmann GRS1042) #show system info
System Description........Hirschmann GRS1042
...
# --- finished OK ---
```

---

## 7. Timeouts

| Option | Covers | If exceeded |
|---|---|---|
| `--connect-timeout` | TCP connect, SSH handshake, login (including RADIUS) | Switch marked FAILED |
| `-t`, `--timeout` | Waiting for the prompt after login, after `enable` and after each command | Switch marked FAILED; the last output received is written to its log |

`--timeout` counts **idle time**, not total time. Each time the switch sends new data, the countdown restarts. A long `show` command that keeps printing will not time out; a timeout only happens when the switch sends nothing for that many seconds without showing a prompt.

Both values apply to all switches and all commands in a run. Decimal values are allowed (for example `-t 7.5`).

---

## 8. SSH host keys

The tool checks every switch's host key, so it cannot be tricked into sending your credentials to a different device (man-in-the-middle).

| Situation | Without `--accept-new-hostkeys` | With `--accept-new-hostkeys` |
|---|---|---|
| Key already saved and matches | Connects | Connects |
| Switch not yet in the file | Refused | Key saved, connects |
| Key saved but **different** | Refused – possible MITM | Refused – possible MITM |

**Where keys are saved**

- Windows: `C:\Users\<user>\.ssh\known_hosts`
- Linux: `/home/<user>/.ssh/known_hosts`
- Or the file given with `--known-hosts`

Entries look like `10.10.10.11 ssh-rsa AAAA...`; for other ports, `[10.10.10.11]:2222 ssh-rsa AAAA...`.

Keys are only written when `--accept-new-hostkeys` is used. Only the switches' **public** keys are stored. Credentials are never stored.

**Recommendation:** use a separate file for this tool, for example `--known-hosts .\hirschmann_known_hosts`. When paramiko saves keys it rewrites the whole file, which can remove comments and key types it does not recognise from your normal OpenSSH known_hosts file. A separate file also gives a clear list of the switches you have trusted.

**When a switch's key changes legitimately** (factory reset, new key generated, device replaced), delete that switch's line from the known_hosts file, verify the new fingerprint, and run once with `--accept-new-hostkeys`.

---

## 9. Exit codes

| Code | Meaning |
|---|---|
| 0 | All switches OK |
| 1 | At least one switch failed |
| 2 | Aborted (Ctrl+C, or no username/password entered) |

These can be used in batch files, for example `if errorlevel 1 echo Some switches failed`.

---

## 10. Behaviour you should know about

- **Paging:** after `enable` the tool sends `cli numlines 0`. If paging is still active, the tool presses SPACE on every `--More--` prompt, so the full output is captured either way.
- **Yes/no questions:** if a command asks `(y/n)`, `[y/n]` or `(yes/no)`, the tool does **not** answer. The switch is marked FAILED and the question is written to its log. This prevents destructive actions (reboot, overwrite, reset) from being confirmed without you seeing it.
- **Errors from the switch** (for example an invalid command) do not stop the run. The error text is written to the log and the next command is sent. Check the logs after each run.
- **Prompt detection:** the tool treats a line ending in `>` or `#` as a prompt. Output where a line ends with one of those characters and the switch then pauses could in rare cases be taken as a prompt.
- **Sequential processing:** switches are handled one at a time.

---

## 11. Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `unknown host key ... not found in known_hosts` | First connection to this switch | Verify the fingerprint, run with `--accept-new-hostkeys` |
| `HOST KEY MISMATCH` | Saved key differs from the switch's key | Find out why. If legitimate, see section 8 |
| `authentication failed` | Wrong username/password, or RADIUS rejected the login | Check credentials, the RADIUS server and its log |
| `NoValidConnectionsError` / `Unable to connect to port` | Switch unreachable, SSH disabled, wrong port, firewall | Ping the switch, check that SSH is enabled, check the port |
| `TimeoutError: no prompt received` | Switch stopped responding, or the command takes longer than `-t` | Increase `-t`; check the last output in the log |
| `'enable' did not give a '#' prompt` | `enable` was refused (for example, insufficient privileges) | Check the account's privileges and the switch's enable settings |
| `TimeoutError` right after `enable` | The switch asked for an enable password (the tool expects none) | Check the switch's enable settings |
| `switch asked for a y/n confirmation` | A command needs confirmation | Run that command manually |
| Window closes immediately (exe) | Started by double-click | Start it from cmd or PowerShell |
| `file not found` / `no usable lines` | Wrong path, or the file only contains comments | Check the path and file content; relative paths start from the current folder |
| Exe is blocked or quarantined | Antivirus/EDR | See section 12 |

---

## 12. Building a Windows .exe

Build on Windows; PyInstaller cannot create Windows exe files on Linux.

```
cd C:\path\to\script
python -m venv venv
venv\Scripts\activate
pip install paramiko pyinstaller
pyinstaller --onefile --console --name hirschmann_ssh_runner hirschmann_ssh_runner.py
```

The exe is created in `dist\`. `--console` is required because the tool asks for input.

| Issue | Fix |
|---|---|
| Missing module error when the exe runs | Rebuild with `--collect-all paramiko --collect-all cryptography` |
| Antivirus or EDR blocks the exe | Build with `--onedir` instead of `--onefile`, have the exe code-signed, or have it whitelisted |
| Exe starts slowly | Normal for `--onefile` (it unpacks to `%TEMP%`); `--onedir` starts faster |

To rebuild with the same options after a code change: `pyinstaller hirschmann_ssh_runner.spec`. Update `VERSION` in the script first so `--version` matches.

---

## 13. Security notes

- Credentials are kept in memory only, never written to disk or logs, and never passed as command-line arguments.
- SSH agent and local key files are not offered to the switches.
- Host keys are verified by default; changed keys are always refused.
- Log files can contain sensitive configuration data (VLANs, addressing, user names). Store and share them according to your project's data-handling rules.
- Test new command files on one lab switch before running them on many devices, especially if they contain configuration commands.

---

## 14. Known limitations

- Tested against a simulated HiOS 10.3.09 SSH server. Not yet tested on real GRS1042/BRS30 hardware.
- The paging command `cli numlines 0` has not been verified against the HiOS CLI reference. If a switch rejects it, use `--paging-cmd` with the correct command or `--paging-cmd ""`; `--More--` handling still captures the full output.
- One timeout value for all commands and switches.
- No parallel connections.
- No `IPv6:port` notation in the devices file.

---

## 15. Version history

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-10-23 | First release of the manual (tool v1.0) |
