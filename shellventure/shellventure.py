#!/usr/bin/env python3
"""SHELLVENTURE: a terminal adventure for real DevOps skills.

  shellventure                 map of all worlds
  shellventure play <world>    enter a world (bash, git, k8s, gcloud) in a game shell
  shellventure reset <world>   rebuild a world with new codes
  shellventure stop            delete the local kind cluster used by the k8s world

Inside the game shell: room, check [code], hint, map, exit.
Everything runs under ~/shellventure-lab. The k8s world uses its own kind cluster and
kubeconfig; the gcloud world uses its own CLOUDSDK_CONFIG. Work clusters and GCP
are never touched.
"""
import configparser, hashlib, io, json, os, random, re, shutil, subprocess, sys, time
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.markup import escape as escape_markup
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

ROOT = Path.home() / "shellventure-lab"
STATE = ROOT / ".state.json"
XP = Path(__file__).resolve().parent / "xp.py"
HERE = Path(__file__).resolve().parent
KIND_NAME = "shellventure"
KUBECONFIG = ROOT / "k8s" / "kubeconfig"
GCLOUD_CFG = ROOT / "gcloud" / "sdk"
con = Console()
AUTOCHECK = False   # set by _autocheck: one quick look, no spinners, no output unless the room opens

WORDS = ["falcon", "cedar", "petra", "wadi", "nebula", "copper", "harbor", "quartz", "saffron",
         "orbit", "jasmine", "beacon", "comet", "dune", "ember", "glacier", "lantern", "prism",
         "oasis", "pixel", "raven", "sphinx", "tundra", "violet", "zephyr", "basalt", "cobalt"]
NAMES = ["alex", "sam", "kim", "lee", "max", "ava", "noah", "mia", "leo", "zoe"]

BANNER = "▓▒░ S H E L L V E N T U R E ░▒▓"

DOOR = [
    "┌────────┐\n│        │\n│   ▓▓   │\n│   ▓▓  ●│\n│        │\n│        │\n└────────┘",
    "┌────────┐\n│ ╲      │\n│  ╲▓▓   │\n│   ▓▓  ●│\n│  ╱     │\n│ ╱      │\n└────────┘",
    "┌────────┐\n│░╲      │\n│░░╲     │\n│░░ │   ●│\n│░░╱     │\n│░╱      │\n└────────┘",
    "┌────────┐\n│░░░░░░░░│\n│░░ ☼☼ ░░│\n│░ \\o/ ░░│\n│░░ |  ░░│\n│░░/ \\ ░░│\n└────────┘",
]


# ---------------------------------------------------------------- helpers
def sh(cmd, cwd=None, env=None, check=True, capture=True):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(cmd, cwd=cwd, env=e, shell=isinstance(cmd, str), text=True,
                       capture_output=capture)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}\n{r.stderr}")
    return r


def code():
    return f"{random.choice(WORDS)}-{random.randint(10, 99)}"


def h(s):
    return hashlib.sha256(("escape:" + s.strip().lower()).encode()).hexdigest()


def load():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"worlds": {}, "active": None}


def save(s):
    ROOT.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1))
    tmp.replace(STATE)


SKILL_OF = {"bash": "linux", "linux": "linux", "git": "git", "k8s": "kubernetes", "helm": "kubernetes",
            "boss": "kubernetes", "cka": "kubernetes", "incidents": "troubleshooting", "docker": "containers", "sql": "databases",
            "network": "networking", "gcloud": "cloud", "cicd": "cicd", "terraform": "iac",
            "observability": "observability", "today": "troubleshooting", "mybugs": "troubleshooting", "daily": "linux",
            "security": "security", "web": "web"}


def award(points, why, skill=None):
    if not XP.exists():
        return
    args = [sys.executable, "-I", str(XP), "add", str(points)] + (["--skill", skill] if skill else []) + [why]
    out = sh(args, check=False).stdout
    for line in out.splitlines():
        if line.startswith("LEVEL_UP "):
            _, n, title = line.split(" ", 2)
            con.print(Panel(Align.center(Text.from_markup(
                f"[bold yellow]★ ★ ★  LEVEL UP  ★ ★ ★[/]\n\n[bold]Level {n}: {title}[/]")), border_style="yellow", box=box.DOUBLE))


def show_profile():
    """Profile screen: rank, level bar, one bar per DevOps skill, badges, streak, last 7 days."""
    if not XP.exists():
        return
    try:
        pr = json.loads(sh([sys.executable, "-I", str(XP), "profile"], check=False).stdout)
    except ValueError:
        return
    s = load()
    con.clear()
    frac = (pr["xp"] - pr["lo"]) / max(pr["hi"] - pr["lo"], 1)
    head = Text.from_markup(f"[bold yellow]Level {pr['level']} · {pr['title']}[/]   {pr['xp']} XP   "
                            f"[cyan]streak {pr['streak']}d[/]   today +{pr['today']}\n"
                            f"[yellow]{'█' * int(frac * 30)}[/][grey35]{'░' * (30 - int(frac * 30))}[/]  "
                            f"{pr['hi'] - pr['xp']} XP to level {pr['level'] + 1}")
    con.print(Panel(head, title="[bold]YOUR PROFILE[/]", border_style="yellow", padding=(1, 2)))
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold grey62", padding=(0, 1))
    t.add_column("skill"); t.add_column("lv", justify="right"); t.add_column("progress"); t.add_column("xp", justify="right")
    for k, v in sorted(pr["skills"].items(), key=lambda kv: -kv[1]["xp"]):
        f = (v["xp"] - v["lo"]) / max(v["hi"] - v["lo"], 1)
        bar = f"[{'green' if v['xp'] else 'grey35'}]{'█' * int(f * 16)}[/][grey23]{'░' * (16 - int(f * 16))}[/]"
        t.add_row(k, str(v["level"]), bar, str(v["xp"]))
    con.print(t)
    con.print(Align.center(badge_line(s)))
    week = "   ".join(f"{d} [green]{'▇' if x >= 30 else '▅' if x >= 10 else '▂' if x else '·'}[/]" for d, x in pr["week"])
    con.print(Align.center(f"\n[grey62]last 7 days[/]  {week}"))
    con.print(Align.center("\n[grey50](press a key)[/]"))
    getkey()


def progress(done, n, width=2):
    """Line bar + count. Uses only ━ (box drawing): every terminal font has it, unlike ■ □ ✅ ▰."""
    if n and done >= n:
        return f"[green]{'━' * (n * width)}  done[/]"
    return f"[green]{'━' * (done * width)}[/][grey35]{'━' * ((n - done) * width)}[/]  [grey62]{done}/{n}[/]"


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 60}m {sec % 60:02d}s"


# ---------------------------------------------------------------- BASH world
def bash_setup(d, w):
    # room 1: haystack, real key only in a hidden file
    r = d / "1-haystack"
    for i in range(400):
        p = r / f"zone{random.randint(1, 8)}" / f"sector{random.randint(1, 6)}" / f"log{i}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [" ".join(random.choices(WORDS, k=8)) for _ in range(5)]
        if i % 9 == 0:
            lines.insert(2, f"KEY={code()}")  # fake keys
        p.write_text("\n".join(lines) + "\n")
    real = code()
    hid = r / f"zone{random.randint(1, 8)}" / f"sector{random.randint(1, 6)}" / ".whisper"
    hid.parent.mkdir(parents=True, exist_ok=True)
    hid.write_text(f"you found me\nKEY={real}\n")
    w["answers"]["1"] = h(real)

    # room 2: the IP with the most 500 errors (not the busiest IP)
    r = d / "2-noisy-log"
    r.mkdir(parents=True, exist_ok=True)
    ips = [f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}" for _ in range(25)]
    target, busy = ips[0], ips[1]
    rows = []
    for ip in ips:
        n = 400 if ip == busy else random.randint(60, 140)
        e500 = 57 if ip == target else random.randint(0, 35)
        for k in range(n):
            st = 500 if k < e500 else random.choice([200, 200, 200, 301, 404])
            if ip == busy and k < 120:
                st = 404
            rows.append((ip, st))
    random.shuffle(rows)
    paths = ["/api/pay", "/login", "/health", "/api/orders", "/static/app.js"]
    with open(r / "access.log", "w") as f:
        for i, (ip, st) in enumerate(rows):
            f.write(f'{ip} - - [29/Oct/2026:10:{i // 60 % 60:02d}:{i % 60:02d} +0300] '
                    f'"GET {random.choice(paths)} HTTP/1.1" {st} {random.randint(200, 9000)}\n')
    w["answers"]["2"] = h(target)

    # room 3: broken script (CRLF, no +x, bad shebang). Check = it runs by itself.
    r = d / "3-broken-script"
    r.mkdir(parents=True, exist_ok=True)
    secret = code()
    import base64
    enc = base64.b64encode(secret[::-1].encode()).decode()
    body = f"#!/bin/bahs\ncode=$(echo '{enc}' | base64 -d | rev)\necho \"The door says: $code\"\n"
    (r / "open-door.sh").write_bytes(body.replace("\n", "\r\n").encode())
    os.chmod(r / "open-door.sh", 0o644)
    w["data"]["3"] = h(secret)

    # room 4: jq vault
    r = d / "4-json-vault"
    r.mkdir(parents=True, exist_ok=True)
    real = code()
    floors = []
    for fl in range(1, 6):
        doors = []
        for _ in range(random.randint(8, 14)):
            doors.append({"id": code(), "color": random.choice(["red", "green", "blue"]),
                          "locked": random.random() < 0.6 if fl != 3 else True})
        floors.append({"floor": fl, "doors": doors})
    f3 = floors[2]["doors"]
    f3.insert(random.randint(0, len(f3)), {"id": real, "color": "blue", "locked": False})
    f3.insert(random.randint(0, len(f3)), {"id": code(), "color": "red", "locked": False})
    floors[0]["doors"].append({"id": code(), "color": "blue", "locked": False})
    (r / "vault.json").write_text(json.dumps({"building": "escape", "floors": floors}))
    w["answers"]["4"] = h(real)


