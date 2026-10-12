#!/usr/bin/env bash
# The Kavrynt lab on Kind (local) or on an existing AKS cluster (the Azure Lab workflow).
#
#   scripts/lab.sh up               install Kavrynt, monitoring and the lab (Kind: create the cluster first)
#   scripts/lab.sh check            run the in-cluster end-to-end checks (Job lab-check)
#   scripts/lab.sh reload           Kind: rebuild the lab image and re-apply manifests/expectations
#   scripts/lab.sh runtime-reload   reinstall Kavrynt (rebuilds images when RUNTIME=source)
#   scripts/lab.sh status           pods, MCPServers, routes and how to reach Grafana
#   scripts/lab.sh down             Kind: delete the cluster (AKS: use the Azure Lab workflow)
#   scripts/lab.sh clean            Kind: also remove lab images from Docker and the .cache folder
#
# Settings (environment):
#   TARGET=kind|aks          kind (default) or an AKS cluster reachable as KUBE_CONTEXT
#   RUNTIME=release|source   release: pinned published chart + images (default)
#                            source: chart and images built from KAVRYNT_SRC (Kind only)
#   KAVRYNT_SRC              kavrynt checkout for RUNTIME=source (default ../kavrynt)
#   DOCKERHUB_MIRROR         pull host-side Docker Hub images via a mirror, e.g. mirror.gcr.io
#   LAB_IMAGE                AKS: the pushed lab image (<registry>/kavrynt-lab:<tag>)
#   KUBE_CONTEXT             AKS: kubectl context (az aks get-credentials); Kind: kind-$CLUSTER
#   CLUSTER                  Kind cluster name (default kavrynt-lab)
#   WAIT_TIMEOUT             rollout wait per deployment (default 300s)
set -euo pipefail
shopt -s inherit_errexit

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${TARGET:-kind}"
CLUSTER="${CLUSTER:-kavrynt-lab}"
CONTEXT="${KUBE_CONTEXT:-kind-${CLUSTER}}"
RUNTIME="${RUNTIME:-release}"
KAVRYNT_SRC="${KAVRYNT_SRC:-$ROOT/../kavrynt}"
DOCKERHUB_MIRROR="${DOCKERHUB_MIRROR:-}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300s}"
RUNTIME_NS="kavrynt-system"
CACHE="$ROOT/.cache"
# The manifests name this image; it is replaced with the real reference on apply.
MANIFEST_IMAGE="kavrynt-lab:local"
LAB_IMAGE="${LAB_IMAGE:-}"

# Pinned versions. Update together, after checking the new digests.
KIND_NODE_IMAGE="kindest/node:v1.35.0@sha256:4613778f3cfcd10e615029370f5786704559103cf27bef934597ba562b269661"
KAVRYNT_VERSION="0.0.2-beta.1"
KAVRYNT_CHART_DIGEST="sha256:3f1ebeded599625a2ef9623fb6636334538d2ad53c48f650a904327626f0e976"
KAVRYNT_GATEWAY_DIGEST="sha256:688160e8cb886ef241e88e44f0b136ebe48a34874f67d5b3075df34e955450ba"
KAVRYNT_OPERATOR_DIGEST="sha256:bc575167ebf29eb9231cd74855dd1d203d9776a3e9293942062a058fe142ebcf"

LAB_DEPLOYMENTS=(
  team-payments/payments-mcp
  team-support/support-mcp
  lab-agents/support-agent
  lab-agents/payments-agent
  lab-agents/rogue-agent
)

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
k() { kubectl --context "$CONTEXT" "$@"; }

require() {
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is required (see README.md)"
  done
}

kind_only() {
  [[ "$TARGET" == kind ]] || die "$1 is Kind only. On AKS use the Azure Lab workflow (docs/runbooks/azure-lab.md)."
}

python_cmd() {
  local candidate
  for candidate in "${PYTHON:-}" python3 python; do
    if [[ -n "$candidate" ]] && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
      echo "$candidate"
      return
    fi
  done
  die "python 3.9+ is required"
}

