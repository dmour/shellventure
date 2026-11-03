#!/usr/bin/env python3
"""Solve every offline room with real commands, in a throwaway HOME. Exit 1 on any failure.

  python3 tests/solve_all.py              all offline worlds
  python3 tests/solve_all.py git linux    only these
Worlds that need kind/docker/gcloud are skipped (they need a real cluster/daemon).
"""
import ipaddress, json, os, re, shutil, site, subprocess, sys, tempfile
from pathlib import Path

ENGINE = Path(os.environ.get("SHELLVENTURE_PY", Path(__file__).resolve().parent.parent / "shellventure" / "shellventure.py"))
HOME = Path(tempfile.mkdtemp(prefix="shellventure-test-"))
ENV = dict(os.environ, HOME=str(HOME), SHELLVENTURE_HOME=str(HOME / ".shellventure"), GIT_CONFIG_GLOBAL="/dev/null",
           GIT_CONFIG_NOSYSTEM="1", TERM="dumb", COLUMNS="100",
           # the fake HOME hides `pip install --user` packages (rich): keep the real user site on the path
           PYTHONPATH=os.pathsep.join(filter(None, [site.getusersitepackages(), os.environ.get("PYTHONPATH")])))
ENV.pop("SHELLVENTURE_WORLDS", None)
ROOM = HOME / "shellventure-lab"
fails = []


def sh(cmd, cwd):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, env=ENV, executable="/bin/bash").stdout.strip()


def esc(*args, world=None):
    env = dict(ENV, **({"SHELLVENTURE_WORLD": world} if world else {}))
    return subprocess.run([sys.executable, str(ENGINE), *args], capture_output=True, text=True, env=env).stdout


def check(world, room, answer=None, expect=True):
    out = esc("_check", *([answer] if answer is not None else []), world=world)
    ok = ("OPENED" in out or "opened!" in out)
    label = f"{world} room {room}" + (" (wrong answer)" if not expect else "")
    if ok != expect:
        fails.append(f"{label}: expected {'open' if expect else 'locked'}, answer={answer!r}\n{out[-400:]}")
    print(f"  {'✔' if ok == expect else '✘'} {label}")


def d(world, sub=""):
    return ROOM / world / sub


# ---- solvers: one function per world, using the hints' commands ----
def bash():
    check("bash", 1, "definitely-wrong", expect=False)
    check("bash", 1, sh("find . -type f -name '.*' -exec cat {} + | grep KEY= | cut -d= -f2", d("bash", "1-haystack")))
    check("bash", 2, sh("awk '$9==500 {print $1}' access.log | sort | uniq -c | sort -rn | head -1 | awk '{print $2}'", d("bash", "2-noisy-log")))
    sh("sed -i 's/\\r$//' open-door.sh && sed -i '1s|.*|#!/bin/bash|' open-door.sh && chmod +x open-door.sh", d("bash", "3-broken-script"))
    check("bash", 3)
    check("bash", 4, sh("jq -r '.floors[]|select(.floor==3).doors[]|select(.locked==false and .color==\"blue\").id' vault.json", d("bash", "4-json-vault")))


def git():
    check("git", 1, "nope-00", expect=False)
    check("git", 1, sh("git log -S 'code =' -p -- config.ini | grep '^+code' | head -1 | awk '{print $3}'", d("git", "1-lost-commit")))
    check("git", 2, sh("h=$(git reflog | grep 'hide the treasure' | awk '{print $1}' | head -1); git show \"$h:treasure.txt\" | awk '{print $4}'", d("git", "2-deleted-branch")))
    check("git", 3, sh("git blame -L 23,23 --porcelain guard.txt | grep '^author ' | cut -d' ' -f2", d("git", "3-who-did-it")))
    check("git", 4, sh("f=$(git rev-list --max-parents=0 HEAD); git bisect start HEAD $f >/dev/null 2>&1; git bisect run ./test.sh >/dev/null 2>&1; "
                       "git rev-parse --short=7 refs/bisect/bad; git bisect reset >/dev/null 2>&1", d("git", "4-bad-commit")))


