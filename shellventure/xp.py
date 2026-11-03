#!/usr/bin/env python3
"""XP + streak tracker for shellventure.

  xp.py add <points> [--skill S] <reason>   award XP (optionally to one DevOps skill)
  xp.py profile                   JSON for the profile screen (rank, skills, days)
  xp.py status [<transcript>]     one line for the status line (also counts new ! commands)
  xp.py report                    short summary for /xp
  xp.py guess on|off|state        toggle guess-first mode
  xp.py sync                      laptop only: swap XP files with the phone (~/.shellventure/phone.conf)

State lives in ~/.shellventure/xp.json (set SHELLVENTURE_HOME to move it), signed with ~/.shellventure/.xp-key: a hand edit is
detected and the last good copy (xp.good.json) comes back. Own `!` commands give BANG_XP each,
at most BANG_DAILY_CAP per day, so spamming `ls` does not level you up.
"""
import hashlib, hmac, json, math, os, secrets, sys, tempfile, time, datetime as dt
from zoneinfo import ZoneInfo

HOME = os.path.expanduser(os.environ.get("SHELLVENTURE_HOME", "~/.shellventure"))
STATE = os.path.join(HOME, "xp.json")
GUESS_FLAG = os.path.join(HOME, "guess-first.on")
OTHER = os.path.join(HOME, "xp-other.json")      # the other device's xp.json (laptop <-> phone), never on GitHub
GOOD = os.path.join(HOME, "xp.good.json")       # last signed copy: a hand-edited xp.json is replaced by it
KEY = os.path.join(HOME, ".xp-key")              # signing key, same on laptop + phone, never on GitHub
ADOPT_WINDOW = 600                               # an unsigned file is accepted only while the key is this new (first run)
MAX_ADD = 200                                    # most XP one award may give
PHONE_CONF = os.path.join(HOME, "phone.conf")    # laptop only: PHONE_IP=...
PHONE_XP = "/data/data/com.termux/files/usr/var/lib/proot-distro/containers/debian/rootfs/root/.shellventure/xp.json"
SYNC_EVERY = 15 * 60
TZ = dt.datetime.now().astimezone().tzinfo
BANG_XP = 2
BANG_DAILY_CAP = 30  # max XP per day from ! commands
WORK_DAYS = {int(x) for x in os.environ.get("SHELLVENTURE_WORKDAYS", "0,1,2,3,4").split(",")}  # Mon=0 .. Sun=6; default Mon-Fri
TITLES = ["Intern", "Pod Watcher", "Log Reader", "Shell Ninja", "Helm Rider", "Pipeline Fixer",
          "Cluster Tamer", "Root-Cause Hunter", "Kube Sensei", "SRE", "CI Wizard", "Infra Legend"]
SKILLS = ["linux", "git", "kubernetes", "containers", "databases", "networking", "cloud", "cicd", "iac",
          "observability", "security", "web", "troubleshooting"]


def today():
    return dt.datetime.now(TZ).date()


def key():
    """The signing key; created on first run (that run may adopt an old unsigned xp.json)."""
    try:
        return open(KEY).read().strip().encode()
    except OSError:
        os.makedirs(HOME, exist_ok=True)
        fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
        return open(KEY).read().strip().encode()


def sign(s):
    body = json.dumps({k: v for k, v in s.items() if k != "sig"}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key(), body.encode(), hashlib.sha256).hexdigest()


def read_signed(path):
    """State from path if its signature is right, else None. Unsigned counts only while the key is brand new."""
    try:
        with open(path) as f:
            s = json.load(f)
    except (OSError, ValueError):
        return None
    k = key()
    if "sig" not in s:
        return s if time.time() - os.path.getmtime(KEY) < ADOPT_WINDOW else None
    return s if hmac.compare_digest(s["sig"], sign(s)) else None


def load():
    s = read_signed(STATE)
    if s is not None or not os.path.exists(STATE):
        return s or {"xp": 0, "days": {}, "events": [], "seen": {}}
    # xp.json was changed outside xp.py: keep it aside, go back to the last good copy
    os.replace(STATE, f"{STATE}.tampered-{int(time.time())}")
    s = read_signed(GOOD) or {"xp": 0, "days": {}, "events": [], "seen": {}}
    s["alert"] = today().isoformat()
    save(s)
    return s


def write(path, s):
    fd, tmp = tempfile.mkstemp(dir=HOME)
    with os.fdopen(fd, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, path)


def save(s):
    os.makedirs(HOME, exist_ok=True)
    s["events"] = s["events"][-500:]
    s["sig"] = sign(s)
    write(STATE, s)
    write(GOOD, s)


