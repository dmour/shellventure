"""Daily puzzle: one small offline puzzle per work day, same puzzle all day.

  shellventure daily              show today's puzzle (builds it the first time)
  shellventure daily check <ans>  answer it
  shellventure daily hint         one hint (-3 XP)
"""
import base64, datetime as dt, ipaddress, json, random, re, time
from zoneinfo import ZoneInfo

TZ = dt.datetime.now().astimezone().tzinfo
WORK_DAYS = {6, 0, 1, 2, 3}  # Sun..Thu


def today():
    return dt.datetime.now(TZ).date()


# ---------------------------------------------------------------- generators
# Each returns dict(title, task, answer (str or list of accepted), hints). May write files into d.

def p_hidden(api, d, rnd):
    real = api.code()
    for i in range(120):
        p = d / f"dir{rnd.randint(1, 6)}" / f"f{i}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"KEY={api.code()}\n" if i % 7 == 0 else "nothing\n")
    (d / f"dir{rnd.randint(1, 6)}" / ".real").write_text(f"KEY={real}\n")
    return dict(title="Hidden Key", answer=real,
                task="In this folder, the real KEY is in a hidden file. The others are fake.",
                hints=["`find . -name '.*' -type f`", "`find . -name '.*' -type f -exec cat {} +`"])


def p_count(api, d, rnd):
    svcs = ["orders", "billing", "search", "auth", "gateway"]
    target = rnd.choice(svcs)
    n = 0
    with open(d / "app.log", "w") as f:
        for i in range(2000):
            s, lvl = rnd.choice(svcs), rnd.choice(["INFO", "INFO", "WARN", "ERROR", "DEBUG"])
            if s == target and lvl == "ERROR":
                n += 1
            f.write(f"2026-10-29T09:{i // 60 % 60:02d}:{i % 60:02d} {lvl:<5} [{s}] request {rnd.randint(1000, 9999)}\n")
    return dict(title="Error Count", answer=str(n),
                task=f"How many [bold]ERROR[/] lines from service [bold]{target}[/] are in app.log?",
                hints=["Match both words on the same line.", f"`grep 'ERROR' app.log | grep -c '\\[{target}\\]'`"])


def p_secret(api, d, rnd):
    pw = f"{rnd.choice(['Petra', 'Wadi', 'Aqaba', 'Jerash'])}#{rnd.randint(1000, 9999)}"
    enc = base64.b64encode(pw.encode()).decode()
    (d / "secret.yaml").write_text(
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: db-creds\ntype: Opaque\ndata:\n"
        f"  username: {base64.b64encode(b'APPUSER').decode()}\n  password: {enc}\n")
    return dict(title="Secret Decoder", answer=pw, case=True,
                task="What is the database [bold]password[/] in secret.yaml?",
                hints=["Secret data is base64, not encrypted.", "`grep password secret.yaml | awk '{print $2}' | base64 -d`"])


def p_cidr(api, d, rnd):
    pre = rnd.choice([22, 23, 24, 25, 26, 27, 28, 29])
    net = ipaddress.ip_network(f"10.{rnd.randint(0, 255)}.{rnd.randint(0, 255)}.0/{pre}", strict=False)
    return dict(title="Subnet Math", answer=str(net.num_addresses - 2),
                task=f"How many [bold]usable host IPs[/] are in [bold]{net}[/]?\n(Normal network: not counting network and broadcast.)",
                hints=["Size = 2^(32 - prefix).", "Usable = size - 2."])


def p_cron(api, d, rnd):
    q = rnd.choice([
        ("Sun to Thu at 9:30 AM", ["30 9 * * 0-4", "30 9 * * sun-thu", "30 9 * * 0,1,2,3,4"]),
        ("every 15 minutes", ["*/15 * * * *", "0,15,30,45 * * * *"]),
        ("every Friday at 8 PM", ["0 20 * * 5", "0 20 * * fri"]),
        ("at 4:30 AM on the 1st of every month", ["30 4 1 * *"]),
        ("every hour, at minute 5, only on weekdays Sun-Thu", ["5 * * * 0-4", "5 * * * sun-thu"]),
    ])
    return dict(title="Cron Riddle", answer=q[1],
                task=f"Write the cron expression for: [bold]{q[0]}[/]\nAnswer with quotes: shellventure daily check \"m h dom mon dow\"",
                hints=["Order: minute hour day-of-month month day-of-week. Sunday = 0.",
                       "Use a range like 0-4 or a step like */15."])


def p_comm(api, d, rnd):
    names = [f"{rnd.choice(['orders', 'billing', 'search', 'auth', 'gateway'])}-{rnd.randint(10, 400)}" for _ in range(90)]
    names = sorted(set(names))
    a = rnd.sample(names, int(len(names) * .7))
    b = rnd.sample(names, int(len(names) * .6))
    rnd.shuffle(a); rnd.shuffle(b)
    (d / "cluster-a.txt").write_text("\n".join(a) + "\n")
    (d / "cluster-b.txt").write_text("\n".join(b) + "\n")
    return dict(title="Namespace Diff", answer=str(len(set(a) - set(b))),
                task="How many namespaces are in [bold]cluster-a.txt[/] but [bold]not[/] in cluster-b.txt?",
                hints=["`comm` needs sorted input.", "`comm -23 <(sort cluster-a.txt) <(sort cluster-b.txt) | wc -l`"])


