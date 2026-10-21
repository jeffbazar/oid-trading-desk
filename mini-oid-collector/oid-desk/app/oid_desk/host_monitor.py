"""Lightweight host resource logger for the OID Mac mini (no third-party deps).

loop:     every 15 s weekdays 6:00-13:30 PT, every 300 s otherwise, append one JSON line to
          ~/oid-data/host/host-YYYYMMDD.jsonl and write desk/cache/host-health.json.
summary [YYYYMMDD]: print peak / p95 of CPU, load, memory free and the top processes at peak.
"""
import ctypes, ctypes.util, json, os, re, subprocess, sys, time
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HOME = os.path.expanduser("~")
OUT_DIR = os.path.join(HOME, "oid-data", "host")
DESK = os.environ.get("OID_DESK_DIR", os.path.join(HOME, "oid-desk", "desk"))
SNAP = os.path.join(DESK, "cache", "host-health.json")
FAST_S, SLOW_S, TOPN = 15, 300, 8

_libc = ctypes.CDLL(ctypes.util.find_library("c"))
_libc.mach_host_self.restype = ctypes.c_uint


def cpu_ticks():
    buf = (ctypes.c_uint * 4)()
    cnt = ctypes.c_uint(4)
    if _libc.host_statistics(_libc.mach_host_self(), 3, buf, ctypes.byref(cnt)) != 0:
        return None
    return list(buf)  # user, system, idle, nice


def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def fast_window(now):
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 6 * 60 <= m < 13 * 60 + 30


def net_bytes():
    ib = ob = 0
    for ln in run(["netstat", "-ib"]).splitlines()[1:]:
        p = ln.split()
        if len(p) < 10 or not p[2].startswith("<Link") or p[0].startswith(("lo", "utun", "gif", "stf", "awdl", "llw", "anpi", "bridge", "ap")):
            continue
        try:
            ib += int(p[-5]); ob += int(p[-2])
        except ValueError:
            pass
    return ib, ob


def mem():
    free = None
    m = re.search(r"free percentage:\s*(\d+)%", run(["memory_pressure", "-Q"]))
    if m:
        free = int(m.group(1))
    swap = None
    m = re.search(r"used = ([\d.]+)M", run(["sysctl", "-n", "vm.swapusage"]))
    if m:
        swap = float(m.group(1))
    return free, swap


def short_name(comm, args):
    base = os.path.basename(comm)
    if "python" in base.lower():
        a = args.split()
        for i, t in enumerate(a[1:], 1):
            if t == "-m" and i + 1 < len(a):
                return "python:" + a[i + 1]
            if not t.startswith("-") and (t.endswith(".py") or "/" in t):
                return "python:" + os.path.basename(t)
    return base[:40]


def top_procs():
    comms = {}
    for ln in run(["ps", "-Ao", "pid=,comm="]).splitlines():
        p = ln.strip().split(None, 1)
        if len(p) == 2 and p[0].isdigit():
            comms[int(p[0])] = p[1]
    rows = []
    for ln in run(["ps", "-Ao", "pid=,pcpu=,rss=,args="]).splitlines():
        p = ln.split(None, 3)
        if len(p) < 3:
            continue
        try:
            pid, cpu, rss = int(p[0]), float(p[1]), int(p[2])
        except ValueError:
            continue
        rows.append({"pid": pid, "cpu": cpu, "rss_mb": round(rss / 1024, 1),
                     "cmd": short_name(comms.get(pid, ""), p[3] if len(p) > 3 else "")})
    rows.sort(key=lambda r: r["cpu"], reverse=True)
    return rows[:TOPN]