def bash_check_script(d, w, _):
    p = d / "3-broken-script" / "open-door.sh"
    if not os.access(p, os.X_OK):
        return False, "The script is not executable yet."
    r = subprocess.run([str(p)], cwd=p.parent, capture_output=True, text=True)
    out = r.stdout.strip()
    if r.returncode != 0 or "door says:" not in out:
        return False, "./open-door.sh still fails:\n" + (r.stderr.strip()[:300] or out[:300])
    got = out.split("door says:")[-1].strip()
    return (h(got) == w["data"]["3"]), "It printed the wrong thing."


BASH = {
    "title": "Bash Dungeon", "needs": ["find", "awk", "jq"], "dir": "bash", "setup": bash_setup, "rooms": [
        {"name": "The Haystack", "dir": "1-haystack", "answer": True,
         "story": "400 files. Many say [bold]KEY=...[/]. All of them lie, except one.",
         "task": "The real key is inside a [bold]hidden file[/]. Find it.\nThen: [cyan]check <key>[/]",
         "hints": ["Hidden files start with a dot. `ls` does not show them.",
                   "`find . -type f -name '.*'`",
                   "`find . -type f -name '.*' -exec cat {} +`"]},
        {"name": "The Noisy Log", "dir": "2-noisy-log", "answer": True,
         "story": "The server is screaming. One client keeps breaking it.",
         "task": "Which IP got the [bold]most 500 errors[/] in access.log?\nThen: [cyan]check <ip>[/]",
         "hints": ["The status code is field 9 when you split by spaces.",
                   "`awk '$9==500 {print $1}' access.log`",
                   "`awk '$9==500 {print $1}' access.log | sort | uniq -c | sort -rn | head -3`"]},
        {"name": "The Broken Script", "dir": "3-broken-script", "check": bash_check_script,
         "story": "A script opens the door. But someone broke it in [bold]3 ways[/].",
         "task": "Make [bold]./open-door.sh[/] run by itself (not `bash open-door.sh`).\nThen: [cyan]check[/]",
         "hints": ["Look at the file closely: `cat -A open-door.sh | head -2`. What is ^M?",
                   "Windows line endings: `sed -i 's/\\r$//' open-door.sh`. Then look at line 1.",
                   "Fix the shebang to `#!/bin/bash` and run `chmod +x open-door.sh`."],
         "steps": [
             {"name": "Windows line endings", "done": lambda d, w: b"\r" not in (d / "3-broken-script" / "open-door.sh").read_bytes(),
              "hints": ["Look at the file closely: `cat -A open-door.sh | head -2`. What is ^M?",
                        "^M is \\r: Windows line endings. Linux reads `#!/bin/bash\\r` as a different program.",
                        "`sed -i 's/\\r$//' open-door.sh`"]},
             {"name": "the shebang (line 1)", "done": lambda d, w: os.path.exists(
                 (d / "3-broken-script" / "open-door.sh").read_text().splitlines()[0].removeprefix("#!").strip()),
              "hints": ["Read line 1: `head -1 open-door.sh`. Does that program exist?",
                        "`ls -l /bin/bahs` vs `ls -l /bin/bash`",
                        "`sed -i '1s|.*|#!/bin/bash|' open-door.sh`"]},
             {"name": "the execute bit", "done": lambda d, w: bool((d / "3-broken-script" / "open-door.sh").stat().st_mode & 0o100),
              "hints": ["`ls -l open-door.sh`: is there an x in the bits?",
                        "`./file` only runs files with the execute bit.", "`chmod +x open-door.sh`"]},
         ]},
        {"name": "The JSON Vault", "dir": "4-json-vault", "answer": True,
         "story": "A building of 5 floors. Only one door leads out.",
         "task": "On [bold]floor 3[/], find the door that is [bold]blue[/] and [bold]not locked[/].\n"
                 "Its id is the key. Then: [cyan]check <id>[/]",
         "hints": ["`jq '.floors[] | select(.floor==3)' vault.json`",
                   "Inside: `.doors[] | select(.locked==false)`",
                   "`jq -r '.floors[]|select(.floor==3).doors[]|select(.locked==false and .color==\"blue\").id' vault.json`"]},
    ]}


# ---------------------------------------------------------------- GIT world
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args, who="keeper", env=None):
    e = dict(GIT_ENV, GIT_AUTHOR_NAME=who, GIT_AUTHOR_EMAIL=f"{who}@shellventure.local",
             GIT_COMMITTER_NAME=who, GIT_COMMITTER_EMAIL=f"{who}@shellventure.local", **(env or {}))
    return sh(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
              cwd=repo, env=e).stdout.strip()


def new_repo(p):
    p.mkdir(parents=True, exist_ok=True)
    git(p, "init", "-q", "-b", "main")
    return p


def git_setup(d, w):
    # room 1: a code that was added then removed
    r = new_repo(d / "1-lost-commit")
    real, at = code(), random.randint(12, 25)
    for i in range(40):
        (r / "notes.txt").write_text(f"day {i}: " + " ".join(random.choices(WORDS, k=6)) + "\n")
        cfg = "[door]\nlocked = true\n"
        if i == at:
            cfg += f"code = {real}\n"
        (r / "config.ini").write_text(cfg)
        git(r, "add", "-A")
        git(r, "commit", "-qm", random.choice(["update notes", "small fix", "tidy", "wip"]),
            who=random.choice(NAMES))
    w["answers"]["1"] = h(real)

    # room 2: a deleted branch
    r = new_repo(d / "2-deleted-branch")
    (r / "README").write_text("nothing here\n")
    git(r, "add", "-A"); git(r, "commit", "-qm", "init")
    real = code()
    git(r, "checkout", "-qb", "secret")
    (r / "treasure.txt").write_text(f"the code is {real}\n")
    git(r, "add", "-A"); git(r, "commit", "-qm", "hide the treasure")
    git(r, "checkout", "-q", "main")
    for i in range(5):
        (r / "README").write_text(f"nothing here {i}\n")
        git(r, "commit", "-qam", "readme")
    git(r, "branch", "-qD", "secret")
    w["answers"]["2"] = h(real)

    # room 3: blame line 23
    r = new_repo(d / "3-who-did-it")
    lines = [f"guard {i + 1}: sleeping" for i in range(40)]
    (r / "guard.txt").write_text("\n".join(lines) + "\n")
    git(r, "add", "-A"); git(r, "commit", "-qm", "guards", who="captain")
    culprit = random.choice(NAMES)
    others = [n for n in NAMES if n != culprit]
    plan = [(random.randint(0, 39), random.choice(others)) for _ in range(25)]
    plan.insert(random.randint(8, 18), (22, culprit))
    plan = [(ln, who) for (ln, who) in plan if not (ln == 22 and who != culprit)]
    plan += [(random.choice([5, 30, 39]), random.choice(others)) for _ in range(3)]
    for k, (ln, who) in enumerate(plan):
        lines[ln] = f"guard {ln + 1}: " + random.choice(["awake", "asleep", "watching", "gone"]) + f" (shift {k})"
        (r / "guard.txt").write_text("\n".join(lines) + "\n")
        git(r, "commit", "-qam", "change shift", who=who)
    w["answers"]["3"] = h(culprit)

    # room 4: bisect the first bad commit
    r = new_repo(d / "4-bad-commit")
    (r / "test.sh").write_text("#!/bin/sh\ngrep -q '^speed=fast$' app.conf\n")
    os.chmod(r / "test.sh", 0o755)
    bad_at, bad = random.randint(20, 50), None
    for i in range(64):
        speed = "slow" if i >= bad_at else "fast"
        (r / "app.conf").write_text(f"name=app\nbuild={i}\nspeed={speed}\ncolor={random.choice(WORDS)}\n")
        git(r, "add", "-A"); git(r, "commit", "-qm", f"build {i}", who=random.choice(NAMES))
        if i == bad_at:
            bad = git(r, "rev-parse", "HEAD")
    w["data"]["4"] = bad


