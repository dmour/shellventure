"""CKA Dojo: one room per CKA exam domain (scheduling, RBAC, storage, network policy, etcd backup).

Runs on the game's own kind cluster; each room has its own namespace, so other worlds are not touched.
"""
import json, subprocess

BB, NGX = "busybox:1.36", "nginx:1.27-alpine"
SA = "system:serviceaccount:cka3:reporter"
ETCD_FLAGS = ("--endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt "
              "--cert=/etc/kubernetes/pki/etcd/server.crt --key=/etc/kubernetes/pki/etcd/server.key")


def make(api):
    kc = api.kc
    sleep = {"image": BB, "command": ["sleep", "infinity"]}

    def node():
        return f"{api.KIND_NAME}-control-plane"

    def can(verb):
        return kc("auth", "can-i", verb, "pods", "-n", "cka3", "--as", SA, check=False).strip() == "yes"

    def reach(src):
        r = kc("exec", "-n", "cka5", f"deploy/{src}", "--", "wget", "-q", "-T", "3", "-O", "-", "http://backend", check=False)
        return "nginx" in r.lower()

    def pvc_phase():
        return kc("get", "pvc", "data", "-n", "cka4", "-o", "jsonpath={.status.phase}", check=False)

    def snapshot_ok():
        r = subprocess.run(["docker", "exec", node(), "sh", "-c", "test -s /var/lib/etcd/snapshot.db"], capture_output=True)
        if r.returncode != 0:
            return False
        st = kc("exec", "-n", "kube-system", f"etcd-{node()}", "--", "etcdctl", "snapshot", "status",
                "/var/lib/etcd/snapshot.db", "-w", "json", check=False)
        try:
            return json.loads(st).get("totalKey", 0) > 0
        except ValueError:
            return False

    def setup(d, w):
        with api.con.status("[cyan]Opening the dojo (kind, about 1 minute)...", spinner="dots12"):
            api.kind_up()
            kc("label", "node", "--all", "disktype-", check=False)
            subprocess.run(["docker", "exec", node(), "rm", "-f", "/var/lib/etcd/snapshot.db"], capture_output=True)
            for ns in ("cka1", "cka2", "cka3", "cka4", "cka5"):
                kc("delete", "ns", ns, "--ignore-not-found", "--wait=true")
                kc("create", "ns", ns)
            picky = api.deploy("cka1", "picky", sleep)
            picky["spec"]["template"]["spec"]["nodeSelector"] = {"disktype": "ssd"}
            greedy = api.deploy("cka2", "greedy", dict(sleep, resources={"requests": {"cpu": "64", "memory": "64Mi"}}))
            db = api.deploy("cka4", "db", dict(sleep, volumeMounts=[{"name": "data", "mountPath": "/data"}]))
            db["spec"]["template"]["spec"]["volumes"] = [{"name": "data", "persistentVolumeClaim": {"claimName": "data"}}]
            items = [
                picky, greedy, db,
                {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": "reporter", "namespace": "cka3"}},
                {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding",
                 "metadata": {"name": "legacy-access", "namespace": "cka3"},
                 "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "edit"},
                 "subjects": [{"kind": "ServiceAccount", "name": "reporter", "namespace": "cka3"}]},
                {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "data", "namespace": "cka4"},
                 "spec": {"storageClassName": "fast-ssd", "accessModes": ["ReadWriteOnce"],
                          "resources": {"requests": {"storage": "100Mi"}}}},
                api.deploy("cka5", "backend", {"image": NGX, "ports": [{"containerPort": 80}]}),
                {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "backend", "namespace": "cka5"},
                 "spec": {"selector": {"app": "backend"}, "ports": [{"port": 80}]}},
                api.deploy("cka5", "frontend", sleep),
                api.deploy("cka5", "intruder", sleep),
                {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "default-deny", "namespace": "cka5"},
                 "spec": {"podSelector": {}, "policyTypes": ["Ingress"]}},
            ]
            kc("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}))
            (d / "README.txt").parent.mkdir(parents=True, exist_ok=True)
            (d / "README.txt").write_text("CKA Dojo: namespaces cka1..cka5, and etcd in kube-system.\n")

    def chk_picky(d, w, _):
        return api.ready("cka1", "picky"), "deploy/picky is not Ready yet."

    def chk_greedy(d, w, _):
        cpu = kc("get", "deploy", "greedy", "-n", "cka2", "-o",
                 "jsonpath={.spec.template.spec.containers[0].resources.requests.cpu}", check=False)
        if not cpu:
            return False, "No cheating: keep a CPU request (a real scheduler needs it). Make it small."
        return api.ready("cka2", "greedy"), "deploy/greedy is not Ready yet."

    def chk_rbac(d, w, _):
        if can("delete"):
            return False, "reporter can still DELETE pods in cka3. Too much power."
        if not can("list"):
            return False, "reporter cannot LIST pods in cka3 yet."
        return True, ""

    def chk_pvc(d, w, _):
        if pvc_phase() != "Bound":
            return False, f"PVC data is {pvc_phase() or 'missing'}, not Bound."
        return api.ready("cka4", "db"), "deploy/db is not Ready yet."

    def chk_wall(d, w, _):
        if not kc("get", "networkpolicy", "default-deny", "-n", "cka5", "-o", "name", check=False):
            return False, "No cheating: keep NetworkPolicy default-deny. Add a policy that ALLOWS, do not remove the wall."
        if not reach("frontend"):
            return False, "frontend still cannot reach http://backend."
        if reach("intruder"):
            return False, "intruder can reach backend too. Only frontend may enter."
        return True, ""

    def chk_etcd(d, w, _):
        return snapshot_ok(), "No valid snapshot at /var/lib/etcd/snapshot.db yet."

    return {"cka": {
        "title": "CKA Dojo", "needs": ["kind", "docker", "kubectl"], "dir": "cka", "setup": setup, "kind": True, "rooms": [
            {"name": "The Picky Pod", "ns": "cka1", "check": chk_picky,
             "story": "deploy/picky is [bold]Pending[/] forever. The scheduler says no node fits.",
             "task": "Namespace [bold]cka1[/]. Make deploy/picky Ready.\nThen: [cyan]check[/]",
             "hints": ["`kubectl describe pod -n cka1` and read the Events at the bottom.",
                       "It wants a node with label disktype=ssd: `kubectl get nodes --show-labels`",
                       "`kubectl label node <node> disktype=ssd` (or remove the nodeSelector from the deploy)."]},
            {"name": "The Greedy Pod", "ns": "cka2", "check": chk_greedy,
             "story": "deploy/greedy asks for more CPU than the whole node has.",
             "task": "Namespace [bold]cka2[/]. Make deploy/greedy Ready. Keep a CPU request.\nThen: [cyan]check[/]",
             "hints": ["Events say `Insufficient cpu`. How much does it ask for?",
                       "`kubectl get deploy greedy -n cka2 -o jsonpath='{..resources}'`",
                       "`kubectl set resources deploy/greedy -n cka2 --requests=cpu=100m`"]},
            {"name": "Who Can?", "ns": "cka3", "check": chk_rbac,
             "story": "ServiceAccount [bold]reporter[/] should only READ pods. Today it can delete them.",
             "task": "Namespace [bold]cka3[/]. reporter must [bold]list[/] pods but [bold]not delete[/] them.\n"
                     "Test: kubectl auth can-i delete pods -n cka3 --as system:serviceaccount:cka3:reporter\nThen: [cyan]check[/]",
             "hints": ["Find what gives reporter its power: `kubectl get rolebindings -n cka3 -o wide`",
                       "Remove the too-wide binding, then grant only read.",
                       "`kubectl create role pod-reader --verb=get,list,watch --resource=pods -n cka3` and a rolebinding for the SA."],
             "steps": [
                 {"name": "too much power (it can delete)", "done": lambda d, w: not can("delete"),
                  "hints": ["Who gives reporter its power? `kubectl get rolebindings -n cka3 -o wide`",
                            "legacy-access binds the ClusterRole `edit`. edit can delete pods.",
                            "`kubectl delete rolebinding legacy-access -n cka3`"]},
                 {"name": "it must still read pods", "done": lambda d, w: can("list"),
                  "hints": ["Now it can do nothing. Give it only read access, in this namespace.",
                            "A Role says what, a RoleBinding says who.",
                            "`kubectl create role pod-reader --verb=get,list,watch --resource=pods -n cka3` then "
                            "`kubectl create rolebinding reporter-read --role=pod-reader --serviceaccount=cka3:reporter -n cka3`"]},
             ]},
            {"name": "The Unbound Claim", "ns": "cka4", "check": chk_pvc,
             "story": "deploy/db waits for its disk. PVC [bold]data[/] stays Pending.",
             "task": "Namespace [bold]cka4[/]. Get PVC data Bound and deploy/db Ready.\nThen: [cyan]check[/]",
             "hints": ["`kubectl describe pvc data -n cka4`  Which StorageClass does it want?",
                       "`kubectl get storageclass`  Does that one exist?",
                       "A PVC spec cannot change. Scale db to 0, replace the PVC with storageClassName: standard, scale back to 1."],
             "steps": [
                 {"name": "the PVC asks for a StorageClass that does not exist",
                  "done": lambda d, w: kc("get", "storageclass", kc("get", "pvc", "data", "-n", "cka4", "-o",
                                                                    "jsonpath={.spec.storageClassName}", check=False) or "none",
                                          "-o", "name", check=False) != "",
                  "hints": ["`kubectl describe pvc data -n cka4`  Which StorageClass does it want?",
                            "`kubectl get storageclass`  Is that one in the list? (Or create a StorageClass with that name.)",
                            "PVC spec cannot change, and a PVC in use cannot be deleted: `kubectl scale deploy db -n cka4 --replicas=0`, "
                            "`kubectl get pvc data -n cka4 -o yaml > pvc.yaml`, set storageClassName: standard, "
                            "`kubectl delete pvc data -n cka4`, `kubectl apply -f pvc.yaml`"]},
                 {"name": "the pod must use the new claim", "done": lambda d, w: api.ready("cka4", "db", polls=1),
                  "hints": ["`kubectl get deploy db -n cka4`  Is it running at all? Did you scale it down?",
                            "Bring it back and let it claim the new PVC.",
                            "`kubectl scale deploy db -n cka4 --replicas=1`"]},
             ]},
            {"name": "The Wall", "ns": "cka5", "check": chk_wall,
             "story": "A [bold]default-deny[/] NetworkPolicy blocks everything. Now even frontend cannot reach backend.",
             "task": "Namespace [bold]cka5[/]. frontend must reach http://backend, intruder must not.\n"
                     "Keep default-deny. Test: kubectl exec -n cka5 deploy/frontend -- wget -qO- -T 3 backend\nThen: [cyan]check[/]",
             "hints": ["`kubectl get networkpolicy -n cka5 -o yaml`  What does default-deny select?",
                       "Policies add up: add one that ALLOWS ingress to app=backend from app=frontend.",
                       "podSelector: {matchLabels: {app: backend}}, ingress: [{from: [{podSelector: {matchLabels: {app: frontend}}}], ports: [{port: 80}]}]"],
             "steps": [
                 {"name": "frontend cannot get in", "done": lambda d, w: reach("frontend"),
                  "hints": ["`kubectl get networkpolicy -n cka5 -o yaml`  default-deny selects every pod.",
                            "NetworkPolicies add up. Write one more that ALLOWS: to app=backend, from app=frontend, port 80.",
                            "spec: podSelector {matchLabels {app: backend}}, policyTypes [Ingress], "
                            "ingress [{from: [{podSelector: {matchLabels: {app: frontend}}}], ports: [{port: 80}]}]"]},
                 {"name": "the intruder must stay out", "done": lambda d, w: not reach("intruder"),
                  "hints": ["`kubectl exec -n cka5 deploy/intruder -- wget -qO- -T 3 backend` works. It should not.",
                            "Is default-deny still there? Does your policy allow everyone?",
                            "The `from` must select only app=frontend, and default-deny must stay."]},
             ]},
            {"name": "The Time Capsule", "ns": "kube-system", "check": chk_etcd,
             "story": "Before an upgrade, the boss wants a backup of the whole cluster state: [bold]etcd[/].",
             "task": "Save an etcd snapshot to [bold]/var/lib/etcd/snapshot.db[/] (inside the etcd pod).\nThen: [cyan]check[/]",
             "hints": ["etcd runs as a static pod: `kubectl get pods -n kube-system | grep etcd`",
                       "etcdctl needs the endpoint and 3 certs from /etc/kubernetes/pki/etcd/ (ca.crt, server.crt, server.key).",
                       "`kubectl exec -n kube-system etcd-<node> -- etcdctl " + ETCD_FLAGS + " snapshot save /var/lib/etcd/snapshot.db`"]},
        ]}}
