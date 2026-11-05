"""Helm Harbor (charts on the local kind cluster) and Docker Docks (local docker, names start with shellventure)."""
import hashlib, json, os, random, shutil, socket, subprocess, time, urllib.request

BB, NGX = "busybox:1.36", "nginx:1.27-alpine"

CHART = "apiVersion: v2\nname: {n}\nversion: 0.1.0\nappVersion: \"1.0\"\n"


def tree_hash(p):
    hsh = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        if f.is_file():
            hsh.update(f.relative_to(p).as_posix().encode() + f.read_bytes())
    return hsh.hexdigest()


def make(api):
    kc = api.kc

    def helm(*args, check=True):
        r = subprocess.run(["helm", "--kubeconfig", str(api.KUBECONFIG), "--kube-context", f"kind-{api.KIND_NAME}", *args],
                           capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"helm {' '.join(args)}: {r.stderr}")
        return r

    def release(name, ns):
        r = helm("list", "-n", ns, "-a", "-o", "json", check=False)
        try:
            return next((x for x in json.loads(r.stdout or "[]") if x["name"] == name), None)
        except ValueError:
            return None

    def write(p, files):
        for rel, body in files.items():
            f = p / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body)

    def deploy_tpl(name, image_expr, extra=""):
        return (f"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {{{{ .Release.Name }}}}\n"
                f"spec:\n  replicas: 1\n  selector:\n    matchLabels:\n      app: {{{{ .Release.Name }}}}\n"
                f"  template:\n    metadata:\n      labels:\n        app: {{{{ .Release.Name }}}}\n"
                f"    spec:\n      terminationGracePeriodSeconds: 1\n      containers:\n"
                f"        - name: main\n          image: {image_expr}\n          imagePullPolicy: IfNotPresent\n{extra}")

    # ================================================================ HELM
    def helm_setup(d, w):
        with api.con.status("[cyan]Building Helm Harbor (kind, about 1 minute)...", spinner="dots12"):
            api.kind_up()
            for ns in ("helm1", "helm2", "helm3", "helm4"):
                kc("delete", "ns", ns, "--ignore-not-found", "--wait=true")
            if d.exists():
                shutil.rmtree(d)

            # 1. template reads a value that does not exist
            c = d / "1-template-trap" / "door"
            write(c, {"Chart.yaml": CHART.format(n="door"),
                      "values.yaml": "image:\n  repository: busybox\n  tag: \"1.36\"\n",
                      "templates/deployment.yaml": deploy_tpl("door", '"{{ .Values.image.repository }}:{{ .Values.image.version }}"',
                                                              "          command: [\"sleep\", \"infinity\"]\n")})
            helm("install", "door", str(c), "-n", "helm1", "--create-namespace")

            # 2. failed upgrade, rev 1 was fine
            c = d / "2-failed-release" / "gate"
            write(c, {"Chart.yaml": CHART.format(n="gate"),
                      "values.yaml": "image:\n  repository: nginx\n  tag: 1.27-alpine\n",
                      "templates/deployment.yaml": deploy_tpl("gate", '"{{ .Values.image.repository }}:{{ .Values.image.tag }}"')})
            helm("install", "gate", str(c), "-n", "helm2", "--create-namespace", "--wait", "--timeout", "90s")
            helm("upgrade", "gate", str(c), "-n", "helm2", "--set", "image.tag=1.27-alpine-hotfix",
                 "--wait", "--timeout", "8s", check=False)

            # 3. hidden switch: Service only renders with the right values
            c = d / "3-hidden-switch" / "lantern"
            write(c, {"Chart.yaml": CHART.format(n="lantern"),
                      "values.yaml": "image: nginx:1.27-alpine\nexpose: {}\n",
                      "templates/deployment.yaml": deploy_tpl("lantern", "{{ .Values.image }}"),
                      "templates/service.yaml":
                          "{{- with .Values.expose.corridor }}\n{{- if and .enabled .port }}\n"
                          "apiVersion: v1\nkind: Service\nmetadata:\n  name: {{ $.Release.Name }}\nspec:\n"
                          "  selector:\n    app: {{ $.Release.Name }}\n  ports:\n    - port: {{ .port }}\n      targetPort: 80\n"
                          "{{- end }}\n{{- end }}\n"})
            helm("install", "lantern", str(c), "-n", "helm3", "--create-namespace")
            w["data"]["h3"] = tree_hash(c / "templates")

            # 4. pre-install hook fails, first install = failed release
            c = d / "4-hook-horror" / "migrator"
            write(c, {"Chart.yaml": CHART.format(n="migrator"),
                      "values.yaml": "db:\n  url: \"\"\n",
                      "templates/deployment.yaml": deploy_tpl("migrator", BB, "          command: [\"sleep\", \"infinity\"]\n"),
                      "templates/migrate-job.yaml":
                          "apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: {{ .Release.Name }}-db-migrate\n  annotations:\n"
                          "    \"helm.sh/hook\": pre-install,pre-upgrade\n    \"helm.sh/hook-delete-policy\": before-hook-creation\n"
                          "spec:\n  backoffLimit: 0\n  template:\n    spec:\n      restartPolicy: Never\n      containers:\n"
                          "        - name: migrate\n          image: busybox:1.36\n          imagePullPolicy: IfNotPresent\n"
                          "          env:\n            - name: DB_URL\n              value: {{ .Values.db.url | quote }}\n"
                          "          command: [\"sh\", \"-c\", \"test -n \\\"$DB_URL\\\" || { echo 'FATAL: DB_URL is empty'; exit 1; }; echo migrated $DB_URL\"]\n"})
            helm("install", "migrator", str(c), "-n", "helm4", "--create-namespace", "--timeout", "60s", check=False)
            w["data"]["h4"] = tree_hash(c / "templates")

    def h_door(d, w, _):
        rel = release("door", "helm1")
        if not rel or rel["status"] != "deployed" or int(rel["revision"]) < 2:
            return False, "Release 'door' needs a successful helm upgrade (revision 2+)."
        return api.ready("helm1", "door"), "deploy/door is not Ready yet."

    def h_gate(d, w, _):
        rel = release("gate", "helm2")
        if not rel or rel["status"] != "deployed":
            return False, f"Release 'gate' status: {rel and rel['status']}."
        return api.ready("helm2", "gate"), "deploy/gate is not Ready yet."

    def h_lantern(d, w, _):
        if tree_hash(d / "3-hidden-switch" / "lantern" / "templates") != w["data"]["h3"]:
            return False, "No cheating: do not edit the templates. Only values."
        svc = kc("get", "svc", "lantern", "-n", "helm3", "-o", "json", check=False)
        if not svc:
            return False, "There is no Service 'lantern' in helm3."
        if json.loads(svc)["metadata"].get("annotations", {}).get("meta.helm.sh/release-name") != "lantern":
            return False, "Service 'lantern' must come from the helm release, not kubectl."
        ep = json.loads(kc("get", "endpoints", "lantern", "-n", "helm3", "-o", "json"))
        return any(s.get("addresses") for s in ep.get("subsets", [])), "Service 'lantern' has no endpoints yet."

    def h_migrator(d, w, _):
        if tree_hash(d / "4-hook-horror" / "migrator" / "templates") != w["data"]["h4"]:
            return False, "No cheating: keep the migration hook as it is."
        rel = release("migrator", "helm4")
        if not rel or rel["status"] != "deployed":
            return False, f"Release 'migrator' status: {rel and rel['status']}."
        return api.ready("helm4", "migrator"), "deploy/migrator is not Ready yet."

    HELM = {"title": "Helm Harbor", "needs": ["kind", "docker", "kubectl", "helm"], "dir": "helm", "setup": helm_setup, "kind": True, "rooms": [
        {"name": "The Template Trap", "dir": "1-template-trap", "check": h_door,
         "story": "Release [bold]door[/] installed fine. But its pod never starts.",
         "task": "Namespace [bold]helm1[/]. Fix the chart in ./door and [bold]helm upgrade[/] it until deploy/door is Ready.\nThen: [cyan]check[/]",
         "hints": ["`kubectl get pods -n helm1` then look at the image name in `kubectl describe`.",
                   "`helm template door ./door` shows what Helm really renders. Compare with values.yaml.",
                   "The template asks for `.Values.image.version`. Use `.tag`, then `helm upgrade door ./door -n helm1`."]},
        {"name": "The Failed Upgrade", "dir": "2-failed-release", "check": h_gate,
         "story": "Someone upgraded [bold]gate[/] with a hotfix tag. Helm says FAILED.",
         "task": "Namespace [bold]helm2[/]. Get release gate back to [bold]deployed[/] and healthy.\nThen: [cyan]check[/]",
         "hints": ["`helm history gate -n helm2`", "Revision 1 was good.", "`helm rollback gate 1 -n helm2`"]},
        {"name": "The Hidden Switch", "dir": "3-hidden-switch", "check": h_lantern,
         "story": "The chart [bold]can[/] make a Service. Nobody remembers how.",
         "task": "Namespace [bold]helm3[/]. Make release lantern create Service [bold]lantern[/] on port 80.\n"
                 "Use [bold]values only[/] (--set or -f). Do not edit templates. Then: [cyan]check[/]",
         "hints": ["Read ./lantern/templates/service.yaml. What must be true?",
                   "It needs `expose.corridor.enabled` AND `expose.corridor.port`.",
                   "`helm upgrade lantern ./lantern -n helm3 --set expose.corridor.enabled=true --set expose.corridor.port=80`"]},
        {"name": "The Hook Horror", "dir": "4-hook-horror", "check": h_migrator,
         "story": "First install of [bold]migrator[/] failed in a pre-install hook. Now even upgrade complains.",
         "task": "Namespace [bold]helm4[/]. Get release migrator [bold]deployed[/]. Keep the hook.\nThen: [cyan]check[/]",
         "hints": ["`kubectl logs job/migrator-db-migrate -n helm4`  What does the hook need?",
                   "It needs a value: db.url. Give it to the release with --set.",
                   "`helm upgrade --install migrator ./migrator -n helm4 --set db.url=postgres://db:5432/app`"]},
    ]}

    # ================================================================ DOCKER
    def docker(*args, check=True):
        r = subprocess.run(["docker", *args], capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"docker {' '.join(args)}: {r.stderr}")
        return r

    def free_port():
        for _ in range(50):
            p = random.randint(18000, 18999)
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", p)) != 0:
                    return p
        return 18080

    def docker_setup(d, w):
        if True:  # build() already shows a spinner for non-kind worlds
            for img in (BB, NGX):
                api.sh(f"docker image inspect {img} >/dev/null 2>&1 || docker pull -q {img}")
            docker("rm", "-f", "shellventure-web", "shellventure-health", check=False)
            docker("rmi", "-f", "shellventure/door:1", "shellventure/slim:1", "shellventure/web:1", "shellventure/health:1", check=False)
            if d.exists():
                shutil.rmtree(d)

            # 1. COPY of a misnamed file + .dockerignore that hides it
            r, real = d / "1-broken-build", api.code()
            write(r, {"Dockerfile": f"FROM {BB}\nCOPY door-code.txt /door/code.txt\nCMD [\"cat\", \"/door/code.txt\"]\n",
                      "door_code.txt": real + "\n", ".dockerignore": "*.txt\n*.log\n"})
            w["data"]["d1"] = api.h(real)

            # 2. fat image: big file added in one layer, deleted in the next
            r = d / "2-fat-image"
            write(r, {"Dockerfile": f"FROM {BB}\nRUN dd if=/dev/urandom of=/big bs=1M count=60\n"
                                    "RUN md5sum /big > /checksum\nRUN rm /big\nCMD [\"echo\", \"slim-ok\"]\n"})
            docker("build", "-q", "-t", "shellventure/slim:1", str(r))

            # 3. container publishes the wrong container port
            r, real, port = d / "3-wrong-port", api.code(), free_port()
            write(r, {"Dockerfile": f"FROM {NGX}\nRUN echo '<h1>exit code: {real}</h1>' > /usr/share/nginx/html/index.html\n",
                      "PORT.txt": f"{port}\n"})
            docker("build", "-q", "-t", "shellventure/web:1", str(r))
            docker("run", "-d", "--name", "shellventure-web", "-p", f"127.0.0.1:{port}:8080", "shellventure/web:1")
            w["data"].update(d3=real, port=port)

            # 4. healthcheck uses curl, busybox has no curl
            r = d / "4-unhealthy"
            write(r, {"Dockerfile": f"FROM {BB}\nRUN mkdir -p /www && echo ok > /www/index.html\n"
                                    "HEALTHCHECK --interval=2s --timeout=2s --retries=2 CMD curl -fs http://localhost:8080/ || exit 1\n"
                                    "CMD [\"httpd\", \"-f\", \"-p\", \"8080\", \"-h\", \"/www\"]\n"})
            docker("build", "-q", "-t", "shellventure/health:1", str(r))
            docker("run", "-d", "--name", "shellventure-health", "shellventure/health:1")

    def d_door(d, w, _):
        r = docker("run", "--rm", "shellventure/door:1", check=False)
        if r.returncode != 0:
            return False, "Image shellventure/door:1 does not run yet:\n" + (r.stderr.strip()[-200:] or "not built")
        return api.h(r.stdout.strip()) == w["data"]["d1"], "It runs, but prints the wrong thing."

    def d_slim(d, w, _):
        df = (d / "2-fat-image" / "Dockerfile").read_text()
        if "dd if=/dev/urandom" not in df or "md5sum" not in df:
            return False, "No cheating: still create /big and its checksum during the build."
        r = docker("image", "inspect", "shellventure/slim:1", "--format", "{{.Size}}", check=False)
        if r.returncode != 0:
            return False, "Image shellventure/slim:1 is missing."
        mb = int(r.stdout.strip()) / 1e6
        if mb > 10:
            return False, f"shellventure/slim:1 is {mb:.0f} MB. Need under 10 MB."
        out = docker("run", "--rm", "shellventure/slim:1", check=False).stdout.strip()
        return out == "slim-ok", "The image must still print slim-ok."

    def d_web(d, w, _):
        try:
            body = urllib.request.urlopen(f"http://127.0.0.1:{w['data']['port']}/", timeout=3).read().decode()
        except OSError as e:
            return False, f"curl localhost:{w['data']['port']} fails: {e}"
        return w["data"]["d3"] in body, "Something answers, but not the shellventure-web page."

    def d_health(d, w, _):
        r = docker("inspect", "shellventure-health", "--format", "{{json .State.Health}}|{{json .Config.Healthcheck}}", check=False)
        if r.returncode != 0:
            return False, "Container shellventure-health does not exist."
        health, hc = r.stdout.strip().split("|", 1)
        if hc in ("null", "") or "NONE" in hc:
            return False, "No cheating: the container must keep a HEALTHCHECK."
        st = (json.loads(health) or {}).get("Status")
        return st == "healthy", f"shellventure-health is {st}."

    DOCKER = {"title": "Docker Docks", "needs": ["docker"], "dir": "docker", "setup": docker_setup, "rooms": [
        {"name": "The Broken Build", "dir": "1-broken-build", "check": d_door,
         "story": "The door image will not build. There are [bold]two[/] reasons.",
         "task": "Build [bold]shellventure/door:1[/] from this folder so that\n`docker run --rm shellventure/door:1` prints the code. Then: [cyan]check[/]",
         "hints": ["`docker build -t shellventure/door:1 .`  Read the error.",
                   "Compare the file name in the Dockerfile with `ls`. Then look at .dockerignore.",
                   "Fix COPY to door_code.txt AND allow it in .dockerignore (add `!door_code.txt`)."],
         "steps": [
             {"name": "COPY names the wrong file", "done": lambda d, w: "door_code.txt" in (d / "1-broken-build" / "Dockerfile").read_text(),
              "hints": ["`docker build -t shellventure/door:1 .`  Read the error: which file is missing?",
                        "Compare the name in the COPY line with `ls`.", "Change COPY to `door_code.txt`."]},
             {"name": ".dockerignore hides the file", "done": lambda d, w: "!door_code.txt" in (d / "1-broken-build" / ".dockerignore").read_text()
                                                                          or "*.txt" not in (d / "1-broken-build" / ".dockerignore").read_text(),
              "hints": ["The name is right, still 'not found'? Something hides files from the build.",
                        "`cat .dockerignore`  Which pattern matches door_code.txt?",
                        "Add a line `!door_code.txt` to .dockerignore, then build again."]},
         ]},
        {"name": "The Fat Image", "dir": "2-fat-image", "check": d_slim,
         "story": "The Dockerfile deletes a 60 MB file. The image is still 64 MB. [bold]Why?[/]",
         "task": "Rebuild [bold]shellventure/slim:1[/] under 10 MB. Keep creating /big and its checksum.\nThen: [cyan]check[/]",
         "hints": ["`docker history shellventure/slim:1`  Each RUN is a layer.",
                   "A file deleted in a later layer still lives in the earlier layer.",
                   "Create, checksum and delete in ONE RUN: `RUN dd ... && md5sum /big > /checksum && rm /big`"]},
        {"name": "The Wrong Port", "dir": "3-wrong-port", "check": d_web,
         "story": "Container [bold]shellventure-web[/] is running. `curl localhost:<PORT.txt>` gets nothing.",
         "task": "Make `curl localhost:$(cat PORT.txt)` show the shellventure-web page. Then: [cyan]check[/]",
         "hints": ["`docker ps`  Look at the PORTS column.", "Which port does nginx listen on inside the container?",
                   "`docker rm -f shellventure-web` then `docker run -d --name shellventure-web -p 127.0.0.1:$(cat PORT.txt):80 shellventure/web:1`"]},
        {"name": "The Unhealthy One", "dir": "4-unhealthy", "check": d_health,
         "story": "The server works. Docker swears it is [bold]unhealthy[/].",
         "task": "Make container [bold]shellventure-health[/] healthy. Keep a HEALTHCHECK.\nThen: [cyan]check[/]",
         "hints": ["`docker inspect shellventure-health --format '{{json .State.Health}}'`  Read the Output.",
                   "busybox has no curl. What does it have?",
                   "Use `wget -q -O /dev/null http://localhost:8080/` in the HEALTHCHECK, rebuild, then recreate the container."]},
    ]}
    return {"helm": HELM, "docker": DOCKER}
