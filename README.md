# ▓▒░ SHELLVENTURE ░▒▓

![test](https://github.com/dmour/shellventure/actions/workflows/test.yml/badge.svg)

**A terminal adventure for real DevOps skills.** Your shell is the sword: every world is an escape room you fix your way out of.
Every room is a real, broken system on your machine. You fix it with real commands: `grep`, `git`, `kubectl`, `helm`, `docker`, `jq`, `psql`, `openssl`...
No multiple choice, no videos. *Break nothing real. Fix everything fake.*

![Shellventure demo: find the hidden key, the door opens, +15 XP, then the menu and your skill profile](docs/demo.gif)

## What is Shellventure?

Shellventure is a game you play **in your own terminal**. It builds small, broken systems in a folder on your
machine: a log full of errors, a git repo with a lost commit, an nginx config that sends traffic to the wrong place,
a Kubernetes pod that keeps crashing. Each one is a **room**. You fix the room with the same commands you use at
work, and the door opens.

- **Who it is for:** anyone learning or practicing Linux, Git, CI/CD, Kubernetes, cloud and SRE work. Beginners
  start in Bash Dungeon; the Boss Fight is hard even for seniors.
- **Why it works:** you learn by doing, not by watching. Every reset makes **new random puzzles**, so you can replay.
- **Safe:** everything happens in `~/shellventure-lab` and a private local cluster. Your real repos, clusters and
  cloud accounts are never touched.
- **Short sessions:** one room takes 2-10 minutes. A daily puzzle takes 5.

## Requirements

**Operating system**

| OS | Status |
|---|---|
| Linux (Ubuntu, Debian, Fedora...) | ✅ tested (Ubuntu 26.04, Debian 13 with Python 3.9) |
| Android: Termux (F-Droid) + Debian proot | ✅ tested, offline worlds only (no docker on a phone) |
| Windows | ⚠️ use **WSL2** with Ubuntu; it should work like Linux, but it is not tested yet |
| macOS | ⚠️ not tested yet. Install GNU tools first: `brew install coreutils gnu-sed jq git` |

**Always needed**

| Tool | Why | Check |
|---|---|---|
| Python **3.9+** | the game | `python3 --version` |
| `bash` | the game shell inside each room | `bash --version` |
| `rich` (Python library) | colors and menus; `install.sh` adds it | `python3 -c "import rich"` |
| Normal Linux tools: `grep`, `awk`, `sed`, `find`, `sort`, `base64` | you solve rooms with them | already on Linux |

**Needed per world** (the game shows "needs: ..." for anything missing, the other worlds still work)

| World | Needs |
|---|---|
| Linux Lab, CI/CD Factory, Terraform Town, Web Street, Daily puzzle | nothing extra |
| Bash Dungeon, Today's Bugs, Observability Hill | `jq` |
| Git Temple | `git` |
| Security Gate | `git`, `jq` |
| Docker Docks, SQL Vault | `docker` (SQL Vault runs Postgres in a container: no local Postgres needed) |
| Kube Castle, CKA Dojo, Boss Fight | `docker`, `kind`, `kubectl` |
| Helm Harbor | `docker`, `kind`, `kubectl`, `helm` 3 |
| It's Always DNS | `docker`, `kind`, `kubectl`, `openssl` |
| Cloud Tower | `gcloud` (Google Cloud CLI). No Google account needed: it runs offline on its own config |

Tested with kind 0.27, kubectl 1.35, helm 3.16, docker 27. The Kubernetes worlds need about **4 GB free RAM** and
**3 GB disk** (the first run downloads kindest/node, nginx, busybox and postgres images).

**Install the tools (Ubuntu / Debian / WSL2)**

```bash
sudo apt install python3 python3-pip git jq openssl     # enough for 10 worlds
```

For the heavy worlds, follow the official guides: [Docker](https://docs.docker.com/engine/install/),
[kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation),
[kubectl](https://kubernetes.io/docs/tasks/tools/), [Helm](https://helm.sh/docs/intro/install/),
[gcloud](https://cloud.google.com/sdk/docs/install).

## Setup

**1. Check what you have:** `./install.sh` (step 2) prints ✔ for every tool it finds and · for the missing ones.

**2. Install**

```bash
git clone https://github.com/dmour/shellventure.git
cd shellventure
./install.sh
```

The installer adds the `rich` library if it is missing, puts `shellventure` and the short name `sv` in
`~/.local/bin`, and lists which optional tools you have (✔) and which are missing (·).

**3. Start**

```bash
sv
```

If `sv` is not found, add `~/.local/bin` to your PATH: `export PATH=$HOME/.local/bin:$PATH` (put it in `~/.bashrc` or `~/.zshrc`).

**Update:** `git pull` in the folder. **Uninstall:** `rm ~/.local/bin/sv ~/.local/bin/shellventure`, then delete
the folder, `~/.shellventure` (XP) and `~/shellventure-lab` (puzzles). `sv stop` first if you played the Kubernetes worlds.

**Phone (Android):** it runs in Termux (F-Droid) with a Debian proot. Install `python3 git jq` and follow the steps above.
Set `SHELLVENTURE_WORLDS=bash,git,linux,today,cicd,terraform,observability,security,web` to show only the offline worlds.

## How to play

**Your first game (about 5 minutes):**

1. Run `sv`. The menu opens.
2. Choose **Worlds**, then **Bash Dungeon** (the easiest).
3. A box shows **Room 1** and what is broken. You are now in a game shell, inside the room's folder.
4. Look around with normal commands: `ls -la`, `cat`, `grep`, `find`...
5. Found the answer? **Just type it** and press Enter. Fixed a broken file? The game sees it after your next command.
6. The door opens, you get XP, and the next room starts. Type `exit` any time: your progress is saved.

**The menu**

| Key | Does |
|---|---|
| `↑ ↓` + `Enter`, or a number | choose |
| `Esc` | back |

The main screen has 6 lines: **Continue** (your last world), **Daily**, **Worlds** (grouped: Foundations, Delivery,
Kubernetes, Operations), **Profile** (level, skill bars, badges, last 7 days), **Settings** (difficulty: easy ·
normal · hard; story mode: *First week as SRE*), **Quit**.

**Inside a room**

| Type | Does |
|---|---|
| your answer, e.g. `falcon-23` | tries it as the answer |
| `check` / `check <answer>` | checks the room now |
| `hint` | a hint for the part you are stuck on (fixed parts show ✔; each hint lowers the room's XP) |
| `room` | shows the room box again |
| `map` | shows all worlds and your progress |
| `exit` | leaves the room, progress saved |

- **Fix-it rooms:** repair the system with normal commands. The game **checks after every command** and opens the door by itself.
- **Answer rooms:** find the answer and **type it** (`10.4.2.1`, `falcon-23`, `ExecStart`...).
- The room's **name, task, time and hints left stay pinned at the top** while your output scrolls below
  (small screens get a thin bar above the prompt instead).
- **Smart hints:** rooms with several problems know what you already fixed. `hint` shows ✔ for the fixed parts
  and only helps with the first part that is still broken.

**Without the menu**

```bash
sv play git         # go straight into a world (keys: bash git linux today cicd terraform observability
                    #   security web k8s gcloud helm cka docker sql network boss)
sv daily            # today's 5-minute puzzle
sv reset git        # rebuild a world with new puzzles
sv map              # all worlds and your progress
sv stop             # delete the local kind cluster and game containers
```

**Tips:** start with Bash Dungeon, Git Temple and Linux Lab. Try without hints first: fewer hints = more XP.
Stuck for 10 minutes? Take one hint, not three.

## Worlds

| World | Skill | You learn | Needs |
|---|---|---|---|
| 🧩 Daily puzzle | linux | one 5-minute puzzle a day: cron, subnets, base64, jq, git history | - |
| Bash Dungeon | linux | `find`, `awk`/`sort`/`uniq`, CRLF + shebang bugs, `jq` | jq |
| Git Temple | git | `log -S`, `reflog`, `blame`, `bisect` | git |
| Linux Lab | linux | CPU hogs in `ps`, disk full (`du`), permissions, systemd units | - |
| Today's Bugs | troubleshooting | the "6 namespaces" trap, JWT claims, odd secrets, Helm hooks that wipe data | jq |
| CI/CD Factory | cicd | `rules` (which jobs run), `needs`, YAML anchors, leaked secrets in logs | - |
| Terraform Town | iac | plans that destroy, drift, the `count` index trap, state locks | - |
| Observability Hill | observability | counter rates, flapping alerts, p99 from histograms, dead targets | jq |
| Security Gate | security | CVE reports, secrets in git history, RBAC that is too wide, root containers | git, jq |
| Web Street | web | nginx location order, the proxy_pass slash, 502 vs 504, default_server | - |
| Kube Castle | kubernetes | ImagePullBackOff, secret keys, selectors, OOMKilled, quotas + probes | kind, docker, kubectl |
| Cloud Tower | cloud | gcloud configurations, proxies, `--filter` (offline, your real gcloud is untouched) | gcloud |
| Helm Harbor | kubernetes | broken templates, rollback, values-only switches, failing hooks | kind, docker, kubectl, helm |
| Docker Docks | containers | `.dockerignore`, fat layers, published ports, healthchecks | docker |
| SQL Vault | databases | `GROUP BY`/`HAVING`, indexes, lock hunting, joins, stuck sequences | docker |
| It's Always DNS | networking | cross-namespace DNS, TLS SANs, key/cert match, port-forward, Host headers | kind, docker, kubectl, openssl |
| CKA Dojo | kubernetes | one room per CKA exam area: nodeSelector, CPU requests, RBAC, PVC + StorageClass, NetworkPolicy, etcd snapshot | kind, docker, kubectl |
| Boss Fight | kubernetes | 3 random faults at once, with a timer | kind, docker, kubectl |

The Kubernetes worlds run on a **private local kind cluster** with its own kubeconfig: your real clusters are never touched.
`shellventure stop` deletes that cluster and the game's containers.

## XP, levels and skills

- Rooms give XP (fewer hints = more XP), finishing a world gives a bonus, badges give extra.
- Every world trains one of **13 skills**: linux, git, kubernetes, containers, databases, networking, cloud, cicd, iac, observability, security, web, troubleshooting.
- 12 ranks from *Intern* to *Infra Legend*. A **work-day streak** counts days you played (Mon-Fri by default; `SHELLVENTURE_WORKDAYS=6,0,1,2,3` for Sun-Thu).
- Data lives in `~/.shellventure` (`SHELLVENTURE_HOME` to move it). Puzzles live in `~/shellventure-lab`.
- **XP is signed.** `xp.json` carries a signature made with a private key (`~/.shellventure/.xp-key`). If the file is
  edited by hand, the game notices, keeps the edited file as `xp.json.tampered-<time>`, and brings back the last good
  copy. One award gives at most 200 XP.

## Tests

`python3 tests/solve_all.py` builds every offline world in a throwaway home, tries wrong answers, then solves every
room with real commands. GitHub Actions runs it on every push.

`python3 tests/solve_heavy.py` does the same for the 8 worlds that need docker, kind or gcloud (about 5 minutes when the
images are pulled). It uses the game's own kind cluster and containers and deletes them at the end.

## Add your own world

Drop a file in `shellventure/worlds/` with `make(api)` returning `{key: world}`. A world is a title, a `setup(dir, state)` that
builds the broken system, and rooms with a `check` (fix-it) or a hashed answer (`"answer": True`) plus 3 hints.
See `worlds/devops_more.py` for small, offline examples.

## License

MIT
