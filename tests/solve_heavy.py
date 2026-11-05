#!/usr/bin/env python3
"""Solve the worlds that need docker / kind / gcloud, with real commands, in a throwaway HOME. Exit 1 on any failure.

  python3 tests/solve_heavy.py                 docker sql gcloud k8s helm network boss
  python3 tests/solve_heavy.py docker sql      only these
Uses the game's own kind cluster (kind-shellventure) and containers, then deletes them (`shellventure stop`).
Takes about 10 minutes when the images are already pulled. Not run in GitHub Actions.
"""
import json, os, re, shutil, site, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ENGINE = Path(os.environ.get("SHELLVENTURE_PY", Path(__file__).resolve().parent.parent / "shellventure" / "shellventure.py"))
HOME = Path(tempfile.mkdtemp(prefix="shellventure-heavy-"))
ROOT = HOME / "shellventure-lab"
ENV = dict(os.environ, HOME=str(HOME), SHELLVENTURE_HOME=str(HOME / ".shellventure"), TERM="dumb", COLUMNS="100",
           KUBECONFIG=str(ROOT / "k8s" / "kubeconfig"), CLOUDSDK_CONFIG=str(ROOT / "gcloud" / "sdk"),
           # the fake HOME hides `pip install --user` packages (rich): keep the real user site on the path
           PYTHONPATH=os.pathsep.join(filter(None, [site.getusersitepackages(), os.environ.get("PYTHONPATH")])))
ENV.pop("SHELLVENTURE_WORLDS", None)
# docker/kind keep their config under HOME: point them at the real one so pulls and contexts still work
ENV["DOCKER_CONFIG"] = os.environ.get("DOCKER_CONFIG", os.path.expanduser("~/.docker"))
fails = []


def sh(cmd, cwd=None, check=False):
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, env=ENV, executable="/bin/bash")
    if check and r.returncode != 0:
        fails.append(f"command failed: {cmd}\n{r.stderr[-400:]}")
    return r.stdout.strip()


def esc(*args, world=None):
    env = dict(ENV, **({"SHELLVENTURE_WORLD": world} if world else {}))
    r = subprocess.run([sys.executable, str(ENGINE), *args], capture_output=True, text=True, env=env)
    return r.stdout + r.stderr


def check(world, room, answer=None, expect=True, tries=1):
    for _ in range(tries):
        out = esc("_check", *([answer] if answer is not None else []), world=world)
        ok = "OPENED" in out or "opened!" in out
        if ok == expect:
            break
        time.sleep(5)
    label = f"{world} room {room}" + (" (not fixed yet)" if not expect else "")
    if ok != expect:
        fails.append(f"{label}: expected {'open' if expect else 'locked'}, answer={answer!r}\n{out[-500:]}")
    print(f"  {'✔' if ok == expect else '✘'} {label}", flush=True)


def hint_part(world, part, label):
    """Smart hints: the hint must be about the first part that is still broken (part 0 = all fixed)."""
    out = esc("_hint", world=world)
    ok = ("Every part looks fixed" in out) if part == 0 else (f"part {part}/" in out)
    if not ok:
        fails.append(f"{world} {label}: expected {'all fixed' if part == 0 else f'a hint for part {part}'}\n{out[-300:]}")
    print(f"  {'✔' if ok else '✘'} {world} {label}: {'all parts fixed' if part == 0 else f'hint is for part {part}'}", flush=True)


def d(world, sub=""):
    return ROOM_DIR / world / sub if sub else ROOM_DIR / world


ROOM_DIR = ROOT
K = "kubectl --context kind-shellventure"
H = "helm --kube-context kind-shellventure"


def rollout(ns, name, t="90s"):
    sh(f"{K} rollout status deploy/{name} -n {ns} --timeout={t}")


