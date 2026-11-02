"""GM 2026-10-25 (Mythastria stopped during a playtest with no trace): run the simulator service and keep what it prints.
Start_Mythastria.bat calls this instead of the service directly. Everything the service prints still shows in the window
and is also written, with the time, to engine\\logs\\mythastria_<date>_<time>.log.
How a run ended reads from the log's last lines:
  - "STOPPED exit code N": the service stopped by itself (a crash shows its traceback just above);
  - "STOPPED by Ctrl+C": stopped from the window on purpose;
  - no STOPPED line: the window was closed or the process was killed (or the PC lost power).
The 30 newest logs are kept; older ones are deleted.
  py -3 tools\\run_logged.py tools\\sim_service.py --port 8772 ...
"""
import datetime
import os
import subprocess
import sys
from pathlib import Path

LOGS = Path(__file__).resolve().parent.parent / "logs"
KEEP = 30


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def prune():
    old = sorted(LOGS.glob("mythastria_*.log"))[:-KEEP]
    for f in old:
        try:
            f.unlink()
        except OSError:
            pass


def main(argv):
    if not argv:
        print("Usage: run_logged.py <script.py> [arguments]")
        return 2
    LOGS.mkdir(exist_ok=True)
    path = LOGS / ("mythastria_%s.log" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    cmd = [sys.executable, "-u"] + argv
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")   # a pipe would otherwise use the ANSI codepage
    print(" Log: %s" % path)
    with open(path, "a", encoding="utf-8", buffering=1) as log:
        log.write("%s START %s\n" % (stamp(), subprocess.list2cmdline(cmd)))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        try:
            for line in p.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write("%s %s" % (stamp(), line))
            code = p.wait()
            log.write("%s STOPPED exit code %s\n" % (stamp(), code))
        except KeyboardInterrupt:
            p.terminate()
            code = p.wait()
            log.write("%s STOPPED by Ctrl+C (exit code %s)\n" % (stamp(), code))
    prune()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