def git_check_bisect(d, w, ans):
    ans = (ans or "").strip().lower()
    if len(ans) < 7:
        return False, "Give at least the first 7 characters of the commit hash."
    return w["data"]["4"].startswith(ans), "That is not the first bad commit."


GIT = {
    "title": "Git Temple", "needs": ["git"], "dir": "git", "setup": git_setup, "rooms": [
        {"name": "The Lost Commit", "dir": "1-lost-commit", "answer": True,
         "story": "Someone wrote the door code in [bold]config.ini[/]. Then deleted it. Git never forgets.",
         "task": "Find the code that was once in config.ini.\nThen: [cyan]check <code>[/]",
         "hints": ["Git can search the history of changes, not only the files today.",
                   "`git log -p -- config.ini`  (look for a + line)",
                   "`git log -S 'code =' -p -- config.ini`"]},
        {"name": "The Deleted Branch", "dir": "2-deleted-branch", "answer": True,
         "story": "A branch called [bold]secret[/] held the treasure. It was deleted with -D.",
         "task": "Bring it back. Read treasure.txt.\nThen: [cyan]check <code>[/]",
         "hints": ["Git keeps a diary of every place HEAD has been.",
                   "`git reflog`  (look for 'hide the treasure')",
                   "`git show <hash>:treasure.txt`  or  `git branch secret <hash>`"]},
        {"name": "Who Did It?", "dir": "3-who-did-it", "answer": True,
         "story": "Guard 23 left his post. Someone changed his line in [bold]guard.txt[/].",
         "task": "Who was the [bold]last[/] person to change line 23?\nThen: [cyan]check <name>[/]",
         "hints": ["There is a git command made for blaming people.",
                   "`git blame guard.txt`",
                   "`git blame -L 23,23 guard.txt`"]},
        {"name": "The Bad Commit", "dir": "4-bad-commit", "check": git_check_bisect, "typed": True,
         "story": "64 builds. [bold]./test.sh[/] passed at the start. Now it fails.",
         "task": "Find the [bold]first commit[/] where ./test.sh fails.\nThen: [cyan]check <hash>[/] (7+ chars)",
         "hints": ["Don't check 64 commits by hand. Git can do binary search.",
                   "`git bisect start; git bisect bad HEAD; git bisect good <first-commit>`",
                   "`git bisect run ./test.sh`  then  `git bisect reset`"]},
    ]}


# ---------------------------------------------------------------- K8S world
def kc(*args, check=True, stdin=None):
    r = subprocess.run(["kubectl", "--kubeconfig", str(KUBECONFIG), "--context", f"kind-{KIND_NAME}", *args],
                       input=stdin, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)}: {r.stderr}")
    return r.stdout


def kind_up():
    clusters = sh(["kind", "get", "clusters"], check=False).stdout.split()
    KUBECONFIG.parent.mkdir(parents=True, exist_ok=True)
    if KIND_NAME not in clusters:
        sh(["kind", "create", "cluster", "--name", KIND_NAME, "--image", "kindest/node:v1.32.2",
            "--kubeconfig", str(KUBECONFIG), "--wait", "90s"])
    else:
        sh(["kind", "export", "kubeconfig", "--name", KIND_NAME, "--kubeconfig", str(KUBECONFIG)])
    for img in ["busybox:1.36", "nginx:1.27-alpine"]:
        sh(f"docker image inspect {img} >/dev/null 2>&1 || docker pull -q {img}")
        sh(["kind", "load", "docker-image", img, "--name", KIND_NAME])


def deploy(ns, name, container, labels=None):
    labels = labels or {"app": name}
    return {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "namespace": ns},
            "spec": {"replicas": 1, "selector": {"matchLabels": labels},
                     "template": {"metadata": {"labels": labels},
                                  "spec": {"terminationGracePeriodSeconds": 1,
                                           "containers": [dict({"name": name, "imagePullPolicy": "IfNotPresent"},
                                                               **container)]}}}}


K8S_ROOMS = {
    "1": ("room1-door", lambda ns: [deploy(ns, "door", {"image": "busybox:1.63", "command": ["sleep", "infinity"]})]),
    "2": ("room2-guard", lambda ns: [
        {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "guard-secret", "namespace": ns},
         "stringData": {"passwd": "open-sesame"}},
        deploy(ns, "guard", {"image": "busybox:1.36", "command": ["sh", "-c", "echo guard is awake; sleep infinity"],
                             "env": [{"name": "PASSWORD", "valueFrom": {"secretKeyRef": {"name": "guard-secret", "key": "password"}}}]})]),
    "3": ("room3-corridor", lambda ns: [
        deploy(ns, "lantern", {"image": "nginx:1.27-alpine", "ports": [{"containerPort": 80}]}),
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "lamp", "namespace": ns},
         "spec": {"selector": {"app": "lamp"}, "ports": [{"port": 80, "targetPort": 80}]}}]),
    "4": ("room4-monster", lambda ns: [deploy(ns, "monster", {
        "image": "busybox:1.36",
        "command": ["sh", "-c", "x=$(head -c 30000000 /dev/zero | tr '\\0' a); echo monster ate; sleep infinity"],
        "resources": {"limits": {"memory": "10Mi"}, "requests": {"memory": "10Mi"}}})]),
    "5": ("room5-gate", lambda ns: [
        {"apiVersion": "v1", "kind": "ResourceQuota", "metadata": {"name": "lock", "namespace": ns},
         "spec": {"hard": {"pods": "0"}}},
        deploy(ns, "gate", {"image": "nginx:1.27-alpine",
                            "readinessProbe": {"httpGet": {"path": "/", "port": 8080}, "periodSeconds": 2}})]),
}


def k8s_setup(d, w):
    with con.status("[cyan]Building your private cluster (kind, about 1 minute)...", spinner="dots12"):
        kind_up()
    for rid, (ns, make) in K8S_ROOMS.items():
        kc("delete", "ns", ns, "--ignore-not-found", "--wait=true")
        kc("create", "ns", ns)
        kc("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": make(ns)}))
    (d / "README.txt").write_text("Your cluster: kind-shellventure. KUBECONFIG is already set in the game shell.\n")


def ready(ns, name, polls=None):
    polls = polls or (1 if AUTOCHECK else 3)
    for i in range(polls):
        try:
            st = json.loads(kc("get", "deploy", name, "-n", ns, "-o", "json"))["status"]
        except (RuntimeError, ValueError):
            return False
        if st.get("readyReplicas", 0) < 1 or st.get("unavailableReplicas", 0) > 0:
            return False
        if i < polls - 1:
            time.sleep(3)
    return True


def k8s_check(rid, name, extra=None):
    def chk(d, w, _):
        ns = K8S_ROOMS[rid][0]
        with con.status("[cyan]Watching the room for a few seconds...", spinner="dots12"):
            if extra:
                ok, msg = extra(ns)
                if not ok:
                    return False, msg
            return ready(ns, name), f"deploy/{name} in ns {ns} is not healthy and ready yet."
    return chk


def corridor_extra(ns):
    try:
        ep = json.loads(kc("get", "endpoints", "lamp", "-n", ns, "-o", "json"))
    except (RuntimeError, ValueError):
        return False, "Service 'lamp' must still exist."
    if not any(s.get("addresses") for s in ep.get("subsets", [])):
        return False, "Service 'lamp' has no endpoints. Nobody answers in the corridor."
    return True, ""


def monster_extra(ns):
    try:
        dep = json.loads(kc("get", "deploy", "monster", "-n", ns, "-o", "json"))
        cmd = " ".join(dep["spec"]["template"]["spec"]["containers"][0]["command"])
    except (RuntimeError, ValueError, KeyError, IndexError):
        return False, "deploy/monster must still exist."
    if "head -c 30000000" not in cmd:
        return False, "No cheating: the monster must still eat (keep its command)."
    return True, ""


def gate_extra(ns):
    try:
        dep = json.loads(kc("get", "deploy", "gate", "-n", ns, "-o", "json"))
        probe = dep["spec"]["template"]["spec"]["containers"][0].get("readinessProbe")
    except (RuntimeError, ValueError, KeyError, IndexError):
        return False, "deploy/gate must still exist."
    if not probe:
        return False, "No cheating: the gate needs its readiness probe."
    return True, ""


