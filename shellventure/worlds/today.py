"""Today's Bugs: real DevOps bugs, rebuilt as offline puzzles (works on laptop and phone).

No cluster, no docker: files only. Skills: jq, base64/JWT reading, sha256 compare, helm hook rules.
"""
import base64, hashlib, json, random, shutil


def b64url(obj):
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode().rstrip("=")


def fake_jwt(claims):
    return f"{b64url({'alg': 'RS256', 'typ': 'JWT'})}.{b64url(claims)}.{base64.urlsafe_b64encode(random.randbytes(32)).decode().rstrip('=')}"


def make(api):
    def setup(d, w):
        if d.exists():
            shutil.rmtree(d)
        names = ["orion", "vega", "lyra", "draco", "nova", "pyxis", "rigel"]

        # 1. the 6-line trap: count output lines vs real answers
        r = d / "1-six-namespaces"
        r.mkdir(parents=True)
        real = random.randint(40, 300)
        (r / "kubectl-output.txt").write_text(
            "\n".join([f'E1029 11:20:1{i}.23 4147 memcache.go:265] "Unhandled Error" err="couldn\'t get current server API group list: '
                       f'the server has asked for the client to provide credentials"' for i in range(5)]
                      + ["error: You must be logged in to the server (the server has asked for the client to provide credentials)"]) + "\n")
        (r / "README.txt").write_text("Someone ran:  kubectl get ns --no-headers | wc -l   on 5 clusters.\n"
                                      "Every cluster said 6. The real output of one run is in kubectl-output.txt.\n")
        w["answers"]["1"] = api.h("0")

        # 2. which token is missing the claim the cluster needs
        r = d / "2-missing-claim"
        r.mkdir(parents=True)
        tid, cid = "11111111-2222-4333-8444-555555555555", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"  # fake ids
        base = {"iss": f"https://login.shellventure.local/{tid}/v2.0", "aud": cid, "ver": "2.0", "tid": tid}
        files = [f"token-{c}.jwt" for c in "abcde"]
        bad = random.choice(files)
        for f in files:
            claims = dict(base, sub=api.code(), iat=1793260000, exp=1793263600)
            if f != bad:
                claims.update(email=f"{random.choice(api.NAMES)}@shellventure.local", name="Escape User", preferred_username="user")
            (r / f).write_text(fake_jwt(claims) + "\n")
        (r / "README.txt").write_text("The cluster maps your user from the 'email' claim.\nOne token will be rejected (401). Which file?\n")
        w["answers"]["2"] = api.h(bad)

        # 3. which kubeconfig user has the odd client secret (compare without printing secrets)
        r = d / "3-odd-secret"
        r.mkdir(parents=True)
        good, odd_user = api.code() + "-" + api.code(), random.choice(names)
        users = [{"name": f"{n}-dev-default-user", "user": {"auth-provider": {"name": "oidc", "config": {
            "client-id": cid, "client-secret": (api.code() if n == odd_user else good),
            "idp-issuer-url": base["iss"]}}}} for n in names]
        (r / "kubeconfig.json").write_text(json.dumps({"apiVersion": "v1", "kind": "Config", "users": users}, indent=1))
        (r / "README.txt").write_text("6 clusters log in fine. One fails: invalid_client (Invalid client secret).\n"
                                      "Find the odd user WITHOUT printing any secret (compare fingerprints).\n")
        w["answers"]["3"] = api.h(odd_user)

        # 4. which chart template drops the database on every helm upgrade
        r = d / "4-upgrade-wipe" / "templates"
        r.mkdir(parents=True)
        tpl = {
            "database.yaml": None, "configmap.yaml": None, "migrate-job.yaml": None, "secret.yaml": None, "deployment.yaml": None}
        bad_tpl = "database.yaml"
        for f in tpl:
            kind = {"database.yaml": "Database", "configmap.yaml": "ConfigMap", "migrate-job.yaml": "Job",
                    "secret.yaml": "Secret", "deployment.yaml": "Deployment"}[f]
            ann = ""
            if f == "database.yaml":
                ann = '  annotations:\n    "helm.sh/hook": pre-install,pre-upgrade\n'
            elif f == "migrate-job.yaml":
                ann = ('  annotations:\n    "helm.sh/hook": pre-install,pre-upgrade\n'
                       '    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded\n')
            elif f == "secret.yaml":
                ann = '  annotations:\n    "helm.sh/resource-policy": keep\n'
            api_v = "db.example.com/v1" if kind == "Database" else ("batch/v1" if kind == "Job" else ("apps/v1" if kind == "Deployment" else "v1"))
            (r / f).write_text(f"apiVersion: {api_v}\nkind: {kind}\nmetadata:\n  name: {{{{ .Release.Name }}}}\n{ann}")
        (r.parent / "README.txt").write_text("After every helm upgrade the app's database is EMPTY.\n"
                                             "Which template causes it? (a Database CR creates/drops the DB)\n")
        w["answers"]["4"] = api.h(bad_tpl)

    return {"today": {"title": "Today's Bugs", "needs": ["jq", "base64", "sha256sum"], "dir": "today", "setup": setup, "rooms": [
        {"name": "The Six Namespaces", "dir": "1-six-namespaces", "answer": True,
         "story": "5 clusters. Every one says [bold]6 namespaces[/]. Suspicious.",
         "task": "How many namespaces did that run REALLY list? Read the output.\nThen: [cyan]check <number>[/]",
         "hints": ["`wc -l` counts lines. ANY lines.", "Are these namespace names, or errors?",
                   "All 6 lines are errors (stderr was counted). Real namespaces listed: 0."]},
        {"name": "The Missing Claim", "dir": "2-missing-claim", "answer": True,
         "story": "Your phone signed in fine. The cluster still says 401.",
         "task": "Which token file has [bold]no email claim[/]? Then: [cyan]check <file>[/]",
         "hints": ["A JWT is header.payload.signature. The payload is base64url JSON.",
                   "`cut -d. -f2 token-a.jwt | tr '_-' '/+' | base64 -d 2>/dev/null`",
                   "`for f in token-*.jwt; do echo \"$f $(cut -d. -f2 $f | tr '_-' '/+' | base64 -d 2>/dev/null | jq -r .email)\"; done`"]},
        {"name": "The Odd Secret", "dir": "3-odd-secret", "answer": True,
         "story": "One cluster says [bold]Invalid client secret[/]. Never print secrets on screen.",
         "task": "Which cluster name (orion, vega, lyra...) has the different secret?\nThen: [cyan]check <name>[/]",
         "hints": ["Compare a hash of each secret, not the secret.",
                   "`jq -r '.users[] | \"\\(.name) \\(.user[\"auth-provider\"].config[\"client-secret\"])\"' kubeconfig.json`  (pipe it, don't look)",
                   "`... | while read n s; do echo \"$n $(printf %s \"$s\" | sha256sum | cut -c1-8)\"; done`"]},
        {"name": "The Upgrade Wipe", "dir": "4-upgrade-wipe", "answer": True,
         "story": "Install: fine. [bold]helm upgrade[/]: the database is empty. Every time.",
         "task": "Which template file causes the wipe? Then: [cyan]check <file>[/]",
         "hints": ["Look at helm.sh/hook annotations: `grep -r helm.sh templates/`",
                   "A hook with no delete policy gets before-hook-creation: deleted and recreated on each upgrade.",
                   "Which hooked resource holds data? A Database drops the schema when deleted."]},
    ]}}
