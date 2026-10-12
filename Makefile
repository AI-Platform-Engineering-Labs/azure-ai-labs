SHELL := bash
.DEFAULT_GOAL := help

# python3 first, except the Windows Store stub that only prints an install hint.
PYTHON ?= $(shell python3 -c 'import sys' >/dev/null 2>&1 && echo python3 || echo python)
# Resolved when a recipe line runs, so it also works right after `make venv` creates it.
VENV_PY = $$( [ -x lab/.venv/Scripts/python.exe ] && echo lab/.venv/Scripts/python.exe || echo lab/.venv/bin/python )
TF ?= terraform
TF_DIR := infra/azure

.PHONY: help
help:
	@echo "make venv           create lab/.venv with the lab package and dev tools"
	@echo "make test           lint and unit tests for the lab package"
	@echo "make validate       render the Kubernetes manifests, check the scripts"
	@echo "make tf-check       terraform fmt and validate for infra/azure (no Azure access)"
	@echo "make lab-up         Kind cluster + Kavrynt + monitoring + lab (RUNTIME=release|source)"
	@echo "make lab-check      in-cluster end-to-end checks"
	@echo "make lab-status     pods, MCPServers, Gateway routes and URLs"
	@echo "make lab-reload     rebuild the lab image, re-apply manifests and expectations"
	@echo "make runtime-reload reinstall Kavrynt (rebuilds images with RUNTIME=source)"
	@echo "make lab-down       delete the Kind cluster"
	@echo "make clean          lab-down, then remove lab images and .cache"
	@echo "Azure lab: GitHub Actions 'Azure Lab' workflow (docs/runbooks/azure-lab.md)"

.PHONY: venv
venv:
	$(PYTHON) -m venv lab/.venv
	$(VENV_PY) -m pip install -q -c lab/constraints.txt -e "./lab[dev]"

.PHONY: test
test:
	py="$$(pwd)/$(VENV_PY)" && cd lab && "$$py" -m ruff check . && "$$py" -m ruff format --check . && "$$py" -m pytest -q

.PHONY: validate
validate:
	kubectl kustomize cluster/monitoring >/dev/null
	kubectl kustomize --load-restrictor=LoadRestrictionsNone cluster/workloads >/dev/null
	bash -n scripts/lab.sh
	bash -n .github/actions/approval/approve.sh

.PHONY: tf-check
tf-check:
	$(TF) fmt -check -recursive infra
	$(TF) -chdir=$(TF_DIR) init -backend=false -input=false >/dev/null
	$(TF) -chdir=$(TF_DIR) validate

.PHONY: lab-up lab-check lab-status lab-reload runtime-reload lab-down clean
lab-up:
	scripts/lab.sh up
lab-check:
	scripts/lab.sh check
lab-status:
	scripts/lab.sh status
lab-reload:
	scripts/lab.sh reload
runtime-reload:
	scripts/lab.sh runtime-reload
lab-down:
	scripts/lab.sh down
clean:
	scripts/lab.sh clean
