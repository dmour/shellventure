"""Boss Fight: one namespace, 3 random faults at once, timer. Full XP on Thursdays, practice XP other days."""
import datetime as dt, json, random
from zoneinfo import ZoneInfo

NS = "boss"
FAULTS = {
    "image": "image tag",
    "secret": "secret key",
    "probe": "readiness probe",
    "selector": "service selector",
    "quota": "resource quota",
    "memory": "memory limit",
}


def is_thursday():
    return dt.datetime.now().weekday() == 3


def make(api):
    kc = api.kc

    def setup(d, w):
        with api.con.status("[cyan]Summoning the boss (kind, about 1 minute)...", spinner="dots12"):
            api.kind_up()
            kc("delete", "ns", NS, "--ignore-not-found", "--wait=true")
            kc("create", "ns", NS)
            faults = random.sample(sorted(FAULTS), 3)
            w["data"]["faults"] = faults
            c = {"image": "nginx:1.27-alpine" + ("-x" if "image" in faults else ""),
                 "ports": [{"containerPort": 80}],
                 "env": [{"name": "API_TOKEN", "valueFrom": {"secretKeyRef": {"name": "boss-secret", "key": "token"}}}],
                 "readinessProbe": {"httpGet": {"path": "/", "port": 8080 if "probe" in faults else 80}, "periodSeconds": 2},
                 "resources": {"limits": {"memory": "2Mi" if "memory" in faults else "64Mi"}}}
            items = [{"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "boss-secret", "namespace": NS},
                      "stringData": {"tok" if "secret" in faults else "token": "s3cret"}},
                     api.deploy(NS, "boss-app", c),
                     {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "boss", "namespace": NS},
                      "spec": {"selector": {"app": "boss-ap" if "selector" in faults else "boss-app"}, "ports": [{"port": 80}]}}]
            if "quota" in faults:
                items.insert(0, {"apiVersion": "v1", "kind": "ResourceQuota", "metadata": {"name": "lock", "namespace": NS},
                                 "spec": {"hard": {"pods": "0"}}})
            kc("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}))
            (d / "README.txt").parent.mkdir(parents=True, exist_ok=True)
            (d / "README.txt").write_text("Boss namespace: boss\n")

    def check(d, w, _):
        with api.con.status("[cyan]The boss is watching...", spinner="dots12"):
            try:
                dep = json.loads(kc("get", "deploy", "boss-app", "-n", NS, "-o", "json"))
                c = dep["spec"]["template"]["spec"]["containers"][0]
            except (RuntimeError, ValueError, KeyError, IndexError):
                return False, "deploy/boss-app must exist."
            if not c.get("readinessProbe") or not c["image"].startswith("nginx:"):
                return False, "No cheating: keep nginx and a readiness probe."
            if not any(e.get("name") == "API_TOKEN" for e in c.get("env", [])):
                return False, "No cheating: the app still needs API_TOKEN from the secret."
            ep = kc("get", "endpoints", "boss", "-n", NS, "-o", "json", check=False)
            if not ep or not any(s.get("addresses") for s in json.loads(ep).get("subsets", [])):
                return False, "Service 'boss' has no endpoints. The boss still stands."
            return api.ready(NS, "boss-app"), "deploy/boss-app is not Ready yet."

    def bonus(took):
        if not is_thursday():
            return 10
        return 50 + (25 if took < 15 * 60 else 0)

    return {"boss": {
        "title": "Boss Fight", "needs": ["kind", "docker", "kubectl"], "dir": "boss", "setup": setup, "kind": True, "bonus": bonus, "rooms": [
            {"name": "The Three-Headed Deploy", "check": check,
             "story": "Namespace [bold]boss[/]. [bold]Three[/] things are broken at once. Each fix shows the next head.\n"
                      "Thursday = 50 XP (+25 under 15 min). Other days = practice (10 XP). New faults each reset.",
             "task": "Make deploy/boss-app Ready and Service [bold]boss[/] send traffic to it.\nThen: [cyan]check[/]",
             "hints": ["Start wide: `kubectl get all,quota,secret -n boss` and `kubectl get events -n boss --sort-by=.lastTimestamp`",
                       "The 6 usual suspects: image tag, secret key, readiness probe port, service selector, quota, memory limit.",
                       "Fix one, wait 10 seconds, look again. The next head shows only after the first falls."]},
        ]}}
