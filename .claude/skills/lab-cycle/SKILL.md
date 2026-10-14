---
name: lab-cycle
description: Bring the Kavrynt lab up on local Kind, run the in-cluster checks, read the governance results, diagnose failures, and tear it down - with the released runtime or a local ../kavrynt checkout (RUNTIME=source). Use to test a lab change or a runtime change end to end.
argument-hint: "[release | source] [keep]"
---

# Run the lab end to end on Kind

Arguments: `$ARGUMENTS`. `source` builds the runtime from `../kavrynt` (or `KAVRYNT_SRC`);
the default is the pinned released runtime. `keep` leaves the cluster running at the end.

## 1. Preflight

```bash
docker info --format '{{.MemTotal}}'      # 4 GB or more for Docker
kind version && kubectl version --client && helm version --short
make venv                                  # once
make test && make validate                 # fast checks before the slow ones
```

With `source`: run `git -C ../kavrynt status -sb` and say which branch and commit you are
testing.

## 2. Up and check

```bash
make lab-up                  # or: RUNTIME=source make lab-up
make lab-status
make lab-check
```

If Docker Hub pulls fail (401, 429, a stale `docker login`):
`DOCKERHUB_MIRROR=mirror.gcr.io make lab-up`.

Runtime development loop (with `source`): change Go code in `../kavrynt`, then
`RUNTIME=source make runtime-reload && make lab-check`. Lab code change: `make lab-reload`.

## 3. Read the result

- Gateway routes: `curl -fsS http://localhost:18080/v1/routes`
- Dashboard: http://localhost:3000/d/kavrynt-governance (Prometheus at :9090)
- Today's runtime has no authentication or policy, so the **ungoverned** count grows by design
  (FINDINGS F1, F2). Report a change in that behaviour, not its presence.
- **Over-blocked** above zero, or `not_found` for a registered server, is a regression.

## 4. Diagnose a failure

```bash
kubectl get pods -A | grep -v Running
kubectl -n kavrynt-system logs deploy/kavrynt-gateway --tail=100
kubectl -n kavrynt-system logs deploy/kavrynt-operator --tail=100
kubectl -n lab-agents logs job/lab-check --tail=100
kubectl get mcpservers -A
```

Decide where the fix belongs: lab code here, runtime in `kavrynt`, Cloud in `kavrynt-cloud`.
Something the lab reveals about the runtime or Cloud gets recorded with `/record-finding`.

## 5. Down

Unless `keep` was given: `make lab-down` (`make clean` also removes lab images and `.cache`).

Report: runtime mode and version or commit, the checks result, governance counts, and any new
findings.
