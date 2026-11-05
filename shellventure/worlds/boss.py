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

    def jp(kind, name, path):
        return kc("get", kind, name, "-n", NS, "-o", "jsonpath={" + path + "}", check=False)

    C = ".spec.template.spec.containers[0]"
    STEPS = {   # smart hints: one step per fault the boss picked
        "image": {"name": "the image", "done": lambda d, w: not jp("deploy", "boss-app", C + ".image").endswith("-x"),
                  "hints": ["`kubectl get pods -n boss`: ErrImagePull or ImagePullBackOff?",
                            "Describe the pod: that image tag does not exist.",
                            "`kubectl set image deploy/boss-app boss-app=nginx:1.27-alpine -n boss`"]},
        "secret": {"name": "the secret", "done": lambda d, w: bool(jp("secret", "boss-secret", ".data.token")),
                   "hints": ["CreateContainerConfigError? `kubectl describe pod -n boss`",
                             "The pod wants key `token`. `kubectl get secret boss-secret -n boss -o yaml`",
                             "`kubectl patch secret boss-secret -n boss -p '{\"stringData\":{\"token\":\"s3cret\"}}'`"]},
        "probe": {"name": "the readiness probe", "done": lambda d, w: jp("deploy", "boss-app", C + ".readinessProbe.httpGet.port") == "80",
                  "hints": ["Running but 0/1 Ready? Describe the pod: what fails?",
                            "nginx listens on 80. Which port does the probe call?",
                            "`kubectl edit deploy boss-app -n boss` and set the readinessProbe port to 80."]},
        "selector": {"name": "the service", "done": lambda d, w: jp("svc", "boss", ".spec.selector.app") == "boss-app",
                     "hints": ["`kubectl get endpoints boss -n boss`  Empty?",
                               "Compare the service selector with the pod labels: `kubectl get pods -n boss --show-labels`",
                               "`kubectl patch svc boss -n boss -p '{\"spec\":{\"selector\":{\"app\":\"boss-app\"}}}'`"]},
        "quota": {"name": "no pods allowed", "done": lambda d, w: jp("quota", "lock", ".spec.hard.pods") != "0",
                  "hints": ["No pods at all? `kubectl describe rs -n boss`",
                            "Something limits the namespace: `kubectl get quota -n boss`", "`kubectl delete quota lock -n boss`"]},
        "memory": {"name": "the memory limit", "done": lambda d, w: jp("deploy", "boss-app", C + ".resources.limits.memory") != "2Mi",
                   "hints": ["The pod keeps restarting? Describe it: Last State reason?",
                             "OOMKilled: the memory limit is far too small for nginx.",
                             "`kubectl set resources deploy/boss-app -n boss --limits=memory=64Mi`"]},
    }

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
                       "Fix one, wait 10 seconds, look again. The next head shows only after the first falls."],
             "steps": lambda w: [STEPS[f] for f in w["data"].get("faults", [])]},
        ]}}