def award(s, pts, reason, kind="manual", skill=None):
    pts = max(0, min(int(pts), MAX_ADD))
    d = today().isoformat()
    day = s["days"].setdefault(d, {"xp": 0, "bang": 0})
    if kind == "bang":
        if day["bang"] >= BANG_DAILY_CAP:
            return 0
        pts = min(pts, BANG_DAILY_CAP - day["bang"])
        day["bang"] += pts
    day["xp"] += pts
    s["xp"] += pts
    if skill:
        s.setdefault("skills", {})[skill] = s.get("skills", {}).get(skill, 0) + pts
    if kind != "bang":
        s["events"].append({"ts": dt.datetime.now(TZ).isoformat(timespec="seconds"),
                            "xp": pts, "why": reason, **({"skill": skill} if skill else {})})
    return pts


def combined(s):
    """Own state + the other device's: one XP total, days summed, events merged (read-only view)."""
    o = read_signed(OTHER)
    if o is None:
        return s  # missing, or changed by hand: count only this device
    days = {d: dict(v) for d, v in s["days"].items()}
    for d, v in o.get("days", {}).items():
        days.setdefault(d, {"xp": 0, "bang": 0})["xp"] += v.get("xp", 0)
    ev = sorted(s["events"] + [dict(e, why=e["why"] + " (phone)" if os.path.exists(PHONE_CONF) else e["why"] + " (laptop)")
                               for e in o.get("events", [])], key=lambda e: e["ts"])
    skills = dict(s.get("skills", {}))
    for k, v in o.get("skills", {}).items():
        skills[k] = skills.get(k, 0) + v
    return dict(s, xp=s["xp"] + o.get("xp", 0), days=days, events=ev, skills=skills)


def phone_ip():
    try:
        return dict(l.strip().split("=", 1) for l in open(PHONE_CONF) if "=" in l).get("PHONE_IP")
    except OSError:
        return None


def sync():
    """Laptop -> phone over SSH: fetch the phone's xp.json as xp-other.json, send ours as its xp-other.json."""
    import subprocess
    ip = phone_ip()
    if not ip:
        return "no phone.conf"
    o = ["-P", "8022", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "-o", "StrictHostKeyChecking=no",
         "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR"]
    tmp = OTHER + ".new"
    got = subprocess.run(["scp", *o, f"{ip}:{PHONE_XP}", tmp], capture_output=True, timeout=20).returncode == 0
    if got:
        os.replace(tmp, OTHER)
    sent = subprocess.run(["scp", *o, STATE, f"{ip}:{PHONE_XP.replace('xp.json', 'xp-other.json')}"],
                          capture_output=True, timeout=20).returncode == 0
    return f"fetched phone XP: {'yes' if got else 'no'}, sent laptop XP: {'yes' if sent else 'no'}"


def maybe_sync(s):
    """From the status line: start a background sync at most every 15 min (laptop only, never blocks)."""
    import subprocess, time
    if not phone_ip() or time.time() - s.get("last_sync", 0) < SYNC_EVERY:
        return
    s["last_sync"] = time.time()
    subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "sync"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def level(xp):
    # Lv1 at 0, Lv2 at 50, Lv3 at 200, Lv4 at 450 ... (50 * (n-1)^2)
    n = int(math.sqrt(xp / 50)) + 1
    lo, hi = 50 * (n - 1) ** 2, 50 * n ** 2
    return n, lo, hi


def skill_level(xp):
    # skills level faster: Lv1 at 0, Lv2 at 30, Lv3 at 120, Lv4 at 270 ... (30 * (n-1)^2)
    n = int(math.sqrt(xp / 30)) + 1
    return n, 30 * (n - 1) ** 2, 30 * n ** 2


def profile(s):
    n, lo, hi = level(s["xp"])
    return {"xp": s["xp"], "level": n, "title": TITLES[min(n - 1, len(TITLES) - 1)], "lo": lo, "hi": hi,
            "streak": streak(s), "today": s["days"].get(today().isoformat(), {}).get("xp", 0),
            "skills": {k: {"xp": s.get("skills", {}).get(k, 0), "level": skill_level(s.get("skills", {}).get(k, 0))[0],
                           "lo": skill_level(s.get("skills", {}).get(k, 0))[1], "hi": skill_level(s.get("skills", {}).get(k, 0))[2]}
                       for k in SKILLS},
            "week": [[(today() - dt.timedelta(days=i)).strftime("%a"),
                      s["days"].get((today() - dt.timedelta(days=i)).isoformat(), {}).get("xp", 0)] for i in range(6, -1, -1)]}