K8S = {
    "title": "Kube Castle", "needs": ["kind", "docker", "kubectl"], "dir": "k8s", "setup": k8s_setup, "kind": True, "rooms": [
        {"name": "The Locked Door", "ns": "room1-door", "check": k8s_check("1", "door"),
         "story": "The door pod will not even start.",
         "task": "Namespace [bold]room1-door[/]. Make deploy/door Ready.\nThen: [cyan]check[/]",
         "hints": ["`kubectl get pods -n room1-door` then describe the pod.",
                   "Read the Events. Is the image name right?",
                   "`kubectl set image deploy/door door=busybox:1.36 -n room1-door`"]},
        {"name": "The Silent Guard", "ns": "room2-guard", "check": k8s_check("2", "guard"),
         "story": "The guard needs a password to wake up. Someone gave him the wrong paper.",
         "task": "Namespace [bold]room2-guard[/]. Make deploy/guard Ready.\nThen: [cyan]check[/]",
         "hints": ["Status says CreateContainerConfigError. Describe the pod.",
                   "Compare the key the pod wants with the keys in the secret: `kubectl get secret guard-secret -o yaml`",
                   "Either add key `password` to the secret, or change the deploy to use key `passwd`."]},
        {"name": "The Dark Corridor", "ns": "room3-corridor", "check": k8s_check("3", "lantern", corridor_extra),
         "story": "The lantern is burning, but the [bold]lamp[/] service shows nothing.",
         "task": "Namespace [bold]room3-corridor[/]. Make service [bold]lamp[/] send traffic to the lantern pods.\nThen: [cyan]check[/]",
         "hints": ["`kubectl get endpoints lamp -n room3-corridor`  Empty? Why?",
                   "Compare the service selector with the pod labels: `kubectl get pods --show-labels`",
                   "`kubectl patch svc lamp -n room3-corridor -p '{\"spec\":{\"selector\":{\"app\":\"lantern\"}}}'`"]},
        {"name": "The Hungry Monster", "ns": "room4-monster", "check": k8s_check("4", "monster", monster_extra),
         "story": "The monster eats 30 MB for breakfast. It keeps dying.",
         "task": "Namespace [bold]room4-monster[/]. Keep its command. Make it live.\nThen: [cyan]check[/]",
         "hints": ["Describe the pod. Look at Last State: Reason.",
                   "OOMKilled = memory limit too small for what it eats.",
                   "`kubectl set resources deploy/monster -n room4-monster --limits=memory=128Mi --requests=memory=64Mi`"]},
        {"name": "The Final Gate", "ns": "room5-gate", "check": k8s_check("5", "gate", gate_extra),
         "story": "The last gate. [bold]Two locks[/]. No pods at all.",
         "task": "Namespace [bold]room5-gate[/]. Make deploy/gate Ready. Keep a readiness probe.\nThen: [cyan]check[/]",
         "hints": ["No pods? Look at the ReplicaSet events: `kubectl describe rs -n room5-gate`",
                   "Lock 1 is a ResourceQuota. Lock 2 shows up after: nginx listens on port 80.",
                   "Delete/raise quota `lock`, then fix the readinessProbe port to 80."],
         "steps": [
             {"name": "lock 1: no pods are allowed", "done": lambda d, w: kc("get", "quota", "lock", "-n", "room5-gate",
                                                                            "-o", "jsonpath={.spec.hard.pods}", check=False) != "0",
              "hints": ["No pods? Look at the ReplicaSet events: `kubectl describe rs -n room5-gate`",
                        "Something limits the namespace: `kubectl get quota -n room5-gate`",
                        "`kubectl delete quota lock -n room5-gate`"]},
             {"name": "lock 2: the pod never gets Ready", "done": lambda d, w: kc(
                 "get", "deploy", "gate", "-n", "room5-gate", "-o",
                 "jsonpath={.spec.template.spec.containers[0].readinessProbe.httpGet.port}", check=False) == "80",
              "hints": ["Pods run but show 0/1? `kubectl describe pod -n room5-gate` and read the Events.",
                        "nginx listens on port 80. Which port does the readiness probe call?",
                        "`kubectl edit deploy gate -n room5-gate` and set readinessProbe port to 80."]},
         ]},
    ]}


# ---------------------------------------------------------------- GCLOUD world
def gconf_write(name, props):
    cp = configparser.ConfigParser()
    for sec, kv in props.items():
        cp[sec] = kv
    p = GCLOUD_CFG / "configurations" / f"config_{name}"
    with open(p, "w") as f:
        cp.write(f)


def gconf_read(name):
    cp = configparser.ConfigParser()
    cp.read(GCLOUD_CFG / "configurations" / f"config_{name}")
    return cp


def gactive():
    try:
        return (GCLOUD_CFG / "active_config").read_text().strip()
    except OSError:
        return "default"


def gcloud_setup(d, w):
    if GCLOUD_CFG.exists():
        shutil.rmtree(GCLOUD_CFG)
    (GCLOUD_CFG / "configurations").mkdir(parents=True)
    quiet = {"disable_usage_reporting": "True"}
    names = random.sample(WORDS, 9)
    keeper_cfg, answer_cfg = names[0], names[1]
    gconf_write("default", {"core": dict(quiet, account="intruder@shellventure.local", project="escape-trap")})
    # vault riddle: exactly one config has project *-vault AND an ops account
    gconf_write(answer_cfg, {"core": dict(quiet, account=f"ops-{random.choice(NAMES)}@shellventure.local",
                                          project=f"{random.choice(WORDS)}-vault")})
    gconf_write(names[2], {"core": dict(quiet, account=f"ops-{random.choice(NAMES)}@shellventure.local",
                                        project=f"{random.choice(WORDS)}-vaults")})
    gconf_write(names[3], {"core": dict(quiet, account=f"dev-{random.choice(NAMES)}@shellventure.local",
                                        project=f"{random.choice(WORDS)}-vault")})
    gconf_write(names[4], {"core": dict(quiet, account=f"{random.choice(NAMES)}-opsx@shellventure.local".replace("-opsx", ""),
                                        project=f"vault-{random.choice(WORDS)}")})
    for n in names[5:]:
        gconf_write(n, {"core": dict(quiet, account=f"{random.choice(NAMES)}@shellventure.local",
                                     project=f"{random.choice(WORDS)}-{random.choice(['dev', 'qa', 'lab'])}")})
    gconf_write(keeper_cfg, {"core": dict(quiet, account="keeper@shellventure.local", project="escape-castle"),
                             "proxy": {"type": "http", "address": "10.66.6.6", "port": "3128"},
                             "component_manager": {"disable_update_check": "True"}})
    (GCLOUD_CFG / "active_config").write_text("default")
    w["data"]["keeper"] = keeper_cfg
    w["answers"]["4"] = h(answer_cfg)
    (d / "README.txt").write_text("CLOUDSDK_CONFIG points to ./sdk in the game shell. Your real gcloud is untouched.\n")


def g_identity(d, w, _):
    a = gactive()
    acct = gconf_read(a).get("core", "account", fallback="")
    return acct == "keeper@shellventure.local", f"Active configuration is '{a}' with account '{acct}'."


def g_proxy(d, w, _):
    a = gactive()
    if a != w["data"]["keeper"]:
        return False, "Stay in the keeper's configuration."
    cp = gconf_read(a)
    left = [k for k in ("type", "address", "port") if cp.get("proxy", k, fallback=None)]
    return not left, f"Still set: proxy/{', proxy/'.join(left)}" if left else ""


def g_hatch(d, w, _):
    a = gactive()
    if a != "exit":
        return False, f"Active configuration is '{a}'. Want one named 'exit'."
    cp = gconf_read("exit")
    acct, proj = cp.get("core", "account", fallback=""), cp.get("core", "project", fallback="")
    if acct != "keeper@shellventure.local":
        return False, f"Account of 'exit' is '{acct}'."
    return proj == "escape-exit", f"Project of 'exit' is '{proj}'."


GCLOUD = {
    "title": "Cloud Tower", "needs": ["gcloud"], "dir": "gcloud", "setup": gcloud_setup, "rooms": [
        {"name": "The Wrong Identity", "check": g_identity,
         "story": "You woke up as [bold]intruder@shellventure.local[/]. The tower does not trust you.",
         "task": "Switch to the gcloud [bold]configuration[/] whose account is keeper@shellventure.local.\nThen: [cyan]check[/]",
         "hints": ["gcloud keeps many named configurations. List them.",
                   "`gcloud config configurations list`",
                   "`gcloud config configurations activate <name>`"]},
        {"name": "The Proxy Trap", "check": g_proxy,
         "story": "Every call from the keeper goes through a fake proxy at 10.66.6.6.",
         "task": "Remove [bold]all proxy settings[/] from the active configuration.\nThen: [cyan]check[/]",
         "hints": ["`gcloud config list` shows every property that is set.",
                   "There are 3 proxy properties.",
                   "`gcloud config unset proxy/type` (same for proxy/address and proxy/port)"]},
        {"name": "The Escape Hatch", "check": g_hatch,
         "story": "No door fits. Build your own: a fresh [bold]configuration[/].",
         "task": "Create and activate a configuration named [bold]exit[/] with account\n"
                 "keeper@shellventure.local and project [bold]escape-exit[/]. Then: [cyan]check[/]",
         "hints": ["Configurations can be created, not only activated.",
                   "`gcloud config configurations create exit`  (it becomes active)",
                   "`gcloud config set account keeper@shellventure.local` and `gcloud config set project escape-exit`"]},
        {"name": "The Filter Master", "answer": True,
         "story": "Nine configurations. One key. No scrolling allowed: use [bold]--filter[/].",
         "task": "Find the configuration whose project [bold]ends with -vault[/] AND whose account [bold]starts with ops-[/].\n"
                 "Its name is the key. Then: [cyan]check <name>[/]",
         "hints": ["`gcloud config configurations list --format=json` shows the field names.",
                   "Fields: properties.core.project and properties.core.account",
                   "`gcloud config configurations list --filter='properties.core.project~-vault$ AND properties.core.account~^ops-' --format='value(name)'`"]},
    ]}