def linux():
    check("linux", 1, "1", expect=False)
    check("linux", 1, sh("sort -k3 -nr ps-aux.txt | head -1 | awk '{print $2}'", d("linux", "1-cpu-hog")))
    check("linux", 2, sh("du -s var/* | sort -n | tail -1 | awk '{print $2}' | xargs basename", d("linux", "2-disk-full")))
    check("linux", 3, expect=False)
    sh("chmod +x run.sh && chmod u+r config.env", d("linux", "3-permission-denied"))
    check("linux", 3)
    check("linux", 4, "ExecStart")


def today():
    check("today", 1, "6", expect=False)
    check("today", 1, "0")
    check("today", 2, sh("for f in token-*.jwt; do e=$(cut -d. -f2 $f | tr '_-' '/+' | base64 -d 2>/dev/null | jq -r .email 2>/dev/null); "
                         "[ \"$e\" = null ] && echo $f; done", d("today", "2-missing-claim")))
    check("today", 3, sh("jq -r '.users[] | \"\\(.name) \\(.user[\"auth-provider\"].config[\"client-secret\"])\"' kubeconfig.json | "
                         "while read n s; do echo \"$(printf %s \"$s\" | sha256sum | cut -c1-8) ${n%%-*}\"; done | sort | uniq -c -w8 | awk '$1==1{print $3}'",
                         d("today", "3-odd-secret")))
    check("today", 4, "migrate-job.yaml", expect=False)
    check("today", 4, "database.yaml")


def cicd():
    blocks = re.split(r"\n(?=[a-z][\w-]*:\n)", (d("cicd", "1-which-jobs") / ".gitlab-ci.yml").read_text())
    runs = [m.group(1) for b in blocks for m in [re.match(r"([a-z][\w-]*):\n", b)]
            if m and m.group(1) != "stages" and ("merge_request_event" in b or "when: always" in b)]
    check("cicd", 1, "build", expect=False)
    check("cicd", 1, " ".join(runs))
    check("cicd", 2, sh("grep -oE \"needs '[a-z-]+'\" error.txt | cut -d\"'\" -f2", d("cicd", "2-stuck-pipeline")))
    check("cicd", 3, sh("grep -A1 '&py' .gitlab-ci.yml | tail -1 | awk '{print $2}'", d("cicd", "3-anchors")), expect=False)
    check("cicd", 3, sh("grep -A1 '&defaults' .gitlab-ci.yml | sed -n 2p | awk '{print $2}'", d("cicd", "3-anchors")))
    check("cicd", 4, sh("grep 'debug: env' job.log | sed -E 's/.*env ([A-Z_]+)=.*/\\1/'", d("cicd", "4-leaked-secret")))


def terraform():
    check("terraform", 1, sh("grep 'must be replaced' plan.txt | awk '{print $2}'", d("terraform", "1-destroy-alert")))
    s = json.loads((d("terraform", "2-drift") / "terraform.tfstate").read_text())["resources"][0]["instances"][0]["attributes"]
    c = dict(re.findall(r'(\w+) = "([^"]+)"', (d("terraform", "2-drift") / "main.tf").read_text()))
    check("terraform", 2, [a for a in c if c[a] != s[a]][0])
    b = json.loads(re.search(r"default = (\[.*\])", (d("terraform", "3-count-trap") / "before.tf").read_text()).group(1))
    a = json.loads(re.search(r"default = (\[.*\])", (d("terraform", "3-count-trap") / "after.tf").read_text()).group(1))
    check("terraform", 3, "1", expect=False)
    check("terraform", 3, str(sum(1 for i in range(len(b)) if i >= len(a) or a[i] != b[i])))
    check("terraform", 4, sh("grep 'ID:' error.txt | awk '{print $2}'", d("terraform", "4-locked-state")))


