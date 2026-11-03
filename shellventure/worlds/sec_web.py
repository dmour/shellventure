"""Security Gate and Web Street: offline worlds (git, jq, coreutils). Random values on every reset."""
import json, os, random, shutil, string


def make(api):
    h = api.h

    def fresh(d):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    def answer_check(n):
        def chk(d, w, arg):
            return api.h(arg or "") == w["answers"][str(n)], "Not this one. Look again."
        return chk

    def rnd(n, chars=string.ascii_uppercase + string.digits):
        return "".join(random.choice(chars) for _ in range(n))

    # ================================================================ SECURITY GATE
    def sec_setup(d, w):
        fresh(d)
        # 1. CVE hunt: the one CRITICAL vuln that has a fix
        r = d / "1-cve-hunt"; r.mkdir()
        pkgs = ["openssl", "libxml2", "zlib", "curl", "glibc", "log4j-core", "jackson-databind", "busybox", "expat", "libpng"]
        random.shuffle(pkgs)
        target = pkgs[0]
        vulns = []
        for i, p in enumerate(pkgs):
            sev = "CRITICAL" if i in (0, 1) else random.choice(["LOW", "MEDIUM", "HIGH"])
            fixed = f"{random.randint(1, 9)}.{random.randint(0, 9)}.{random.randint(1, 20)}" if i != 1 else ""
            vulns.append({"VulnerabilityID": f"CVE-202{random.randint(1, 6)}-{random.randint(1000, 49999)}", "PkgName": p,
                          "InstalledVersion": f"{random.randint(0, 3)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
                          "FixedVersion": fixed, "Severity": sev})
        random.shuffle(vulns)
        (r / "scan.json").write_text(json.dumps({"ArtifactName": "registry.local/app:1.4.2",
                                                  "Results": [{"Target": "app (debian 12)", "Vulnerabilities": vulns}]}, indent=1))
        w["answers"]["1"] = h(target)
        # 2. AWS key committed, then "removed"
        r = d / "2-secret-history"; r.mkdir()
        api.git(r, "init", "-q", "-b", "main")
        key = "AKIA" + rnd(16)
        at = random.randint(3, 9)
        for i in range(14):
            cfg = f"region = eu-west-1\nretries = {random.randint(1, 5)}\n"
            if i == at:
                cfg += f"aws_access_key_id = {key}\naws_secret_access_key = {rnd(40, string.ascii_letters + string.digits)}\n"
            (r / "settings.ini").write_text(cfg)
            api.git(r, "add", "-A")
            api.git(r, "commit", "-q", "--allow-empty", "-m", random.choice(["tune retries", "cleanup", "update config"]),
                    who=random.choice(api.NAMES))
        w["answers"]["2"] = h(key)
        # 3. RBAC: which ServiceAccount can delete secrets in ALL namespaces
        r = d / "3-too-much-power"; r.mkdir()
        sas = random.sample(["ci-runner", "metrics", "backup", "deployer", "argocd", "logger", "dashboard"], 5)
        guilty = sas[0]
        docs = []
        for i, sa in enumerate(sas):
            kind = "ClusterRole" if i in (0, 1) else "Role"
            verbs = ["get", "list", "delete"] if i in (0, 2) else ["get", "list", "watch"]
            res = ["secrets"] if i in (0, 2, 3) else ["pods", "configmaps"]
            docs.append({"apiVersion": "rbac.authorization.k8s.io/v1", "kind": kind,
                         "metadata": {"name": f"{sa}-role", **({} if kind == "ClusterRole" else {"namespace": "apps"})},
                         "rules": [{"apiGroups": [""], "resources": res, "verbs": verbs}]})
            docs.append({"apiVersion": "rbac.authorization.k8s.io/v1", "kind": kind + "Binding",
                         "metadata": {"name": f"{sa}-binding", **({} if kind == "ClusterRole" else {"namespace": "apps"})},
                         "roleRef": {"kind": kind, "name": f"{sa}-role", "apiGroup": "rbac.authorization.k8s.io"},
                         "subjects": [{"kind": "ServiceAccount", "name": sa, "namespace": "apps"}]})
        random.shuffle(docs)
        (r / "rbac.json").write_text(json.dumps({"items": docs}, indent=1))
        w["answers"]["3"] = h(guilty)
        # 4. fix-it: the image must not run as root
        r = d / "4-root-container"; r.mkdir()
        (r / "Dockerfile").write_text("FROM alpine:3.20\nRUN adduser -D -u 10001 app\nCOPY app.sh /app/app.sh\n"
                                      "RUN chmod +x /app/app.sh\nWORKDIR /app\nCMD [\"/app/app.sh\"]\n")
        (r / "audit.txt").write_text("policy: containers must not run as root (UID 0)\n"
                                     "result: FAIL  Dockerfile  image runs as root: no USER instruction after the last FROM\n")

    def sec4(d, w, _):
        lines = [l.strip() for l in (d / "4-root-container" / "Dockerfile").read_text().splitlines()]
        last_from = max((i for i, l in enumerate(lines) if l.upper().startswith("FROM ")), default=-1)
        users = [l.split(None, 1)[1].strip() if len(l.split()) > 1 else "" for l in lines[last_from + 1:] if l.upper().startswith("USER")]
        if "adduser -D -u 10001 app" not in "\n".join(lines):
            return False, "Keep the adduser line: the app user must exist."
        if not users:
            return False, "Still no USER instruction after the last FROM."
        u = users[-1].split(":")[0]
        return u not in ("root", "0", ""), f"USER {u} is still root."

    SEC = {"title": "Security Gate", "dir": "security", "setup": sec_setup, "skill": "security", "needs": ["git", "jq"], "rooms": [
        {"name": "The CVE Hunt", "dir": "1-cve-hunt", "check": answer_check(1), "typed": True,
         "story": "The scanner found many CVEs. You have time to fix [bold]one[/] today.",
         "task": "Which package has a [bold]CRITICAL[/] CVE that already has a [bold]fixed version[/]? Type its name.",
         "hints": ["`jq '.Results[0].Vulnerabilities[] | select(.Severity==\"CRITICAL\")' scan.json`",
                   "Two are CRITICAL. Only one has a FixedVersion.",
                   "`jq -r '.Results[0].Vulnerabilities[] | select(.Severity==\"CRITICAL\" and .FixedVersion!=\"\").PkgName' scan.json`"]},
        {"name": "Secret in History", "dir": "2-secret-history", "check": answer_check(2), "typed": True,
         "story": "Someone pushed an AWS key, then 'removed' it in the next commit. It is still in git.",
         "task": "Type the leaked [bold]access key id[/] (starts with AKIA). (Then: rotate it! Removing a commit is not enough.)",
         "hints": ["The file today is clean. Search the history.", "`git log -p -S aws_access_key_id`",
                   "`git log -p | grep -o 'AKIA[A-Z0-9]*' | head -1`"]},
        {"name": "Too Much Power", "dir": "3-too-much-power", "check": answer_check(3), "typed": True,
         "story": "An audit asks: who can [bold]delete secrets in every namespace[/]?",
         "task": "Type the [bold]ServiceAccount[/] name.",
         "hints": ["A Role works in one namespace. A ClusterRole + ClusterRoleBinding works everywhere.",
                   "`jq '.items[] | select(.kind==\"ClusterRole\")' rbac.json` and look for secrets + delete.",
                   "Follow that ClusterRole to its ClusterRoleBinding: the subject is the answer."]},
        {"name": "The Root Container", "dir": "4-root-container", "check": sec4,
         "story": "The policy check fails: [bold]image runs as root[/].",
         "task": "Edit the Dockerfile so the container runs as the [bold]app[/] user. I check after every command.",
         "hints": ["The user is created, but never used.", "The USER instruction sets who runs the CMD.",
                   "Add a line before CMD: `USER app` (or USER 10001). e.g. `sed -i 's|^CMD|USER app\\nCMD|' Dockerfile`"]},
    ]}

    # ================================================================ WEB STREET
    def web_setup(d, w):
        fresh(d)
        # 1. nginx location matching
        r = d / "1-location-order"; r.mkdir()
        ext = random.choice(["json", "png", "css"])
        variant = random.choice(["regex", "caret", "exact"])
        uri = f"/api/v1/report.{ext}" if variant != "exact" else "/api/v1/health"
        conf = ["server {", "  listen 80;", "  location / { proxy_pass http://frontend; }",
                "  location /api/ { proxy_pass http://api_pool; }"]
        if variant == "caret":
            conf.append("  location ^~ /api/v1/ { proxy_pass http://api_v1; }")
            ans = "api_v1"
        else:
            conf.append("  location /api/v1/ { proxy_pass http://api_v1; }")
        conf.append(f"  location ~* \\.({ext}|txt)$ {{ proxy_pass http://static_files; }}")
        if variant == "exact":
            conf.append("  location = /api/v1/health { proxy_pass http://health_check; }")
            ans = "health_check"
        if variant == "regex":
            ans = "static_files"
        conf.append("}")
        (r / "nginx.conf").write_text("\n".join(conf) + "\n")
        (r / "request.txt").write_text(f"GET {uri} HTTP/1.1\nHost: shop.local\n")
        w["answers"]["1"] = h(ans)
        # 2. proxy_pass trailing slash
        r = d / "2-proxy-slash"; r.mkdir()
        slash = random.choice([True, False])
        page = random.choice(["users", "orders", "invoices"])
        (r / "nginx.conf").write_text("location /api/ {\n  proxy_pass http://backend:8080" + ("/" if slash else "") + ";\n}\n")
        (r / "request.txt").write_text(f"GET /api/{page} HTTP/1.1\n")
        w["answers"]["2"] = h(f"/{page}" if slash else f"/api/{page}")
        # 3. 502 vs 504: which upstream times out
        r = d / "3-gateway-errors"; r.mkdir()
        ups = ["auth", "cart", "search", "payments", "catalog"]
        slow, crashed = random.sample(ups, 2)
        rows = []
        for u in ups:
            for _ in range(random.randint(80, 140)):
                st = random.choice([200] * 8 + [404])
                rows.append((u, st))
            rows += [(slow, 504)] * random.randint(40, 70) + [(crashed, 502)] * random.randint(40, 70) if u == ups[-1] else []
        random.shuffle(rows)
        with open(r / "access.log", "w") as f:
            for i, (u, st) in enumerate(rows):
                f.write(f'10.0.{random.randint(0, 9)}.{random.randint(1, 250)} - - [01/Nov/2026:10:{i // 60 % 60:02d}:{i % 60:02d} +0000] '
                        f'"GET /{u}/x HTTP/1.1" {st} {random.randint(0, 5000)} upstream={u}\n')
        w["answers"]["3"] = h(slow)
        # 4. which server block answers (Host header, default_server)
        r = d / "4-wrong-host"; r.mkdir()
        names = ["shop", "blog", "admin", "api"]
        default = random.choice(names)
        host = random.choice(["www.unknown.local", "10.0.0.5", "old-shop.local"])
        blocks = []
        for n in names:
            blocks.append(f"server {{\n  listen 80{' default_server' if n == default else ''};\n  server_name {n}.local;\n"
                          f"  root /srv/{n};\n}}\n")
        random.shuffle(blocks)
        (r / "sites.conf").write_text("\n".join(blocks))
        (r / "request.txt").write_text(f"GET / HTTP/1.1\nHost: {host}\n")
        w["answers"]["4"] = h(default)

    WEB = {"title": "Web Street", "dir": "web", "setup": web_setup, "skill": "web", "rooms": [
        {"name": "Location, Location", "dir": "1-location-order", "check": answer_check(1), "typed": True,
         "story": "One request. Several [bold]location[/] blocks could match. Only one wins.",
         "task": "Which upstream gets the request in request.txt? Type its name (after http://).",
         "hints": ["nginx order: `=` exact first, then the longest prefix (stop if it has ^~), then regex (~) in file order.",
                   "A regex match beats a normal prefix match, but NOT an exact (=) or a ^~ prefix.",
                   "Check: is there an = for this exact path? A ^~ prefix? Else does a regex match?"]},
        {"name": "The Missing Slash", "dir": "2-proxy-slash", "check": answer_check(2), "typed": True,
         "story": "The backend logs say it gets a strange path. One character decides.",
         "task": "Which [bold]path[/] does the backend receive? Type it (starts with /).",
         "hints": ["Look at the end of proxy_pass: is there a / after the port?",
                   "With a URI part (even just /), nginx REPLACES the matched location prefix.",
                   "proxy_pass http://b:8080/ -> /api/users becomes /users. Without the slash it stays /api/users."]},
        {"name": "502 or 504?", "dir": "3-gateway-errors", "check": answer_check(3), "typed": True,
         "story": "Users see gateway errors. One upstream is [bold]crashing[/], another is [bold]too slow[/].",
         "task": "Which upstream is [bold]too slow[/] (timing out)? Type its name.",
         "hints": ["502 Bad Gateway = the upstream refused or broke the connection. 504 = it did not answer in time.",
                   "`awk '$9==504' access.log | grep -o 'upstream=[a-z]*' | sort | uniq -c`",
                   "The upstream with the 504s."]},
        {"name": "The Wrong Host", "dir": "4-wrong-host", "check": answer_check(4), "typed": True,
         "story": "A request with an unknown Host header still gets a page. From which site?",
         "task": "Which site (shop, blog, admin or api) answers request.txt? Type it.",
         "hints": ["No server_name matches this Host.", "Then nginx uses the default_server for that port.",
                   "`grep -B1 -A2 default_server sites.conf`"]},
    ]}
    return {"security": SEC, "web": WEB}