WORLDS = {"bash": BASH, "git": GIT, "k8s": K8S, "gcloud": GCLOUD}


def load_plugins():
    """Extra worlds live in worlds/*.py; each has make(api) -> {key: world}."""
    import importlib.util
    for f in sorted((HERE / "worlds").glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"escape_world_{f.stem}", f)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        WORLDS.update(m.make(sys.modules[__name__]))
    order = ["bash", "git", "linux", "today", "mybugs", "cicd", "terraform", "observability", "security", "web", "k8s", "gcloud", "helm", "cka", "docker", "sql", "network", "incidents", "boss"]
    for k in sorted(WORLDS, key=lambda k: order.index(k) if k in order else 50):
        WORLDS[k] = WORLDS.pop(k)
    only = os.environ.get("SHELLVENTURE_WORLDS")  # e.g. "bash,git" on the phone
    if only:
        for k in [k for k in WORLDS if k not in only.split(",")]:
            del WORLDS[k]


load_plugins()


# ---------------------------------------------------------------- game engine
def world_state(s, key):
    return s["worlds"].setdefault(key, {"built": False, "room": 0, "hints": {}, "solved": [],
                                        "answers": {}, "data": {}, "start": None, "best": None})


def missing_tools(key):
    return [c for c in WORLDS[key].get("needs", []) if not shutil.which(c)]


def build(key, s):
    W, w = WORLDS[key], world_state(s, key)
    d = ROOT / W["dir"]
    if not W.get("kind") and d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    w.update(built=False, room=0, hints={}, solved=[], answers={}, data={}, start=None)
    if W.get("kind"):
        W["setup"](d, w)
    else:
        with con.status(f"[cyan]Building {W['title']}...", spinner="dots12"):
            W["setup"](d, w)
    w["built"] = True
    save(s)


def room_dir(key, i):
    W = WORLDS[key]
    r = W["rooms"][i]
    return ROOT / W["dir"] / r["dir"] if r.get("dir") else ROOT / W["dir"]


def show_room(key, s):
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    if i >= len(W["rooms"]):
        con.print(Panel(Align.center(f"[bold green]You escaped {W['title']}![/]  Best: {fmt_time(w['best'] or 0)}"),
                        box=box.DOUBLE, border_style="green"))
        return
    r = W["rooms"][i]
    dots = "".join("[green]━━[/]" if j < i else ("[yellow]━━[/]" if j == i else "[grey35]━━[/]")
                   for j in range(len(W["rooms"])))
    used = w["hints"].get(str(i + 1), 0)
    body = Group(
        Text.from_markup(f"[italic]{r['story']}[/]\n"),
        Text.from_markup(r["task"]),
        Text.from_markup(f"[grey50]ns:[/] {r['ns']}" if r.get("ns") else ""),
        Text.from_markup(f"\n[bold yellow]YOU NOW:[/] " + ("find the answer, then just [cyan]type it[/] and press Enter"
                         if r.get('answer') or r.get('typed') else "fix it with normal commands. [cyan]I check after every command[/]") + "\n"
                         f"[grey42]hint · room · exit[/]"),
    )
    con.print(Panel(body, title=f"[bold]{W['title']}[/]  room {i + 1}/{len(W['rooms'])}: [bold yellow]{r['name']}[/]",
                    subtitle=f"{dots}  {fmt_time(time.time() - (w['start'] or time.time()))}",
                    border_style="magenta", box=box.ROUNDED, padding=(1, 2)))


def door_animation():
    with Live(console=con, refresh_per_second=10, transient=True) as live:
        for f in DOOR:
            live.update(Align.center(Text(f, style="bold yellow")))
            time.sleep(0.35)
    con.print(Align.center(Text(DOOR[-1], style="bold green")))


def do_check(key, s, arg):
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    if not w["built"]:
        con.print(f"[yellow]World not built. Run: shellventure play {key}[/]")
        return
    if i >= len(W["rooms"]):
        return show_room(key, s)
    r = W["rooms"][i]
    w["start"] = w["start"] or time.time()
    if r.get("answer"):
        if not arg:
            con.print("[yellow]This room needs an answer:[/] check <answer>")
            return
        ok, msg = h(arg) == w["answers"][str(i + 1)], "Wrong answer. The door does not move."
    else:
        ok, msg = r["check"](ROOT / W["dir"], w, arg)
    if not ok:
        con.print(Panel(f"[bold red]❌ Still locked.[/]\n{msg}", border_style="red"))
        return
    used = w["hints"].get(str(i + 1), 0)
    dif = DIFF[settings(s)["difficulty"]]
    pts = max(round((15 - dif["hint_cost"] * used) * dif["mult"]), 3)
    w["solved"].append(i + 1)
    w["room"] += 1
    save(s)
    door_animation()
    con.print(Align.center(f"[bold green]{r['name']} OPENED![/]  +{pts} XP"))
    award(pts, f"escape {key}: {r['name']}", SKILL_OF.get(key, W.get("skill")))
    if w["room"] >= len(W["rooms"]):
        took = time.time() - w["start"]
        w["best"] = min(w["best"] or took, took)
        bonus = W["bonus"](took) if "bonus" in W else 25 + (10 if took < 8 * 60 * len(W["rooms"]) else 0)
        bonus = round(bonus * DIFF[settings(s)["difficulty"]]["mult"])
        w["escapes"] = w.get("escapes", 0) + 1
        w["last_hints"] = sum(w["hints"].values())
        w["last_time"] = took
        save(s)
        con.print(Panel(Align.center(Text.from_markup(
            f"[bold green]{BANNER}[/]\n\n[bold]You escaped {W['title']} in {fmt_time(took)}![/]\n"
            f"World bonus +{bonus} XP")), border_style="green", box=box.DOUBLE))
        award(bonus, f"escaped {W['title']}", SKILL_OF.get(key, W.get("skill")))
    else:
        con.print()
        show_room(key, s)
    check_badges(s)


# ---------------------------------------------------------------- badges
def _escaped(s, key):
    return s["worlds"].get(key, {}).get("escapes", 0) > 0


def _daily_streak(s, need):
    import datetime as dt
    days = sorted({dt.date.fromisoformat(d) for d in s.get("daily_log", [])})
    best = run = 0
    prev = None
    for d in days:
        nxt = prev + dt.timedelta(days=1) if prev else None
        while nxt and nxt.weekday() not in {int(x) for x in os.environ.get("SHELLVENTURE_WORKDAYS", "0,1,2,3,4").split(",")}:
            nxt += dt.timedelta(days=1)
        run = run + 1 if nxt == d else 1
        best, prev = max(best, run), d
    return best >= need


BADGES = [
    ("first_escape", "First Escape", "escape any world",
     lambda s: any(_escaped(s, k) for k in WORLDS)),
    ("no_hints", "No-Hint Run", "escape a world with zero hints",
     lambda s: any(w.get("escapes") and w.get("last_hints", 1) == 0 for w in s["worlds"].values())),
    ("speedrunner", "Speedrunner", "escape a world in under 2 min per room",
     lambda s: any(_escaped(s, k) and s["worlds"][k].get("best", 9e9) < 120 * len(W["rooms"]) for k, W in WORLDS.items())),
    ("bisect", "Bisect Master", "open The Bad Commit with no hints",
     lambda s: s["worlds"].get("git", {}).get("room", 0) >= 4 and s["worlds"]["git"].get("hints", {}).get("4", 0) == 0),
    ("survivor", "Incident Survivor", "escape the Incident Archive",
     lambda s: _escaped(s, "incidents")),
    ("polyglot", "Polyglot", "escape 4 different worlds",
     lambda s: sum(_escaped(s, k) for k in WORLDS if k != "boss") >= 4),
    ("legend", "Infra Legend", "escape every world",
     lambda s: all(_escaped(s, k) for k in WORLDS if k != "boss")),
    ("boss", "Boss Slayer", "beat the Thursday boss",
     lambda s: s.get("boss_thursday_win", False)),
    ("daily5", "Daily Five", "solve the daily puzzle 5 work days in a row",
     lambda s: _daily_streak(s, 5)),
]


def check_badges(s):
    s = load()  # pick up the latest saved state
    if _escaped(s, "boss") and WORLDS.get("boss") and s["worlds"]["boss"].get("last_time") is not None:
        import datetime as dt
        from zoneinfo import ZoneInfo
        if dt.datetime.now(dt.datetime.now().astimezone().tzinfo).weekday() == 3:
            s["boss_thursday_win"] = True
    have = set(s.setdefault("badges", []))
    for bid, name, how, test in BADGES:
        try:
            ok = bid not in have and test(s)
        except (KeyError, TypeError, ValueError):
            ok = False
        if ok:
            s["badges"].append(bid)
            con.print(Panel(Align.center(f"[bold yellow]★ NEW BADGE: {name} ★[/]\n[grey70]{how}[/]   +10 XP"),
                            border_style="yellow", box=box.HEAVY))
            award(10, f"badge: {name}")
    save(s)