def observability():
    check("observability", 1, sh("awk 'NR==2{e1=$2;t1=$3}NR==3{e2=$2;t2=$3}END{printf \"%g\", (e2-e1)/((t2-t1)/1000)}' samples.txt", d("observability", "1-error-rate")))
    check("observability", 2, "for")
    check("observability", 3, "2.5", expect=False) if sh("grep -c 'le=\"2.5\"} 1000' histogram.txt", d("observability", "3-p99")) == "1" and \
        sh("awk -F'\"' '/le=\"[0-9.]+\"/{split($3,a,\" \"); if (a[2]+0>=990 && !f){print $2; f=1}}' histogram.txt", d("observability", "3-p99")) != "2.5" else None
    check("observability", 3, sh("awk -F'\"' '/le=\"[0-9.]+\"/{split($3,a,\" \"); if (a[2]+0>=990 && !f){print $2; f=1}}' histogram.txt", d("observability", "3-p99")))
    check("observability", 4, sh("jq -r '.data.activeTargets[] | select(.health==\"down\").labels.job' targets.json", d("observability", "4-target-down")))


def security():
    check("security", 1, sh("jq -r '.Results[0].Vulnerabilities[] | select(.Severity==\"CRITICAL\" and .FixedVersion==\"\").PkgName' scan.json", d("security", "1-cve-hunt")), expect=False)
    check("security", 1, sh("jq -r '.Results[0].Vulnerabilities[] | select(.Severity==\"CRITICAL\" and .FixedVersion!=\"\").PkgName' scan.json", d("security", "1-cve-hunt")))
    check("security", 2, sh("git log -p | grep -o 'AKIA[A-Z0-9]*' | head -1", d("security", "2-secret-history")))
    sa = sh("r=$(jq -r '.items[] | select(.kind==\"ClusterRole\" and (.rules[0].resources|index(\"secrets\")) and (.rules[0].verbs|index(\"delete\"))).metadata.name' rbac.json); "
            "jq -r --arg r \"$r\" '.items[] | select(.kind==\"ClusterRoleBinding\" and .roleRef.name==$r).subjects[0].name' rbac.json", d("security", "3-too-much-power"))
    check("security", 3, sa)
    check("security", 4, expect=False)
    sh("sed -i 's|^CMD|USER app\\nCMD|' Dockerfile", d("security", "4-root-container"))
    check("security", 4)


def web():
    conf = (d("web", "1-location-order") / "nginx.conf").read_text(); uri = (d("web", "1-location-order") / "request.txt").read_text().split()[1]
    ans = "health_check" if f"= {uri}" in conf else ("api_v1" if "^~" in conf else "static_files")
    check("web", 1, "frontend", expect=False)
    check("web", 1, ans)
    pp = (d("web", "2-proxy-slash") / "nginx.conf").read_text(); page = (d("web", "2-proxy-slash") / "request.txt").read_text().split()[1]
    check("web", 2, page.replace("/api", "", 1) if ":8080/;" in pp else page)
    check("web", 3, sh("awk '$9==504' access.log | grep -o 'upstream=[a-z]*' | sort | uniq -c | sort -rn | head -1 | sed 's/.*=//'", d("web", "3-gateway-errors")))
    check("web", 4, sh("grep -A1 'default_server' sites.conf | grep -o 'server_name [a-z]*' | awk '{print $2}'", d("web", "4-wrong-host")))


SOLVERS = {"bash": bash, "git": git, "linux": linux, "today": today, "cicd": cicd, "terraform": terraform,
           "observability": observability, "security": security, "web": web}


def main():
    want = sys.argv[1:] or list(SOLVERS)
    try:
        for w in want:
            print(f"== {w}")
            esc("reset", w)
            if not (ROOM / w).exists():
                fails.append(f"{w}: world did not build"); continue
            SOLVERS[w]()
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
    print(f"\n{'ALL ROOMS OPEN' if not fails else str(len(fails)) + ' FAILURE(S)'}")
    for f in fails:
        print("\n✘ " + f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