def streak(s):
    """Work days in a row with XP. Fri/Sat are skipped; today counts only once earned."""
    d, count = today(), 0
    if s["days"].get(d.isoformat(), {}).get("xp", 0) == 0:
        d -= dt.timedelta(days=1)
    for _ in range(400):
        if d.weekday() not in WORK_DAYS:
            d -= dt.timedelta(days=1)
            continue
        if s["days"].get(d.isoformat(), {}).get("xp", 0) > 0:
            count += 1
            d -= dt.timedelta(days=1)
        else:
            break
    return count


def scan_bangs(s, transcript):
    """Award XP for new `!` commands in this transcript (dedup by message uuid)."""
    if not transcript or not os.path.isfile(transcript):
        return
    seen = s["seen"].setdefault(transcript, {"off": 0})
    size = os.path.getsize(transcript)
    if size < seen["off"]:
        seen["off"] = 0
    with open(transcript, "rb") as f:
        f.seek(seen["off"])
        for raw in f:
            if not raw.endswith(b"\n"):
                break  # line still being written; read it next time
            seen["off"] += len(raw)
            if b"<bash-input>" not in raw:
                continue
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            c = m.get("message", {}).get("content")
            if m.get("type") == "user" and isinstance(c, str) and c.startswith("<bash-input>"):
                award(s, BANG_XP, "own command", kind="bang")
    # forget transcripts we have not touched in a while
    if len(s["seen"]) > 50:
        for k in list(s["seen"])[:-50]:
            del s["seen"][k]


def bar(frac, width=8):
    # XP_FULL / XP_EMPTY / XP_STAR: the phone font has no ▰ ▱ ★, so it sets its own characters
    full = int(round(frac * width))
    return os.environ.get("XP_FULL", "▰") * full + os.environ.get("XP_EMPTY", "▱") * (width - full)


def status(s):
    n, lo, hi = level(s["xp"])
    title = TITLES[min(n - 1, len(TITLES) - 1)]
    t = s["days"].get(today().isoformat(), {}).get("xp", 0)
    gf = " guess:on" if os.path.exists(GUESS_FLAG) else ""
    return (f"{os.environ.get('XP_STAR', '★')} Lv{n} {title} {s['xp']}xp {bar((s['xp'] - lo) / (hi - lo))} "
            f"today +{t}  streak {streak(s)}d{gf}" + ("  ⚠️ XP file was edited: restored" if s.get("alert") == today().isoformat() else ""))


def report(s):
    n, lo, hi = level(s["xp"])
    lines = [status(s), f"next level in {hi - s['xp']} xp", "", "last wins:"]
    for e in s["events"][-5:][::-1]:
        lines.append(f"  +{e['xp']:>3}  {e['ts'][5:16].replace('T', ' ')}  {e['why']}")
    week = [(today() - dt.timedelta(days=i)) for i in range(6, -1, -1)]
    lines += ["", "last 7 days:"]
    for d in week:
        x = s["days"].get(d.isoformat(), {}).get("xp", 0)
        lines.append(f"  {d.strftime('%a')}  {'█' * min(x // 5, 30):<30} {x}")
    return "\n".join(lines)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    s = load()
    if cmd == "add":
        rest = argv[3:]
        skill = None
        if len(rest) >= 2 and rest[0] == "--skill":
            skill, rest = rest[1], rest[2:]
        pts, why = int(argv[2]), " ".join(rest) or "win"
        before = level(combined(s)["xp"])[0]
        got = award(s, pts, why, skill=skill)
        save(s)
        after = level(combined(s)["xp"])[0]
        print(f"+{got} XP ({why}). {status(combined(s))}")
        if after > before:
            print(f"LEVEL_UP {after} {TITLES[min(after - 1, len(TITLES) - 1)]}")
    elif cmd == "profile":
        print(json.dumps(profile(combined(s))))
    elif cmd == "status":
        scan_bangs(s, argv[2] if len(argv) > 2 else None)
        maybe_sync(s)
        save(s)
        print(status(combined(s)))
    elif cmd == "report":
        print(report(combined(s)))
    elif cmd == "sync":
        print(sync())
    elif cmd == "guess":
        arg = argv[2] if len(argv) > 2 else "state"
        if arg == "on":
            open(GUESS_FLAG, "w").close()
        elif arg == "off" and os.path.exists(GUESS_FLAG):
            os.remove(GUESS_FLAG)
        print("guess-first:", "on" if os.path.exists(GUESS_FLAG) else "off")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