def badge_line(s):
    have = set(s.get("badges", []))
    return "  ".join(f"[bold yellow]★ {n}[/]" if b in have else f"[grey35]☆ {n}[/]" for b, n, _h, _t in BADGES)


def room_steps(r, w):
    """A room with several problems lists them as steps: {"name", "done": fn(dir, w) -> bool, "hints": [...]}."""
    st = r.get("steps")
    return (st(w) if callable(st) else st) or []


def step_done(key, step, w):
    try:
        return bool(step["done"](ROOT / WORLDS[key]["dir"], w))
    except Exception:
        return False


def hints_left(key, s):
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    r, dif = W["rooms"][i], DIFF[settings(s)["difficulty"]]
    steps = room_steps(r, w)
    budget = dif["max_hints"] * len(steps) if steps else min(dif["max_hints"], len(r["hints"]))
    return max(budget - w["hints"].get(str(i + 1), 0), 0)


def give_hint(key, s, i, text, title):
    w = world_state(s, key)
    w["hints"][str(i + 1)] = w["hints"].get(str(i + 1), 0) + 1   # the room total: XP cost + "hints left"
    save(s)
    pretty = re.sub(r"`([^`]+)`", r"[bold cyan]\1[/]", escape_markup(text))
    cost = DIFF[settings(s)["difficulty"]]["hint_cost"]
    con.print(Panel(pretty, title=f"{title}  ({'free' if not cost else f'-{cost} XP'})", border_style="yellow"))


def do_hint(key, s):
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    if i >= len(W["rooms"]):
        return
    r, dif = W["rooms"][i], DIFF[settings(s)["difficulty"]]
    steps = room_steps(r, w)
    if steps:   # smart hints: skip what is already fixed, help with the first broken part only
        done = [step_done(key, st, w) for st in steps]
        for st, ok in zip(steps, done):
            if ok:
                con.print(f"[green]✔ already fixed:[/] {st['name']}")
        if all(done):
            con.print("[green]Every part looks fixed.[/] Type [cyan]check[/].")
            return
        k = done.index(False)
        used = w.setdefault("step_hints", {}).setdefault(str(i + 1), {})
        n = used.get(str(k), 0)
        if n >= min(dif["max_hints"], len(steps[k]["hints"])):
            con.print(f"[yellow]No more hints for this part ({steps[k]['name']}). You can do it.[/]")
            return
        used[str(k)] = n + 1
        give_hint(key, s, i, steps[k]["hints"][n], f"part {k + 1}/{len(steps)}: {steps[k]['name']} · hint {n + 1}/3")
        return
    n = w["hints"].get(str(i + 1), 0)
    hints = r["hints"]
    if n >= dif["max_hints"] and n < len(hints):
        con.print(f"[yellow]Hard mode: only {dif['max_hints']} hint per room. You can do it.[/]")
        return
    if n >= len(hints):
        con.print("[yellow]No more hints. The last one is the answer path. You can do it.[/]")
        return
    give_hint(key, s, i, hints[n], f"hint {n + 1}/3")


def show_map(s):
    con.print(Text(BANNER, style="bold magenta"))
    con.print(Align.center("[italic grey70]Break nothing real. Fix everything fake.[/]\n"))
    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    for c in ("world", "", "rooms", "progress", "best time", "play"):
        t.add_column(c)
    for key, W in WORLDS.items():
        w = s["worlds"].get(key, {})
        done = w.get("room", 0)
        n = len(W["rooms"])
        bar = progress(done, n)
        state = "" if done >= n else ("[yellow]in progress[/]" if w.get("start") else "")
        t.add_row(f"[bold]{key}[/]", W["title"], str(n), f"{bar} {state}",
                  fmt_time(w["best"]) if w.get("best") else "-", f"[cyan]shellventure play {key}[/]")
    con.print(Align.center(t))
    con.print(Panel(
        "[bold]1.[/] Pick a world and type its command, for example: [cyan]shellventure play bash[/]  (easiest)\n"
        "[bold]2.[/] You get a game shell. Read the room box: it says what is broken.\n"
        "[bold]3.[/] Fix it with your normal commands (ls, grep, git, kubectl...).\n"
        "[bold]4.[/] Type [cyan]check[/] (or [cyan]check <answer>[/]). Door opens = next room.\n"
        "[bold]5.[/] Stuck: [cyan]hint[/]  ·  show the room again: [cyan]room[/]  ·  leave (progress saved): [cyan]exit[/]\n"
        "[grey50]Quick 5-min puzzle instead: [/][cyan]shellventure daily[/]",
        title="[bold yellow]HOW TO PLAY[/]", border_style="yellow", padding=(0, 2)))
    con.print(Align.center("[grey50]badges:[/]"))
    con.print(Align.center(badge_line(s)))
    if XP.exists():
        con.print(Align.center(sh([sys.executable, "-I", str(XP), "status"], check=False).stdout.strip(), style="yellow"))


def status_line(key, s):
    """The thin bar above the prompt: world · room · time · hints left."""
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    if i >= len(W["rooms"]):
        return
    left = hints_left(key, s)
    took = fmt_time(time.time() - (w["start"] or time.time()))
    con.rule(f"[magenta]{W['title']}[/] [grey50]·[/] {i + 1}/{len(W['rooms'])} [bold]{W['rooms'][i]['name']}[/] "
             f"[grey50]·[/] {took} [grey50]·[/] hints left {left}", style="grey30")


PIN_ROWS, PIN_MIN = 3, 12   # pinned header height; below PIN_MIN terminal rows the old status bar is used


def pinned():
    return shutil.get_terminal_size((80, 24)).lines >= PIN_MIN


def pin_header(key, s, cols):
    """The 3 lines pinned at the top of the game shell: status, task in one line, a rule."""
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    if i >= len(W["rooms"]):
        return
    r = W["rooms"][i]
    left = hints_left(key, s)
    took = fmt_time(time.time() - (w["start"] or time.time()))
    task = " ".join(Text.from_markup(r["task"]).plain.split())
    out = Console(file=io.StringIO(), width=cols, force_terminal=True, color_system=con.color_system or "standard")
    out.print(Text.from_markup(f"[bold magenta]{W['title']}[/] [grey50]·[/] {i + 1}/{len(W['rooms'])} "
                               f"[bold yellow]{r['name']}[/] [grey50]·[/] {took} [grey50]·[/] hints {left}"),
              no_wrap=True, overflow="ellipsis")
    out.print(Text.assemble(("Task: ", "bold cyan"), task), no_wrap=True, overflow="ellipsis")
    out.print(Text("─" * cols, style="grey30"), no_wrap=True)
    sys.stdout.write(out.file.getvalue())


def autocheck(key, s):
    """After every command: fix-it rooms are checked quietly (door opens on success); then the status bar
    (only on small screens: bigger ones get the pinned header). Exit 10 = world finished."""
    rc = _autocheck(key, s)
    if rc != 10 and not pinned():
        status_line(key, load())
    return rc


def _autocheck(key, s):
    global AUTOCHECK
    W, w = WORLDS[key], world_state(s, key)
    i = w["room"]
    if not w["built"] or i >= len(W["rooms"]):
        return 10 if i >= len(W["rooms"]) else 0
    r = W["rooms"][i]
    if r.get("answer") or r.get("typed"):   # these wait for a typed answer
        return 0
    AUTOCHECK, con.quiet = True, True
    try:
        ok, _ = r["check"](ROOT / W["dir"], w, None)
    except Exception:
        ok = False
    finally:
        AUTOCHECK, con.quiet = False, False
    if ok:
        do_check(key, s, None)        # full check + door + XP + next room
    return 10 if world_state(load(), key)["room"] >= len(W["rooms"]) else 0