def sample(prev):
    t = time.time()
    now = datetime.fromtimestamp(t, PT)
    ticks, (ib, ob) = cpu_ticks(), net_bytes()
    cpu = rin = rout = None
    if prev and ticks and prev["ticks"]:
        d = [a - b for a, b in zip(ticks, prev["ticks"])]
        tot = sum(d)
        cpu = round(100.0 * (tot - d[2]) / tot, 1) if tot > 0 else None
        dt = t - prev["t"]
        if dt > 0 and ib >= prev["ib"] and ob >= prev["ob"]:
            rin, rout = round((ib - prev["ib"]) / dt), round((ob - prev["ob"]) / dt)
    free, swap = mem()
    st = os.statvfs("/System/Volumes/Data" if os.path.exists("/System/Volumes/Data") else "/")
    row = {
        "ts": datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds"),
        "ts_pt": now.strftime("%Y-%m-%d %I:%M:%S %p PT"),
        "interval_s": FAST_S if fast_window(now) else SLOW_S,
        "load1": None, "load5": None, "load15": None,
        "cpu_pct": cpu,
        "mem_free_pct": free,
        "swap_used_mb": swap,
        "disk_free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1),
        "net_in_Bps": rin, "net_out_Bps": rout,
        "top": top_procs(),
    }
    row["load1"], row["load5"], row["load15"] = [round(x, 2) for x in os.getloadavg()]
    return row, {"t": t, "ticks": ticks, "ib": ib, "ob": ob}


def write_snapshot(row):
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    snap = dict(row, written_by="com.oid.desk.host-monitor", file=os.path.join(OUT_DIR, "host-%s.jsonl" % datetime.now(PT).strftime("%Y%m%d")))
    tmp = SNAP + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snap, f, indent=1)
    os.replace(tmp, SNAP)


def loop():
    os.makedirs(OUT_DIR, exist_ok=True)
    _, prev = sample(None)
    time.sleep(2)
    while True:
        row, prev = sample(prev)
        day = datetime.now(PT).strftime("%Y%m%d")
        with open(os.path.join(OUT_DIR, "host-%s.jsonl" % day), "a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        write_snapshot(row)
        time.sleep(max(1, row["interval_s"] - (time.time() - prev["t"])))


def pct(vals, q):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def summary(day=None):
    day = day or datetime.now(PT).strftime("%Y%m%d")
    path = os.path.join(OUT_DIR, "host-%s.jsonl" % day)
    if not os.path.exists(path):
        print("no host log for", day); return 1
    rows = [json.loads(l) for l in open(path) if l.strip()]
    print("Host summary %s  (%d samples, %s -> %s)" % (day, len(rows), rows[0]["ts_pt"], rows[-1]["ts_pt"]))
    for k, lab in (("cpu_pct", "CPU %"), ("load1", "Load 1m"), ("load5", "Load 5m")):
        vals = [r.get(k) for r in rows]
        print("  %-14s peak %-7s p95 %s" % (lab, max((x for x in vals if x is not None), default=None), pct(vals, 0.95)))
    mf = [r.get("mem_free_pct") for r in rows]
    print("  %-14s min  %-7s p5  %s" % ("Mem free %", min((x for x in mf if x is not None), default=None), pct(mf, 0.05)))
    sw = [r.get("swap_used_mb") for r in rows if r.get("swap_used_mb") is not None]
    print("  %-14s max  %s MB" % ("Swap used", max(sw) if sw else None))
    pk = max((r for r in rows if r.get("cpu_pct") is not None), key=lambda r: r["cpu_pct"], default=None)
    if pk:
        print("  Top processes at CPU peak (%s, %s%%):" % (pk["ts_pt"], pk["cpu_pct"]))
        for p in pk["top"]:
            print("    %6d %6.1f%% %8.1f MB  %s" % (p["pid"], p["cpu"], p["rss_mb"], p["cmd"]))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] or ["loop"]
    if a[0] == "loop":
        loop()
    elif a[0] == "summary":
        sys.exit(summary(a[1] if len(a) > 1 else None))
    elif a[0] == "once":
        r, p = sample(None); time.sleep(2); print(json.dumps(sample(p)[0], indent=1))