# hub IMAGE: rewrite a Docker Hub reference to DOCKERHUB_MIRROR when set.
hub() {
  local image="$1"
  if [[ -z "$DOCKERHUB_MIRROR" ]]; then
    echo "$image"
  elif [[ "${image%%:*}" == */* ]]; then
    echo "$DOCKERHUB_MIRROR/$image"
  else
    echo "$DOCKERHUB_MIRROR/library/$image"
  fi
}

pull_hint() {
  if [[ -z "$DOCKERHUB_MIRROR" ]]; then
    echo " (Docker Hub 401/429? retry with DOCKERHUB_MIRROR=mirror.gcr.io)"
  fi
}

# Captured first: with pipefail, `kind get clusters | grep -q` can fail when grep exits early.
cluster_exists() {
  local clusters
  clusters="$(kind get clusters 2>/dev/null)" || return 1
  grep -qx "$CLUSTER" <<<"$clusters"
}

require_cluster() {
  if [[ "$TARGET" == kind ]]; then
    cluster_exists || die "no Kind cluster $CLUSTER - run: scripts/lab.sh up"
  else
    k get namespace kube-system >/dev/null || die "cannot reach the cluster through kube context $CONTEXT"
  fi
}

create_cluster() {
  if cluster_exists; then
    log "Kind cluster $CLUSTER already exists"
  else
    log "Creating Kind cluster $CLUSTER"
    kind create cluster --name "$CLUSTER" --config "$ROOT/kind/cluster.yaml" \
      --image "$(hub "$KIND_NODE_IMAGE")" --wait 120s
  fi
}

# Builds the lab image and loads it into Kind under a content-addressed tag, so a changed
# image always changes the pod specs and rolls the pods.
build_lab_image() {
  local args=() id
  if [[ -n "$DOCKERHUB_MIRROR" ]]; then
    args=(--build-arg "PYTHON_IMAGE=$(hub "$(sed -n 's/^ARG PYTHON_IMAGE=//p' "$ROOT/lab/Dockerfile")")")
  fi
  log "Building the lab image"
  # No provenance attestation: it changes the image ID on every build, and the tag must
  # change only when the image content does.
  docker build --quiet --provenance=false "${args[@]}" -t "$MANIFEST_IMAGE" "$ROOT/lab" >/dev/null ||
    die "lab image build failed$(pull_hint)"
  id="$(docker image inspect -f '{{.Id}}' "$MANIFEST_IMAGE")"
  LAB_IMAGE="kavrynt-lab:${id#sha256:}"
  LAB_IMAGE="${LAB_IMAGE:0:24}"
  docker tag "$MANIFEST_IMAGE" "$LAB_IMAGE"
  kind load docker-image "$LAB_IMAGE" --name "$CLUSTER" >/dev/null || die "kind load $LAB_IMAGE failed"
}

# The image the running lab uses (check reuses it).
deployed_lab_image() {
  k -n lab-agents get deployment support-agent -o jsonpath='{.spec.template.spec.containers[0].image}'
}

# render DIR|FILE: manifests with the lab image reference filled in.
render() {
  local source="$1" yaml
  [[ -n "$LAB_IMAGE" ]] || die "LAB_IMAGE is not set"
  if [[ -d "$source" ]]; then
    yaml="$(k kustomize --load-restrictor=LoadRestrictionsNone "$source")"
  else
    yaml="$(cat "$source")"
  fi
  sed "s#image: ${MANIFEST_IMAGE}\$#image: ${LAB_IMAGE}#" <<<"$yaml"
}

sha256_of() {
  "$(python_cmd)" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
}

# The pinned release chart, downloaded once and verified on every use.
release_chart() {
  local chart="$CACHE/charts/kavrynt-$KAVRYNT_VERSION.tgz"
  if [[ ! -f "$chart" ]]; then
    log "Fetching chart kavrynt $KAVRYNT_VERSION from Docker Hub" >&2
    "$(python_cmd)" "$ROOT/scripts/fetch_chart.py" kavrynt/kavrynt "$KAVRYNT_VERSION" "$CACHE/charts" \
      --digest "$KAVRYNT_CHART_DIGEST" >&2
  fi
  [[ "sha256:$(sha256_of "$chart")" == "$KAVRYNT_CHART_DIGEST" ]] ||
    die "$chart does not match $KAVRYNT_CHART_DIGEST; delete it and run again"
  echo "$chart"
}

# Builds gateway/operator images from KAVRYNT_SRC, loads them into Kind, prints the tag.
build_runtime_images() {
  [[ -f "$KAVRYNT_SRC/build/Dockerfile" ]] || die "KAVRYNT_SRC=$KAVRYNT_SRC is not a kavrynt checkout"
  local commit tag args=()
  commit="$(git -C "$KAVRYNT_SRC" rev-parse HEAD)"
  tag="src-${commit:0:7}"
  if [[ -n "$(git -C "$KAVRYNT_SRC" status --porcelain)" ]]; then
    tag="$tag-dirty-$(date +%s)"
  fi
  args=(--file "$KAVRYNT_SRC/build/Dockerfile" --build-arg "VERSION=$tag" --build-arg "COMMIT=$commit"
        --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)")
  if [[ -n "$DOCKERHUB_MIRROR" ]]; then
    local go_image syntax
    go_image="$(sed -n 's/^ARG GO_IMAGE=//p' "$KAVRYNT_SRC/build/Dockerfile")"
    syntax="$(sed -n 's/^# syntax=//p' "$KAVRYNT_SRC/build/Dockerfile")"
    args+=(--build-arg "GO_IMAGE=$(hub "$go_image")")
    if [[ -n "$syntax" ]]; then args+=(--build-arg "BUILDKIT_SYNTAX=$(hub "$syntax")"); fi
  fi
  local component
  for component in gateway operator; do
    log "Building kavrynt/$component:$tag from $KAVRYNT_SRC" >&2
    docker build --quiet "${args[@]}" --target "$component" -t "kavrynt/$component:$tag" "$KAVRYNT_SRC" >/dev/null ||
      die "kavrynt/$component build failed$(pull_hint)"
    kind load docker-image "kavrynt/$component:$tag" --name "$CLUSTER" >/dev/null ||
      die "kind load kavrynt/$component:$tag failed"
  done
  echo "$tag"
}

# Copies the source chart and drops packaged subcharts (*.tgz) that would shadow the
# unpacked ones - a stale charts/*.tgz otherwise renders extra Deployments.
source_chart() {
  local dir="$CACHE/src-chart"
  rm -rf "$dir"
  mkdir -p "$dir"
  cp -r "$KAVRYNT_SRC/charts/kavrynt" "$dir/kavrynt"
  rm -f "$dir"/kavrynt/charts/*.tgz
  echo "$dir/kavrynt"
}

install_runtime() {
  local chart sets=() crds
  case "$RUNTIME" in
    release)
      chart="$(release_chart)"
      sets=(--set "gateway.image.tag=$KAVRYNT_VERSION@$KAVRYNT_GATEWAY_DIGEST"
            --set "operator.image.tag=$KAVRYNT_VERSION@$KAVRYNT_OPERATOR_DIGEST")
      ;;
    source)
      kind_only "RUNTIME=source"
      local tag
      tag="$(build_runtime_images)"
      chart="$(source_chart)"
      sets=(--set "gateway.image.tag=$tag" --set "operator.image.tag=$tag")
      ;;
    *) die "RUNTIME must be release or source (got $RUNTIME)" ;;
  esac
  # Helm installs crds/ once and never upgrades them; apply them first so a schema change
  # in the chart (or in ../kavrynt) always reaches the cluster.
  crds="$(helm show crds "$chart")"
  if [[ -n "$crds" ]]; then
    k apply --server-side --force-conflicts -f - <<<"$crds" >/dev/null
  fi
  log "Installing Kavrynt ($RUNTIME) into $RUNTIME_NS"
  helm upgrade --install kavrynt "$chart" --kube-context "$CONTEXT" \
    --namespace "$RUNTIME_NS" --create-namespace "${sets[@]}" --wait --timeout 5m >/dev/null
}

apply_monitoring() {
  log "Applying Prometheus and Grafana"
  k apply -k "$ROOT/cluster/monitoring" >/dev/null
}

apply_workloads() {
  log "Applying lab MCP servers, MCPServer registrations and agents ($LAB_IMAGE)"
  render "$ROOT/cluster/workloads" | k apply -f - >/dev/null
}

apply_kind_access() {
  k apply -f "$ROOT/kind/nodeports.yaml" >/dev/null
}

wait_ready() {
  log "Waiting for workloads"
  local item
  for item in lab-monitoring/prometheus lab-monitoring/grafana "${LAB_DEPLOYMENTS[@]}"; do
    k -n "${item%%/*}" rollout status "deployment/${item#*/}" --timeout "$WAIT_TIMEOUT" >/dev/null ||
      die "deployment ${item#*/} in ${item%%/*} is not ready (kubectl --context $CONTEXT -n ${item%%/*} describe deployment ${item#*/})"
  done
}

urls() {
  if [[ "$TARGET" == kind ]]; then
    cat <<EOF

  Grafana     http://localhost:3000/d/kavrynt-governance
  Prometheus  http://localhost:9090
  Gateway     http://localhost:18080/v1/routes
              MCP: http://localhost:18080/mcp/team-support.support-mcp
                   http://localhost:18080/mcp/team-payments.payments-mcp

EOF
  else
    cat <<EOF

  Nothing is exposed. Reach the lab through the Kubernetes API (docs/runbooks/azure-lab.md):
    kubectl --context $CONTEXT -n lab-monitoring port-forward svc/grafana 3000:3000
    kubectl --context $CONTEXT -n kavrynt-system port-forward svc/kavrynt-gateway 18080:8080
  then open http://localhost:3000/d/kavrynt-governance

EOF
  fi
}

cmd_up() {
  if [[ "$TARGET" == kind ]]; then
    require docker kind kubectl helm
    create_cluster
    build_lab_image
  else
    require kubectl helm
    [[ -n "$LAB_IMAGE" && "$LAB_IMAGE" != "$MANIFEST_IMAGE" ]] ||
      die "TARGET=aks needs LAB_IMAGE=<registry>/kavrynt-lab:<tag> (pushed by the Azure Lab workflow)"
    require_cluster
  fi
  install_runtime
  apply_monitoring
  apply_workloads
  if [[ "$TARGET" == kind ]]; then apply_kind_access; fi
  wait_ready
  log "Lab is up (target: $TARGET, runtime: $RUNTIME, image: $LAB_IMAGE)"
  urls
}

cmd_reload() {
  kind_only reload
  require docker kind kubectl
  require_cluster
  build_lab_image
  apply_monitoring
  apply_workloads
  wait_ready
  log "Reloaded ($LAB_IMAGE)"
}

cmd_runtime_reload() {
  require kubectl helm
  require_cluster
  install_runtime
  log "Kavrynt reinstalled (runtime: $RUNTIME)"
}

cmd_check() {
  require kubectl
  require_cluster
  LAB_IMAGE="$(deployed_lab_image)" || die "the lab is not deployed - run: scripts/lab.sh up"
  log "Running lab-check Job ($LAB_IMAGE)"
  k -n lab-agents delete job lab-check --ignore-not-found --wait >/dev/null
  render "$ROOT/cluster/workloads/check-job.yaml" | k apply -f - >/dev/null

  # A transient API error only means another poll.
  local deadline=$((SECONDS + 300)) succeeded="" failed=""
  while ((SECONDS < deadline)); do
    succeeded="$(k -n lab-agents get job lab-check -o jsonpath='{.status.succeeded}' 2>/dev/null || true)"
    failed="$(k -n lab-agents get job lab-check -o jsonpath='{.status.failed}' 2>/dev/null || true)"
    if [[ "${succeeded:-0}" -ge 1 || "${failed:-0}" -ge 1 ]]; then
      break
    fi
    sleep 3
  done
  k -n lab-agents logs job/lab-check || true
  if [[ "${succeeded:-0}" -ge 1 ]]; then
    log "All checks passed"
  elif [[ "${failed:-0}" -ge 1 ]]; then
    die "checks failed"
  else
    die "lab-check did not finish within 300s"
  fi
}

cmd_status() {
  require kubectl
  require_cluster
  k get pods -A -o wide \
    --field-selector 'metadata.namespace!=kube-system,metadata.namespace!=local-path-storage'
  echo
  k get mcpservers -A
  if [[ "$TARGET" == kind ]]; then
    echo
    curl -fsS http://localhost:18080/v1/routes && echo || echo "Gateway not reachable on localhost:18080"
  fi
  urls
}

cmd_down() {
  kind_only down
  require kind
  if cluster_exists; then
    log "Deleting Kind cluster $CLUSTER"
    kind delete cluster --name "$CLUSTER"
  else
    log "No Kind cluster $CLUSTER"
  fi
}

cmd_clean() {
  kind_only clean
  cmd_down
  require docker
  local images
  images="$(docker image ls --format '{{.Repository}}:{{.Tag}}' |
    grep -E '^kavrynt-lab:|^kavrynt/(gateway|operator):src-' || true)"
  if [[ -n "$images" ]]; then
    log "Removing lab images from Docker"
    xargs docker image rm >/dev/null <<<"$images"
  fi
  rm -rf "$CACHE"
  log "Clean"
}

case "$TARGET" in kind | aks) ;; *) die "TARGET must be kind or aks (got $TARGET)" ;; esac

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  clean) cmd_clean ;;
  check) cmd_check ;;
  reload) cmd_reload ;;
  runtime-reload) cmd_runtime_reload ;;
  status) cmd_status ;;
  *) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