def play(key, s):
    W, w = WORLDS[key], world_state(s, key)
    miss = missing_tools(key)
    if miss:
        con.print(Panel(f"[yellow]{W['title']} needs: [bold]{', '.join(miss)}[/][/]\nInstall them, then play again.",
                        border_style="yellow"))
        if sys.stdin.isatty():
            con.print("[grey50](press a key)[/]"); getkey()
        return
    s["last"] = key  # menu "Continue" also works after `play <world>` from the command line
    if not w["built"]:
        build(key, s)
    if W.get("refresh"):  # e.g. My Bugs: rooms for bug files added after the world was built
        W["refresh"](ROOT / W["dir"], w)
    if w["room"] >= len(W["rooms"]):
        con.print(f"[green]You already escaped {W['title']}.[/] Play again with: shellventure reset {key}")
        return
    if not w["start"]:
        w["start"] = time.time()
    s["active"] = key
    save(s)
    con.clear()
    if pinned():
        con.print("\n" * (PIN_ROWS - 1))   # these rows become the pinned header at the first prompt
    else:
        con.print(Align.center(Text(BANNER, style="bold magenta") if con.width >= 56 else SMALL_BANNER))
    if settings(s).get("story") and key in STORY and w["room"] == 0:
        con.print(Panel(f"[italic]{STORY[key]}[/]", title="[bold]story[/]", border_style="cyan", padding=(0, 2)))
    show_room(key, s)
    env = dict(os.environ, SHELLVENTURE_WORLD=key)
    if W.get("kind"):
        env["KUBECONFIG"] = str(KUBECONFIG)
    if key == "gcloud":
        env["CLOUDSDK_CONFIG"] = str(GCLOUD_CFG)
    if key == "git":
        env.update(GIT_ENV)
    rc = ROOT / ".escape-rc"
    me = f"{sys.executable} {Path(__file__).resolve()}"
    rc.write_text(f"""
[ -f ~/.bashrc ] && . ~/.bashrc
check() {{ {me} _check "$@"; cd "$({me} _dir)" 2>/dev/null; }}
answer() {{ check "$@"; }}
hint() {{ {me} _hint; }}
room() {{ {me} _room; }}
map() {{ {me}; }}
alias k=kubectl
_esc_ps1() {{ {me} _ps1 2>/dev/null; }}
PS1='\\[\\e[1;35m\\]❯\\[\\e[0m\\] '
# after every command: quick automatic check; world finished -> back to the menu
# pinned header: rows 1-{PIN_ROWS} stay, everything else scrolls below them (re-set every prompt: clear/less/k9s reset it)
_esc_pin() {{
  local rows=$(tput lines) cols=$(tput cols) r=0 c=1 hdr
  (( rows < {PIN_MIN} )) && {{ printf '\\e[r'; return; }}
  printf '\\e[6n' >/dev/tty; IFS='[;' read -rs -t 0.3 -d R _ r c </dev/tty   # ask the terminal: cursor row;col
  hdr=$({me} _pin "$cols")
  printf '\\e[{PIN_ROWS + 1};%dr\\e[1;1H' "$rows"
  while IFS= read -r line; do printf '\\e[2K%s\n' "$line"; done <<< "$hdr"
  (( r <= {PIN_ROWS} )) && r={PIN_ROWS + 1} c=1
  printf '\\e[%d;%dH' "$r" "$c"
}}
_esc_auto() {{ local rc=$?; {me} _autocheck; [ $? = 10 ] && {{ sleep 2; exit; }}; cd "$({me} _dir)" 2>/dev/null; _esc_pin; return $rc; }}
PROMPT_COMMAND=_esc_auto
# typing something that is not a command = an answer attempt
# runs in a SUBSHELL (bash rule): it checks the answer; _esc_auto (PROMPT_COMMAND) then moves on or exits
command_not_found_handle() {{ {me} _typed "$@"; return 0; }}
cd "{room_dir(key, w['room'])}"
""")
    subprocess.call(["bash", "--rcfile", str(rc), "-i"], env=env)
    sys.stdout.write("\033[r\033[2J\033[H"); sys.stdout.flush()   # undo the pinned header's scroll region
    s = load()
    s["active"] = None
    save(s)
    con.print("[magenta]You left the lab. Your progress is saved.[/] Back with: shellventure play " + key)


def getkey():
    """One key press, no Enter. Arrows come back as 'up'/'down'/'left'/'right', Enter as 'enter'."""
    if not sys.stdin.isatty():
        c = (sys.stdin.readline() or "q").strip()
        return c[:1] if c else "enter"
    import termios, tty, select
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        c = os.read(fd, 1).decode(errors="ignore")
        if c == "\x1b" and select.select([fd], [], [], 0.05)[0]:
            seq = os.read(fd, 2).decode(errors="ignore")
            return {"[A": "up", "[B": "down", "[C": "right", "[D": "left", "OA": "up", "OB": "down"}.get(seq, "esc")
        return {"\r": "enter", "\n": "enter", "\x1b": "esc", "\x04": "q"}.get(c, c)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


DIFF = {"easy": {"mult": 0.5, "hint_cost": 0, "max_hints": 3}, "normal": {"mult": 1.0, "hint_cost": 5, "max_hints": 3},
        "hard": {"mult": 1.5, "hint_cost": 5, "max_hints": 1}}
CAMPAIGN = ["bash", "linux", "git", "cicd", "docker", "k8s", "helm", "cka", "terraform", "observability", "web",
            "security", "sql", "network", "gcloud", "today", "boss"]
STORY = {
    "cka": "Week 3. Your lead says: pass the CKA by Friday. The practice cluster is already broken in six places.",
    "bash": "Monday 08:55. Your first day as an SRE. The laptop boots, the on-call phone buzzes: 'logs are full of junk, find the key'.",
    "linux": "Monday 14:00. A server is slow and the disk is almost full. Your team lead: 'you have ssh, go'.",
    "git": "Tuesday 09:30. Someone force-deleted a branch and a password leaked into history. Git remembers everything.",
    "cicd": "Tuesday 15:00. The pipeline is red and nobody knows why jobs are skipped. Welcome to CI.",
    "docker": "Wednesday 10:00. The image is 64 MB too big and the container says 'unhealthy'. Time to read Dockerfiles.",
    "k8s": "Wednesday 16:00. Pods crash, services are empty, a monster eats memory. Your first real cluster day.",
    "helm": "Thursday 09:00. A release failed mid-upgrade. Helm history is your friend.",
    "terraform": "Thursday 13:00. The plan says '1 to destroy'. Before anyone types yes: what dies?",
    "observability": "Thursday 23:40. 40 pages tonight. Make the alerts make sense.",
    "web": "Friday 09:10. The site returns the wrong page for some hosts. nginx has opinions.",
    "security": "Friday 11:00. The security audit is today. A key leaked, a role is too powerful.",
    "sql": "Friday 14:00. Payments are slow and a lock holds everything. Open psql.",
    "network": "Friday 16:00. DNS, certificates, a radio on a secret port. The network maze.",
    "gcloud": "Friday 17:30. Wrong identity, a fake proxy. The cloud tower before the weekend.",
    "today": "Saturday. Real bugs from real people. No hints from the story now.",
    "boss": "Sunday night. Three things break at once. The boss fight. Good luck, SRE.",
}


def settings(s):
    return s.setdefault("settings", {"difficulty": "normal", "story": False})


def campaign_keys():
    return [k for k in CAMPAIGN if k in WORLDS]


def locked(s, key):
    """Story mode: a world opens when the previous one in the campaign was escaped."""
    if not settings(s).get("story") or key not in CAMPAIGN:
        return False
    keys = campaign_keys()
    i = keys.index(key)
    return i > 0 and not s["worlds"].get(keys[i - 1], {}).get("escapes")


SMALL_BANNER = "[bold magenta]▓▒░ S H E L L V E N T U R E ░▒▓[/]"


