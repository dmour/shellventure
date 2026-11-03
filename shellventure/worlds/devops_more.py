"""More DevOps worlds, all offline (only bash/coreutils/jq): Linux Lab, CI/CD Factory, Terraform Town, Observability Hill.
Every puzzle is generated with random values, so each reset is a new game."""
import json, os, random, shutil


def make(api):
    code, h = api.code, api.h

    def fresh(d):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    def answer_check(n):  # typed answer compared to the stored hash (exact, case-insensitive)
        def chk(d, w, arg):
            return api.h(arg or "") == w["answers"][str(n)], "Not this one. Look again."
        return chk

    def set_check(n, wrong="Not the right set of jobs."):  # several words, any order
        def chk(d, w, arg):
            got = sorted(set((arg or "").replace(",", " ").lower().split()))
            return api.h(" ".join(got)) == w["answers"][str(n)], wrong
        return chk

    # ================================================================ LINUX LAB
    def linux_setup(d, w):
        fresh(d)
        # 1. CPU hog in a ps snapshot
        r = d / "1-cpu-hog"; r.mkdir()
        procs = [("root", "systemd"), ("www", "nginx"), ("app", "java"), ("app", "node"), ("pg", "postgres"),
                 ("root", "sshd"), ("app", "python3"), ("root", "containerd"), ("app", "ruby"), ("root", "kubelet")]
        hog = random.choice(procs[2:])
        lines = ["USER       PID %CPU %MEM    VSZ   RSS TTY  STAT START   TIME COMMAND"]
        for u, c in procs * 3:
            cpu = round(random.uniform(0, 9), 1)
            lines.append(f"{u:<9}{random.randint(100, 32000):>6} {cpu:>4} {random.uniform(0, 5):>4.1f} "
                         f"{random.randint(1000, 900000):>7} {random.randint(100, 90000):>6} ?    Ssl  09:{random.randint(10, 59)}   0:{random.randint(1, 59):02d} {c}")
        pid = random.randint(32001, 39999)
        lines.insert(random.randint(1, len(lines)), f"{hog[0]:<9}{pid:>6} 97.3 12.1 4194304 1048576 ?    Rl   09:12  88:41 {hog[1]}")
        (r / "ps-aux.txt").write_text("\n".join(lines) + "\n")
        w["answers"]["1"] = h(str(pid))
        # 2. disk full: which directory is biggest
        r = d / "2-disk-full"; r.mkdir()
        dirs = ["logs", "cache", "backups", "uploads", "tmp", "builds"]
        big = random.choice(dirs)
        for x in dirs:
            p = r / "var" / x; p.mkdir(parents=True)
            for i in range(random.randint(2, 6)):
                kb = random.randint(10, 120) if x != big else random.randint(400, 700)
                (p / f"f{i}.bin").write_bytes(os.urandom(kb * 1024))
        w["answers"]["2"] = h(big)
        # 3. permission denied: make ./run.sh work
        r = d / "3-permission-denied"; r.mkdir()
        secret = code()
        (r / "config.env").write_text(f"DOOR={secret}\n")
        (r / "run.sh").write_text('#!/bin/sh\n. ./config.env || exit 1\necho "door: $DOOR"\n')
        os.chmod(r / "run.sh", 0o644); os.chmod(r / "config.env", 0o000)
        w["data"]["linux3"] = h(secret)
        # 4. broken systemd unit
        r = d / "4-broken-unit"; r.mkdir()
        (r / "app.service").write_text("[Unit]\nDescription=payments app\nAfter=network.target\n\n[Service]\n"
                                        "User=app\nWorkingDirectory=/opt/app\nExecStart=app --port 8080\nRestart=always\n\n[Install]\nWantedBy=multi-user.target\n")
        (r / "journal.txt").write_text("systemd[1]: /etc/systemd/system/app.service:8: Executable \"app\" not found in path, ignoring.\n"
                                       "systemd[1]: app.service: Unit configuration has fatal error, unit will not be started.\n")

    def linux3(d, w, _):
        import subprocess
        p = d / "3-permission-denied"
        if not os.access(p / "run.sh", os.X_OK):
            return False, "run.sh is not executable."
        r = subprocess.run(["./run.sh"], cwd=p, capture_output=True, text=True)
        got = r.stdout.strip().removeprefix("door: ")
        return api.h(got) == w["data"]["linux3"], "./run.sh still cannot read its config."

    LINUX = {"title": "Linux Lab", "dir": "linux", "setup": linux_setup, "skill": "linux", "needs": ["sort", "du"], "rooms": [
        {"name": "The CPU Hog", "dir": "1-cpu-hog", "check": answer_check(1), "typed": True,
         "story": "The server is slow. Someone saved [bold]ps aux[/] before it froze.",
         "task": "Which [bold]PID[/] is eating the CPU? Type it.",
         "hints": ["%CPU is the 3rd column.", "`sort -k3 -nr ps-aux.txt | head -3`", "The top line after sorting by column 3 is the hog: type its PID (column 2)."]},
        {"name": "Disk Full", "dir": "2-disk-full", "check": answer_check(2), "typed": True,
         "story": "[bold]No space left on device.[/] Find what is filling the disk.",
         "task": "Which folder under var/ uses the most space? Type its name.",
         "hints": ["du shows disk usage.", "`du -sh var/*`", "`du -s var/* | sort -n | tail -1`"]},
        {"name": "Permission Denied", "dir": "3-permission-denied", "check": linux3,
         "story": "[bold]./run.sh: Permission denied[/]. Then it cannot read its config either.",
         "task": "Make [bold]./run.sh[/] run and print the door code. I check after every command.",
         "hints": ["`ls -l` shows the permission bits.", "run.sh needs x (execute), config.env needs r (read).",
                   "`chmod +x run.sh && chmod u+r config.env`"]},
        {"name": "The Broken Unit", "dir": "4-broken-unit", "check": answer_check(4), "typed": True,
         "story": "The service never starts. The journal has the clue.",
         "task": "Which [bold]key[/] in app.service is wrong? Type the key name (left of =).",
         "hints": ["Read journal.txt: which line number?", "Line 8 of app.service.", "systemd needs an absolute path: ExecStart=/opt/app/app ..."]},
    ]}
    LINUX_ANS4 = "execstart"

    # ================================================================ CI/CD FACTORY
    def cicd_setup(d, w):
        fresh(d)
        # 1. which jobs run on an MR pipeline
        r = d / "1-which-jobs"; r.mkdir()
        jobs = {"build": "always", "lint": "mr", "unit-tests": "mr", "deploy-prod": "main", "nightly-e2e": "schedule",
                "docs": "main", "security-scan": "mr_or_main"}
        picked = random.sample(list(jobs), 6)
        y = ["stages: [build, test, deploy]", ""]
        rule = {"always": ["    - when: always"],
                "mr": ['    - if: $CI_PIPELINE_SOURCE == "merge_request_event"'],
                "main": ['    - if: $CI_COMMIT_BRANCH == "main"'],
                "schedule": ['    - if: $CI_PIPELINE_SOURCE == "schedule"'],
                "mr_or_main": ['    - if: $CI_PIPELINE_SOURCE == "merge_request_event"', '    - if: $CI_COMMIT_BRANCH == "main"']}
        for j in picked:
            y += [f"{j}:", f"  stage: {'build' if j == 'build' else 'deploy' if 'deploy' in j else 'test'}", "  script: [./ci.sh " + j + "]", "  rules:"] + rule[jobs[j]] + [""]
        (r / ".gitlab-ci.yml").write_text("\n".join(y))
        (r / "event.txt").write_text("A developer opens a MERGE REQUEST from branch feature/login into main.\n"
                                     "CI_PIPELINE_SOURCE=merge_request_event\nCI_COMMIT_BRANCH is NOT set in MR pipelines.\n")
        runs = sorted(j for j in picked if jobs[j] in ("always", "mr", "mr_or_main"))
        w["answers"]["1"] = h(" ".join(runs))
        # 2. stuck pipeline: needs points to a job that does not exist in this pipeline
        r = d / "2-stuck-pipeline"; r.mkdir()
        ghost = random.choice(["build-image", "compile", "package"])
        (r / ".gitlab-ci.yml").write_text(
            "stages: [build, test, deploy]\n\nbuild:\n  stage: build\n  script: [make]\n\n"
            f"test:\n  stage: test\n  needs: [build]\n  script: [make test]\n\n"
            f"deploy:\n  stage: deploy\n  needs: [test, {ghost}]\n  script: [./deploy.sh]\n")
        (r / "error.txt").write_text(f"This GitLab CI configuration is invalid: 'deploy' job needs '{ghost}' job, but '{ghost}' is not in any previous stage\n")
        w["answers"]["2"] = h(ghost)
        # 3. YAML anchors: final image of a job
        r = d / "3-anchors"; r.mkdir()
        imgs = [f"python:3.{v}" for v in range(9, 14)]
        base, over = random.sample(imgs, 2)
        (r / ".gitlab-ci.yml").write_text(
            f".defaults: &defaults\n  image: {base}\n  tags: [docker]\n  retry: 2\n\n"
            f".py-overrides: &py\n  image: {over}\n\n"
            "unit:\n  <<: [*defaults, *py]\n  script: [pytest]\n\n"
            "lint:\n  <<: *defaults\n  script: [ruff check .]\n")
        # YAML merge: with a list, the FIRST map wins for duplicate keys
        w["answers"]["3"] = h(base)
        # 4. leaked secret in a job log
        r = d / "4-leaked-secret"; r.mkdir()
        names = ["DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "SLACK_TOKEN", "NPM_TOKEN", "REGISTRY_PASSWORD"]
        leaked = random.choice(names)
        log = ["$ ./deploy.sh", "Connecting to registry...", "Using DB_PASSWORD=[MASKED]", "Using SLACK_TOKEN=[MASKED]"]
        log = [l for l in log if leaked not in l] + [f"debug: env {leaked}={code()}{code()}"] + \
              [f"Using {n}=[MASKED]" for n in names if n not in (leaked, "DB_PASSWORD", "SLACK_TOKEN")]
        random.shuffle(log)
        (r / "job.log").write_text("\n".join(log) + "\nJob succeeded\n")
        w["answers"]["4"] = h(leaked)

    CICD = {"title": "CI/CD Factory", "dir": "cicd", "setup": cicd_setup, "skill": "cicd", "rooms": [
        {"name": "Which Jobs Run?", "dir": "1-which-jobs", "check": set_check(1), "typed": True,
         "story": "A merge request pipeline starts. Some jobs run, some are skipped by their [bold]rules[/].",
         "task": "Type ALL job names that run, separated by spaces (any order).",
         "hints": ["Read event.txt: what is set, and what is NOT set in an MR pipeline?",
                   "Rules match top to bottom; no match = job not added.",
                   "In MR pipelines only CI_PIPELINE_SOURCE == merge_request_event and `when: always` jobs match."]},
        {"name": "The Stuck Pipeline", "dir": "2-stuck-pipeline", "check": answer_check(2), "typed": True,
         "story": "The pipeline will not even start: [bold]invalid configuration[/].",
         "task": "Which job name is missing? Type it.",
         "hints": ["Read error.txt.", "needs: can only point to jobs that exist.", "The job in deploy's needs that has no definition."]},
        {"name": "The Anchor Puzzle", "dir": "3-anchors", "check": answer_check(3), "typed": True,
         "story": "Two anchors are merged into one job. Which [bold]image[/] wins?",
         "task": "Which image does the [bold]unit[/] job use? Type it (like python:3.12).",
         "hints": ["`<<: [*a, *b]` merges a list of maps.", "For a duplicate key, the FIRST map in the list wins.",
                   "unit gets image from *defaults (listed first)."]},
        {"name": "The Leaky Log", "dir": "4-leaked-secret", "check": answer_check(4), "typed": True,
         "story": "A job printed its environment. One secret was not masked.",
         "task": "Which variable [bold]leaked[/]? Type its name.",
         "hints": ["Masked values show [MASKED].", "`grep -v MASKED job.log`", "The variable printed with its real value."]},
    ]}

    # ================================================================ TERRAFORM TOWN
    def tf_setup(d, w):
        fresh(d)
        # 1. which resource will be destroyed (replacement)
        r = d / "1-destroy-alert"; r.mkdir()
        res = ["aws_instance.web", "aws_db_instance.main", "aws_s3_bucket.assets", "aws_lb.front", "aws_iam_role.ci"]
        victim = random.choice(res)
        plan = ["Terraform will perform the following actions:", ""]
        for x in res:
            if x == victim:
                plan += [f"  # {x} must be replaced", f"-/+ resource \"{x.split('.')[0]}\" \"{x.split('.')[1]}\" {{",
                         "      ~ engine_version = \"14.7\" -> \"16.2\" # forces replacement", "    }", ""]
            elif random.random() < .5:
                plan += [f"  # {x} will be updated in-place", f"  ~ resource \"{x.split('.')[0]}\" \"{x.split('.')[1]}\" {{",
                         "      ~ tags = { \"team\" = \"ops\" -> \"platform\" }", "    }", ""]
        plan.append("Plan: 1 to add, 2 to change, 1 to destroy.")
        (r / "plan.txt").write_text("\n".join(plan) + "\n")
        w["answers"]["1"] = h(victim)
        # 2. drift: which attribute changed outside terraform
        r = d / "2-drift"; r.mkdir()
        attrs = {"instance_type": ("t3.small", "t3.xlarge"), "monitoring": ("false", "true"), "ami": ("ami-0a1b2c", "ami-9z8y7x"),
                 "ebs_optimized": ("false", "true")}
        k = random.choice(list(attrs))
        code_tf = "resource \"aws_instance\" \"web\" {\n" + "".join(f"  {a} = \"{v[0]}\"\n" for a, v in attrs.items()) + "}\n"
        state = {"resources": [{"type": "aws_instance", "name": "web", "instances": [{"attributes":
                 {a: (v[1] if a == k else v[0]) for a, v in attrs.items()}}]}]}
        (r / "main.tf").write_text(code_tf); (r / "terraform.tfstate").write_text(json.dumps(state, indent=2))
        w["answers"]["2"] = h(k)
        # 3. count index trap
        r = d / "3-count-trap"; r.mkdir()
        users = random.sample(["alex", "sam", "kim", "lee", "max", "ava", "noah"], 6)
        gone = random.randint(0, 3)
        (r / "before.tf").write_text(f"variable \"users\" {{ default = {json.dumps(users)} }}\n"
                                     "resource \"aws_iam_user\" \"u\" {\n  count = length(var.users)\n  name  = var.users[count.index]\n}\n")
        new = users[:gone] + users[gone + 1:]
        (r / "after.tf").write_text(f"variable \"users\" {{ default = {json.dumps(new)} }}\n"
                                    "resource \"aws_iam_user\" \"u\" {\n  count = length(var.users)\n  name  = var.users[count.index]\n}\n")
        # every index from `gone` up changes name (replace), and the last index is destroyed
        w["answers"]["3"] = h(str(len(users) - gone))
        # 4. locked state
        r = d / "4-locked-state"; r.mkdir()
        lid = f"{random.randint(10**7, 10**8):x}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(10**11, 10**12):x}"
        (r / "error.txt").write_text("Error: Error acquiring the state lock\n\nLock Info:\n"
                                     f"  ID:        {lid}\n  Path:      tf-state/prod/terraform.tfstate\n  Operation: OperationTypeApply\n"
                                     "  Who:       ci-runner@runner-7\n  Created:   2026-11-01 03:12:44 (the CI job was killed)\n")
        w["answers"]["4"] = h(lid)

    TF = {"title": "Terraform Town", "dir": "terraform", "setup": tf_setup, "skill": "iac", "rooms": [
        {"name": "Destroy Alert", "dir": "1-destroy-alert", "check": answer_check(1), "typed": True,
         "story": "The plan says [bold]1 to destroy[/]. Before you type yes: what dies?",
         "task": "Which resource address will be destroyed and created again? (like aws_x.name)",
         "hints": ["Look for -/+ and 'must be replaced'.", "`grep -B1 -- '-/+' plan.txt`", "The address in the '# ... must be replaced' line."]},
        {"name": "The Drift", "dir": "2-drift", "check": answer_check(2), "typed": True,
         "story": "Someone changed the server in the console. Now code and reality differ.",
         "task": "Which attribute [bold]drifted[/]? Type its name.",
         "hints": ["Compare main.tf with terraform.tfstate.", "`jq '.resources[0].instances[0].attributes' terraform.tfstate`",
                   "The one attribute whose state value differs from main.tf."]},
        {"name": "The Count Trap", "dir": "3-count-trap", "check": answer_check(3), "typed": True,
         "story": "You removed ONE user from a list. The plan wants to touch many more.",
         "task": "How many aws_iam_user resources will be [bold]changed or destroyed[/]? Type the number.",
         "hints": ["count tracks items by POSITION (index), not by name.", "Every item after the removed one moves up one index.",
                   "From the removed index to the old end: all of them. (for_each would avoid this.)"]},
        {"name": "The Locked State", "dir": "4-locked-state", "check": answer_check(4), "typed": True,
         "story": "A CI job died during apply. Now every plan fails: [bold]state lock[/].",
         "task": "Type the lock ID you would give to `terraform force-unlock`.",
         "hints": ["Read error.txt.", "Lock Info has an ID line.", "`grep ID error.txt`"]},
    ]}

    # ================================================================ OBSERVABILITY HILL
    def obs_setup(d, w):
        fresh(d)
        # 1. error rate from two counter samples
        r = d / "1-error-rate"; r.mkdir()
        t0, dt = 1700000000, random.choice([60, 120, 300])
        e0 = random.randint(1000, 9000); de = random.choice([3, 6, 12, 30]) * dt // 6
        (r / "samples.txt").write_text(f"# TYPE http_requests_errors_total counter\n"
                                       f"http_requests_errors_total{{job=\"api\"}} {e0} {t0}000\n"
                                       f"http_requests_errors_total{{job=\"api\"}} {e0 + de} {t0 + dt}000\n")
        w["answers"]["1"] = h(f"{de / dt:g}")
        # 2. flapping alert: which field
        r = d / "2-flapping-alert"; r.mkdir()
        (r / "alert.yaml").write_text("groups:\n- name: api\n  rules:\n  - alert: HighLatency\n    expr: histogram_quantile(0.99, rate(http_duration_seconds_bucket[1m])) > 0.5\n"
                                      "    for: 0s\n    labels: {severity: page}\n")
        (r / "pager.txt").write_text("02:01 FIRING HighLatency\n02:01 RESOLVED\n02:02 FIRING HighLatency\n02:02 RESOLVED\n02:03 FIRING ... (40 pages tonight)\n")
        # 3. p99 bucket
        r = d / "3-p99"; r.mkdir()
        les = [0.05, 0.1, 0.25, 0.5, 1, 2.5]
        total = 1000
        k = random.randint(1, 4)                       # bucket index where 99% is first reached
        below = sorted(random.sample(range(200, 989), k))
        above = sorted(random.sample(range(990, 1000), len(les) - k - 1)) + [total]
        cum = below + above
        lines = ["# TYPE http_duration_seconds histogram"]
        for le, v in zip(les, cum):
            lines.append(f'http_duration_seconds_bucket{{le="{le}"}} {v}')
        lines.append(f'http_duration_seconds_bucket{{le="+Inf"}} {total}')
        (r / "histogram.txt").write_text("\n".join(lines) + "\n")
        p99 = next(le for le, v in zip(les, cum) if v >= 990)
        w["answers"]["3"] = h(f"{p99:g}")
        # 4. which target is down
        r = d / "4-target-down"; r.mkdir()
        jobs = ["api", "worker", "postgres-exporter", "redis-exporter", "node", "blackbox"]
        bad = random.choice(jobs)
        tg = {"data": {"activeTargets": [{"labels": {"job": j}, "scrapeUrl": f"http://{j}:9{random.randint(100, 999)}/metrics",
                                          "health": "down" if j == bad else "up",
                                          "lastError": "connection refused" if j == bad else ""} for j in jobs]}}
        (r / "targets.json").write_text(json.dumps(tg, indent=1))
        w["answers"]["4"] = h(bad)

    OBS = {"title": "Observability Hill", "dir": "observability", "setup": obs_setup, "skill": "observability", "needs": ["jq"], "rooms": [
        {"name": "The Error Rate", "dir": "1-error-rate", "check": answer_check(1), "typed": True,
         "story": "Two samples of an error [bold]counter[/]. The boss asks: how many errors per second?",
         "task": "Type the rate: (value2 - value1) / seconds between them. (timestamps are in ms)",
         "hints": ["A counter only goes up; rate = difference / time.", "The last number on each line is a timestamp in milliseconds.",
                   "(e2 - e1) / ((t2 - t1) / 1000)"]},
        {"name": "The Flapping Alert", "dir": "2-flapping-alert", "check": lambda d, w, a: ((a or "").strip().lower() in ("for", "for:"), "Not that field."), "typed": True,
         "story": "40 pages in one night: firing, resolved, firing, resolved...",
         "task": "Which [bold]field[/] in alert.yaml should change so short spikes do not page? Type the field name.",
         "hints": ["The alert fires the very second the expression is true.", "Prometheus can wait until it has been true for a while.",
                   "`for: 0s` -> for: 5m"]},
        {"name": "The p99 Bucket", "dir": "3-p99", "check": answer_check(3), "typed": True,
         "story": "1000 requests. Which bucket holds the [bold]99th percentile[/]?",
         "task": "Type the smallest [bold]le[/] value whose count reaches 99% of all requests.",
         "hints": ["Buckets are CUMULATIVE: each count includes all faster requests.", "99% of 1000 = 990.",
                   "First bucket with a count >= 990."]},
        {"name": "The Silent Target", "dir": "4-target-down", "check": answer_check(4), "typed": True,
         "story": "A dashboard went empty. Prometheus is up, but one target is not.",
         "task": "Which [bold]job[/] is down? Type its name.",
         "hints": ["`jq '.data.activeTargets[] | {job: .labels.job, health}' targets.json`",
                   "Look for health = down.", "`jq -r '.data.activeTargets[] | select(.health==\"down\").labels.job' targets.json`"]},
    ]}

    # Linux room 4 has a fixed answer
    orig = linux_setup
    def linux_setup2(d, w):
        orig(d, w); w["answers"]["4"] = h(LINUX_ANS4)
    LINUX["setup"] = linux_setup2
    return {"linux": LINUX, "cicd": CICD, "terraform": TF, "observability": OBS}