def p_gitlog(api, d, rnd):
    real = api.code()
    api.git(d, "init", "-q", "-b", "main")
    at = rnd.randint(4, 12)
    for i in range(16):
        (d / "values.yaml").write_text(f"replicas: {rnd.randint(1, 3)}\n" + (f"dbPassword: {real}\n" if i == at else ""))
        api.git(d, "add", "-A")
        api.git(d, "commit", "-q", "--allow-empty", "-m", "tune values", who=rnd.choice(api.NAMES))
    return dict(title="Leaked Password", answer=real,
                task="Someone committed a [bold]dbPassword[/] to values.yaml, then removed it. What was it?",
                hints=["Search the history, not the file.", "`git log -S dbPassword -p`"])


def p_jq(api, d, rnd):
    pods = []
    for i in range(30):
        pods.append({"metadata": {"name": f"pod-{api.code()}", "namespace": rnd.choice(["orders", "billing", "search"])},
                     "status": {"phase": rnd.choice(["Running", "Running", "Pending", "Failed"]),
                                "restarts": rnd.randint(0, 3)}})
    worst = rnd.randrange(30)
    pods[worst]["status"].update(phase="Running", restarts=rnd.randint(40, 90))
    (d / "pods.json").write_text(json.dumps({"items": pods}, indent=1))
    return dict(title="Restart King", answer=pods[worst]["metadata"]["name"],
                task="In pods.json, which pod has the [bold]most restarts[/]? Answer its name.",
                hints=["`jq '.items | sort_by(.status.restarts)'`",
                       "`jq -r '.items | max_by(.status.restarts) | .metadata.name' pods.json`"])


PUZZLES = [p_hidden, p_count, p_secret, p_cidr, p_cron, p_comm, p_gitlog, p_jq]


# ---------------------------------------------------------------- engine
def norm(s, case=False):
    s = re.sub(r"\s+", " ", s.strip())
    return s if case else s.lower()


def get_today(api, s):
    day = today().isoformat()
    st = s.setdefault("daily", {})
    if st.get("day") != day:
        d = api.ROOT / "daily" / day
        if d.exists():
            api.shutil.rmtree(d)
        d.mkdir(parents=True)
        idx = today().toordinal()
        rnd = random.Random(idx)
        gen = PUZZLES[idx % len(PUZZLES)]
        p = gen(api, d, rnd)
        ans = p["answer"] if isinstance(p["answer"], list) else [p["answer"]]
        st.clear()
        st.update(day=day, title=p["title"], task=p["task"], hints=p["hints"], case=p.get("case", False),
                  answers=[api.h(norm(a, p.get("case")).lower()) for a in ans],
                  dir=str(d), start=None, hints_used=0, solved=False, banner=st.get("banner"))
        api.save(s)
    return st


def show(api, st):
    from rich.panel import Panel
    if st["solved"]:
        body = f"[bold green]✅ Solved today.[/] Come back tomorrow{' (Sunday)' if today().weekday() == 3 else ''}."
    else:
        where = st["dir"].replace(str(api.Path.home()), "~")
        body = (f"[bold]Puzzle:[/] {st['task']}\n\n"
                f"[bold yellow]HOW TO PLAY[/]\n"
                f"  [bold]1.[/] Go to the folder:   [cyan]cd {where}[/]\n"
                f"  [bold]2.[/] Look around:        [cyan]ls -la[/]  and use your normal commands\n"
                f"  [bold]3.[/] Found it? Answer:   [cyan]shellventure daily check <your answer>[/]\n"
                f"  [bold]4.[/] Stuck? Get a hint:  [cyan]shellventure daily hint[/]  (-3 XP)\n\n"
                f"[grey50]Wrong answers cost nothing. Solve in under 5 min for +5 bonus XP.[/]")
    api.con.print(Panel(body, title=f"[bold]Daily Puzzle {st['day']}[/]: [yellow]{st['title']}[/]",
                        border_style="cyan", padding=(1, 2)))


def main(api, s, args):
    st = get_today(api, s)
    if not st["start"] and not st["solved"]:
        st["start"] = time.time()
        api.save(s)
    if not args:
        return show(api, st)
    if args[0] == "hint":
        if st["hints_used"] >= len(st["hints"]):
            api.con.print("[yellow]No more hints.[/]")
            return
        st["hints_used"] += 1
        api.save(s)
        api.con.print(f"[yellow]hint {st['hints_used']}/{len(st['hints'])}:[/] " +
                      re.sub(r"`([^`]+)`", r"[bold cyan]\1[/]", api.escape_markup(st["hints"][st["hints_used"] - 1])))
        return
    if args[0] == "check":
        if st["solved"]:
            return show(api, st)
        guess = norm(" ".join(args[1:]), st["case"])
        if api.h(guess.lower()) not in st["answers"]:
            api.con.print("[bold red]❌ Not this one.[/] Try again (no penalty).")
            return
        took = time.time() - (st["start"] or time.time())
        pts = max(10 - 3 * st["hints_used"], 2) + (5 if took < 300 else 0)
        st["solved"] = True
        s.setdefault("daily_log", []).append(st["day"])
        api.save(s)
        api.con.print(f"[bold green]✅ Daily puzzle solved in {api.fmt_time(took)}![/] +{pts} XP")
        api.award(pts, f"daily puzzle: {st['title']}")
        api.check_badges(s)
        return
    api.con.print(__doc__)


def banner(api, s):
    """One line, once a day, on work days after 9 AM, until solved. Must stay fast and quiet."""
    now = dt.datetime.now(TZ)
    st = s.get("daily", {})
    if now.weekday() not in WORK_DAYS or now.hour < 9:
        return
    day = now.date().isoformat()
    if st.get("banner") == day or (st.get("day") == day and st.get("solved")):
        return
    st["banner"] = day
    s["daily"] = st
    api.save(s)
    print("\033[1;36m⏳ Daily puzzle ready (5 min, +10 XP):\033[0m shellventure daily")