def daily_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("escape_daily", HERE / "daily.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def daily_shell(s):
    """Daily puzzle in a game shell: type the answer, it is checked; solved -> back to the menu."""
    d = daily_mod(); st = d.get_today(sys.modules[__name__], s)
    if not st["start"] and not st["solved"]:
        st["start"] = time.time(); save(s)
    con.clear(); d.show(sys.modules[__name__], st)
    if st["solved"]:
        con.print("[grey50](press a key)[/]"); getkey(); return
    me = f"{sys.executable} {Path(__file__).resolve()}"
    rc = ROOT / ".escape-daily-rc"
    rc.write_text(f"""
[ -f ~/.bashrc ] && . ~/.bashrc
hint() {{ {me} daily hint; }}
check() {{ {me} _dtyped "$@"; return 0; }}
room() {{ {me} daily; }}
# runs in a SUBSHELL (bash rule): it can check, but cannot exit this shell. PROMPT_COMMAND does the exit.
command_not_found_handle() {{ check "$@"; }}
_esc_daily_done() {{ {me} _dailydone && {{ sleep 2; exit; }}; }}
PROMPT_COMMAND=_esc_daily_done
PS1='\\[\\e[1;36m\\][DAILY]\\[\\e[0m\\] \\w \\$ '
cd "{st['dir']}"
""")
    subprocess.call(["bash", "--rcfile", str(rc), "-i"], env=dict(os.environ))


GROUPS = [("Foundations", ["bash", "linux", "git", "today"]),
          ("Delivery", ["cicd", "docker", "terraform"]),
          ("Kubernetes", ["k8s", "helm", "cka", "boss"]),
          ("Operations", ["network", "sql", "web", "security", "observability", "gcloud", "incidents", "mybugs"])]


def pick(title, rows, sel=0, header=None):
    """Clean one-column list. rows = [(label, right_text, value)]. Arrows + Enter, number keys, Esc/q = back.
    Returns the chosen value, or None for back."""
    while True:
        con.clear()
        con.print(Align.center(Text(BANNER, style="bold magenta") if con.width >= 56 else SMALL_BANNER))
        if header:
            con.print(Align.center(header))
        con.print()
        if title:
            con.print(Align.center(f"[bold grey62]{title}[/]\n"))
        t = Table(box=None, show_header=False, padding=(0, 1))
        t.add_column(width=2); t.add_column(width=2, style="grey42"); t.add_column(min_width=16); t.add_column(style="grey62")
        for i, (label, right, _v) in enumerate(rows):
            on = i == sel
            t.add_row("[bold magenta]▶[/]" if on else "", str(i + 1) if i < 9 else "",
                      f"[bold reverse] {label} [/]" if on else f" {label} ", right or "")
        con.print(Align.center(t))
        con.print(Align.center("\n[grey42]↑ ↓ Enter · Esc back[/]"))
        k = getkey()
        if k in ("esc", "q", "Q", "left"):
            return None
        if k == "up":
            sel = (sel - 1) % len(rows)
        elif k == "down":
            sel = (sel + 1) % len(rows)
        elif k in ("enter", "right"):
            return rows[sel][2]
        elif len(k) == 1 and k.isdigit() and 1 <= int(k) <= min(len(rows), 9):
            return rows[int(k) - 1][2]


def world_line(s, key):
    W = WORLDS[key]; w = s["worlds"].get(key, {}); n = len(W["rooms"]); done = min(w.get("room", 0), n)
    if missing_tools(key):
        return f"[grey35]needs {', '.join(missing_tools(key))}[/]"
    if locked(s, key):
        return "[grey35]locked[/]"
    return progress(done, n)


def play_world(key):
    s = load(); W = WORLDS[key]; w = world_state(s, key)
    if locked(s, key):
        prev = campaign_keys()[campaign_keys().index(key) - 1]
        con.print(Align.center(f"\n[yellow]Locked. Finish {WORLDS[prev]['title']} first.[/] (press a key)")); getkey(); return
    s["last"] = key; save(s)
    if w.get("built") and w["room"] >= len(W["rooms"]):
        con.print(Align.center(f"\n[green]You escaped {W['title']}.[/] Play again with new puzzles? [bold]y[/]/n"))
        if getkey().lower() != "y":
            return
        build(key, load())
    play(key, load())


def worlds_menu():
    while True:
        s = load()
        if settings(s).get("story"):   # story mode: one list, in campaign order
            keys = campaign_keys() + [k for k in WORLDS if k not in CAMPAIGN]
            v = pick("First week as SRE", [(WORLDS[k]["title"], world_line(s, k), k) for k in keys])
            if v is None:
                return
            play_world(v); continue
        groups = [(g, [k for k in ks if k in WORLDS]) for g, ks in GROUPS]
        groups = [(g, ks) for g, ks in groups if ks]
        rest = [k for k in WORLDS if all(k not in ks for _, ks in groups)]
        if rest:
            groups.append(("More", rest))
        rows = []
        for g, ks in groups:
            done = sum(1 for k in ks if s["worlds"].get(k, {}).get("escapes"))
            rows.append((g, f"{done}/{len(ks)} escaped", g))
        g = pick("Worlds", rows)
        if g is None:
            return
        ks = dict(groups)[g]
        while True:
            s = load()
            v = pick(g, [(WORLDS[k]["title"], world_line(s, k), k) for k in ks])
            if v is None:
                break
            play_world(v)


def settings_menu():
    while True:
        s = load(); cfg = settings(s)
        v = pick("Settings", [("Difficulty", f"[bold]{cfg['difficulty']}[/]  easy · normal · hard", "d"),
                              ("Story mode", f"[bold]{'on' if cfg.get('story') else 'off'}[/]  First week as SRE", "s")])
        if v is None:
            return
        if v == "d":
            cfg["difficulty"] = {"easy": "normal", "normal": "hard", "hard": "easy"}[cfg["difficulty"]]
        else:
            cfg["story"] = not cfg.get("story")
        save(s)


def menu():
    """Main screen: 6 lines. Everything else is one level down."""
    while True:
        s = load(); cfg = settings(s)
        st = s.get("daily", {})
        dsolved = st.get("day") == time.strftime("%Y-%m-%d") and st.get("solved")
        escaped = sum(1 for k in WORLDS if s["worlds"].get(k, {}).get("escapes"))
        header = ""
        if XP.exists():
            try:
                pr = json.loads(sh([sys.executable, "-I", str(XP), "profile"], check=False).stdout)
                header = f"[yellow]Lv{pr['level']} {pr['title']}[/] [grey50]·[/] {pr['xp']} xp [grey50]·[/] streak {pr['streak']}d"
            except ValueError:
                pass
        rows = []
        last = s.get("last")
        if last in WORLDS:
            w = s["worlds"].get(last, {}); n = len(WORLDS[last]["rooms"])
            if w.get("room", 0) < n:
                rows.append(("Continue", f"{WORLDS[last]['title']} · room {w.get('room', 0) + 1}/{n}", "continue"))
        rows += [("Daily", "[green]done today[/]" if dsolved else "5 min · +10 XP", "daily"),
                 ("Worlds", f"{escaped} of {len(WORLDS)} escaped", "worlds"),
                 ("Profile", "", "profile"),
                 ("Settings", f"{cfg['difficulty']} · story {'on' if cfg.get('story') else 'off'}", "settings"),
                 ("Quit", "", "quit")]
        v = pick(None, rows, header=header)
        if v in (None, "quit"):
            con.clear(); return 0
        if v == "continue":
            play_world(last)
        elif v == "daily":
            daily_shell(load())
        elif v == "worlds":
            worlds_menu()
        elif v == "profile":
            show_profile()
        elif v == "settings":
            settings_menu()


def main(argv):
    s = load()
    if len(argv) == 1 and sys.stdin.isatty() and sys.stdout.isatty():
        return menu()
    cmd = argv[1] if len(argv) > 1 else "map"
    key = os.environ.get("SHELLVENTURE_WORLD")
    if cmd == "map":
        show_map(s)
    elif cmd == "play" and len(argv) > 2 and argv[2] in WORLDS:
        play(argv[2], s)
    elif cmd == "reset" and len(argv) > 2 and argv[2] in WORLDS:
        build(argv[2], s)
        con.print(f"[green]{WORLDS[argv[2]]['title']} rebuilt with new puzzles.[/] Play: shellventure play {argv[2]}")
    elif cmd == "stop":
        sh(["kind", "delete", "cluster", "--name", KIND_NAME], check=False)
        sh(["docker", "rm", "-f", "shellventure-pg", "shellventure-web", "shellventure-health"], check=False)
        for k, W in WORLDS.items():
            if W.get("kind") or k in ("sql", "docker"):
                s["worlds"].pop(k, None)
        save(s)
        con.print(f"[green]kind cluster '{KIND_NAME}' deleted.[/]")
    elif cmd in ("daily", "_daily_banner"):
        import importlib.util
        spec = importlib.util.spec_from_file_location("escape_daily", HERE / "daily.py")
        daily = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(daily)
        if cmd == "daily":
            daily.main(sys.modules[__name__], s, argv[2:])
        else:
            daily.banner(sys.modules[__name__], s)
    elif cmd == "_check" and key:
        do_check(key, s, " ".join(argv[2:]))
    elif cmd == "_autocheck" and key:  # after every command: quick silent look at a fix-it room
        return autocheck(key, s)
    elif cmd == "_typed" and key:      # unknown command typed in the game shell = an answer attempt
        W, w = WORLDS[key], world_state(s, key)
        if w["room"] < len(W["rooms"]) and (W["rooms"][w["room"]].get("answer") or W["rooms"][w["room"]].get("typed")):
            do_check(key, s, " ".join(argv[2:]))
        else:
            con.print(f"[grey50]{argv[2] if len(argv) > 2 else ''}: command not found[/]")
        return 10 if world_state(load(), key)["room"] >= len(W["rooms"]) else 0
    elif cmd == "_dailydone":          # exit 0 = today's daily is solved
        st = load().get("daily", {})
        return 0 if st.get("solved") and st.get("day") == time.strftime("%Y-%m-%d") else 1
    elif cmd == "_dtyped":             # daily puzzle shell: typed text = answer
        argv2 = ["daily", "check", *argv[2:]]
        return main([argv[0], *argv2]) or (10 if load().get("daily", {}).get("solved") else 0)
    elif cmd == "_hint" and key:
        do_hint(key, s)
    elif cmd == "_room" and key:
        show_room(key, s)
    elif cmd == "_dir" and key:
        print(room_dir(key, min(world_state(s, key)["room"], len(WORLDS[key]["rooms"]) - 1)))
    elif cmd == "_pin" and key:
        pin_header(key, s, int(argv[2]) if len(argv) > 2 else shutil.get_terminal_size().columns)
    elif cmd == "_ps1" and key:
        w = world_state(s, key)
        print(f"{key} {min(w['room'] + 1, len(WORLDS[key]['rooms']))}/{len(WORLDS[key]['rooms'])}", end="")
    else:
        con.print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:      # Ctrl+C: leave quietly, no traceback
        con.show_cursor(True)
        con.print("\n[magenta]Bye. Your progress is saved.[/]")
        sys.exit(130)