def port_forward(target, ns, remote):
    """Start kubectl port-forward on a free local port, return (process, port)."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(f"exec {K} port-forward -n {ns} {target} {port}:{remote}", shell=True, env=ENV,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, executable="/bin/bash")
    for _ in range(30):
        time.sleep(0.5)
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
    return p, port


# ---- solvers: one per world, using the hints' commands ----
def docker():
    r = d("docker", "1-broken-build")
    check("docker", 1, expect=False)
    hint_part("docker", 1, "room 1 nothing fixed")
    sh("sed -i 's/door-code.txt/door_code.txt/' Dockerfile", r)
    hint_part("docker", 2, "room 1 COPY fixed")
    sh("echo '!door_code.txt' >> .dockerignore", r)
    sh("docker build -q -t shellventure/door:1 .", r, check=True)
    check("docker", 1)
    r = d("docker", "2-fat-image")
    (r / "Dockerfile").write_text("FROM busybox:1.36\nRUN dd if=/dev/urandom of=/big bs=1M count=60 && md5sum /big > /checksum && rm /big\n"
                                  "CMD [\"echo\", \"slim-ok\"]\n")
    sh("docker build -q -t shellventure/slim:1 .", r, check=True)
    check("docker", 2)
    r = d("docker", "3-wrong-port")
    sh("docker rm -f shellventure-web && docker run -d --name shellventure-web -p 127.0.0.1:$(cat PORT.txt):80 shellventure/web:1", r, check=True)
    time.sleep(2)
    check("docker", 3)
    r = d("docker", "4-unhealthy")
    sh("sed -i 's|curl -fs http://localhost:8080/|wget -q -O /dev/null http://localhost:8080/|' Dockerfile", r)
    sh("docker build -q -t shellventure/health:1 . && docker rm -f shellventure-health && "
       "docker run -d --name shellventure-health shellventure/health:1", r, check=True)
    check("docker", 4, tries=6)


def psql(q):
    return sh(f"docker exec shellventure-pg psql -tA -U postgres -d shop -c \"{q}\"")


def sql():
    check("sql", 1, "not-a-tenant", expect=False)
    check("sql", 1, psql("SELECT name FROM tenants GROUP BY name HAVING count(*) > 1"))
    check("sql", 2, expect=False)
    psql("CREATE INDEX ON payments (ref)")
    check("sql", 2)
    check("sql", 3, expect=False)
    psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = 'batch-job-17'")
    check("sql", 3)
    check("sql", 4, psql("SELECT c.name FROM payments p JOIN customers c ON c.id = p.customer_id WHERE p.status = 'FAILED' "
                         "AND p.created_at >= '2026-10-01' AND p.created_at < '2026-11-01' GROUP BY c.name ORDER BY sum(p.amount) DESC LIMIT 1"))
    check("sql", 5, expect=False)
    psql("SELECT setval(pg_get_serial_sequence('invoices','id'), (SELECT max(id) FROM invoices))")
    check("sql", 5)


def gcloud():
    check("gcloud", 1, expect=False)
    keeper = sh("gcloud config configurations list --filter='properties.core.account=keeper@shellventure.local' --format='value(name)'")
    sh(f"gcloud config configurations activate {keeper}", check=True)
    check("gcloud", 1)
    check("gcloud", 2, expect=False)
    sh("gcloud config unset proxy/type && gcloud config unset proxy/address && gcloud config unset proxy/port", check=True)
    check("gcloud", 2)
    sh("gcloud config configurations create exit && gcloud config set account keeper@shellventure.local && "
       "gcloud config set project escape-exit", check=True)
    check("gcloud", 3)
    check("gcloud", 4, "default", expect=False)
    check("gcloud", 4, sh("gcloud config configurations list --filter='properties.core.project~-vault$ AND "
                          "properties.core.account~^ops-' --format='value(name)'"))


def k8s():
    check("k8s", 1, expect=False)
    sh(f"{K} set image deploy/door door=busybox:1.36 -n room1-door", check=True)
    rollout("room1-door", "door")
    check("k8s", 1, tries=3)
    sh(f"{K} patch secret guard-secret -n room2-guard -p '{{\"stringData\":{{\"password\":\"open-sesame\"}}}}'", check=True)
    sh(f"{K} rollout restart deploy/guard -n room2-guard")
    rollout("room2-guard", "guard")
    check("k8s", 2, tries=3)
    check("k8s", 3, expect=False)
    sh(f"{K} patch svc lamp -n room3-corridor -p '{{\"spec\":{{\"selector\":{{\"app\":\"lantern\"}}}}}}'", check=True)
    check("k8s", 3, tries=3)
    sh(f"{K} set resources deploy/monster -n room4-monster --limits=memory=128Mi --requests=memory=64Mi", check=True)
    rollout("room4-monster", "monster")
    check("k8s", 4, tries=3)
    check("k8s", 5, expect=False)
    hint_part("k8s", 1, "room 5 nothing fixed")
    sh(f"{K} delete quota lock -n room5-gate", check=True)
    hint_part("k8s", 2, "room 5 quota fixed")
    sh(f"{K} patch deploy gate -n room5-gate --type=json "
       "-p='[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/readinessProbe/httpGet/port\",\"value\":80}]'", check=True)
    rollout("room5-gate", "gate")
    check("k8s", 5, tries=3)


def helm():
    r = d("helm", "1-template-trap")
    check("helm", 1, expect=False)
    sh("sed -i 's/.Values.image.version/.Values.image.tag/' door/templates/deployment.yaml", r)
    sh(f"{H} upgrade door ./door -n helm1 --wait --timeout 90s", r, check=True)
    check("helm", 1, tries=3)
    check("helm", 2, expect=False)
    sh(f"{H} rollback gate 1 -n helm2 --wait --timeout 90s", check=True)
    check("helm", 2, tries=3)
    r = d("helm", "3-hidden-switch")
    check("helm", 3, expect=False)
    sh(f"{H} upgrade lantern ./lantern -n helm3 --set expose.corridor.enabled=true --set expose.corridor.port=80 --wait --timeout 90s", r, check=True)
    check("helm", 3, tries=3)
    r = d("helm", "4-hook-horror")
    check("helm", 4, expect=False)
    sh(f"{H} upgrade --install migrator ./migrator -n helm4 --set db.url=postgres://db:5432/app --wait --timeout 90s", r, check=True)
    check("helm", 4, tries=3)


def network():
    rollout("net1", "client")
    rollout("secrets", "vault")
    check("network", 1, "vault", expect=False)
    body = sh(f"{K} exec -n net1 deploy/client -- wget -qO- -T 5 vault.secrets")
    if "nginx" not in body.lower():
        fails.append(f"network room 1: vault.secrets did not answer from net1: {body[:200]!r}")
    check("network", 1, "vault.secrets")
    r = d("network", "2-cert-check")
    check("network", 2, "cert-z.pem", expect=False)
    cert = sh("for f in cert-*.pem; do openssl x509 -in $f -noout -ext subjectAltName | grep -q 'DNS:pay.shellventure.local' && echo $f; done", r)
    check("network", 2, cert)
    r = d("network", "3-key-match")
    key = sh("for f in cert-*.pem; do openssl x509 -in $f -noout -pubkey | cmp -s - <(openssl pkey -in key.pem -pubout) && echo $f; done", r)
    check("network", 3, key)
    rollout("net4", "radio")
    port = sh(f"{K} exec -n net4 deploy/radio -- netstat -tln | awk '/LISTEN/ {{split($4,a,\":\"); print a[length(a)]}}' | head -1")
    p, local = port_forward("deploy/radio", "net4", port)
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{local}/", timeout=5).read().decode()
    except OSError as e:
        page = f"ERROR {e}"
    p.kill()
    check("network", 4, "0000", expect=False)
    check("network", 4, page.replace("code:", "").strip())
    rollout("net5", "gatekeeper")
    p, local = port_forward("svc/gatekeeper", "net5", 80)
    code = sh(f"curl -si -H 'Host: vault.shellventure.local' localhost:{local}/ | awk -F': ' 'tolower($1)==\"x-escape-code\" {{print $2}}' | tr -d '\\r'")
    p.kill()
    check("network", 5, code)


def boss():
    check("boss", 1, expect=False)
    hint_part("boss", 1, "nothing fixed")
    # a player fixes what they find; the solver applies all 6 usual fixes (the ones not broken are no-ops)
    sh(f"{K} delete quota lock -n boss --ignore-not-found")
    sh(f"{K} patch secret boss-secret -n boss -p '{{\"stringData\":{{\"token\":\"s3cret\"}}}}'")
    sh(f"{K} patch svc boss -n boss -p '{{\"spec\":{{\"selector\":{{\"app\":\"boss-app\"}}}}}}'")
    sh(f"{K} patch deploy boss-app -n boss --type=json -p='["
       "{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/image\",\"value\":\"nginx:1.27-alpine\"},"
       "{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/readinessProbe/httpGet/port\",\"value\":80},"
       "{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/limits/memory\",\"value\":\"64Mi\"}]'", check=True)
    hint_part("boss", 0, "after all fixes")
    sh(f"{K} rollout restart deploy/boss-app -n boss")
    rollout("boss", "boss-app", "120s")
    check("boss", 1, tries=4)


SOLVERS = {"docker": docker, "sql": sql, "gcloud": gcloud, "k8s": k8s, "helm": helm, "network": network, "boss": boss}


def main():
    want = sys.argv[1:] or list(SOLVERS)
    t0 = time.time()
    try:
        for w in want:
            t = time.time()
            print(f"== {w}", flush=True)
            out = esc("reset", w)
            if not (ROOT / w).exists() or "Traceback" in out:
                fails.append(f"{w}: world did not build\n{out[-600:]}")
                continue
            SOLVERS[w]()
            print(f"   {time.time() - t:.0f}s", flush=True)
    finally:
        esc("stop")
        sh("docker rmi -f shellventure/door:1 shellventure/slim:1 shellventure/web:1 shellventure/health:1")
        shutil.rmtree(HOME, ignore_errors=True)
    print(f"\n{'ALL HEAVY ROOMS OPEN' if not fails else str(len(fails)) + ' FAILURE(S)'}  ({time.time() - t0:.0f}s)")
    for f in fails:
        print("\n✘ " + f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
