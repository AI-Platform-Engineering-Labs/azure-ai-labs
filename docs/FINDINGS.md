# Findings

What the lab has shown about the Kavrynt runtime and Cloud. Each finding names the
repository that owns the fix; open an issue there and link it here. Code references are to
`kavrynt` at `2fa8047` (runtime `0.0.2-beta.1`).

| # | Finding | Severity | Owner | Status |
|---|---|---|---|---|
| F1 | Any caller can use any registered MCP server | high | `kavrynt` | open (Phase 4) |
| F2 | Calls that policy would deny run anyway | high | `kavrynt` | open (Phase 4) |
| F3 | Gateway buffers responses, which breaks streamed (SSE) MCP responses | high | `kavrynt` | open |
| F4 | Gateway metrics have no labels | medium | `kavrynt` | open |
| F5 | Nothing syncs the cluster to Kavrynt Cloud | medium | `kavrynt` | open (Phase 3) |
| F6 | `MCPServer` has no owner, description or tool metadata | medium | `kavrynt` | open |
| F7 | Gateway errors are plain JSON, not MCP errors | medium | `kavrynt` | open |
| F8 | Stale packaged subcharts in a checkout render extra Deployments | low | `kavrynt` | open |
| F9 | `helm pull` of the public chart fails with a stale Docker Hub login | low | docs | worked around |

## F1. Any caller can use any registered MCP server

The Gateway strips `Authorization`, `Cookie` and `Proxy-Authorization`
(`internal/gateway/api/api.go:27`) and forwards everything else; it does not authenticate the
caller. Any pod that can reach `kavrynt-gateway.kavrynt-system:8080` can call every tool on
every registered server. The lab's agent name (`X-Lab-Agent`) is self-asserted and passed
straight through, so the servers' per-agent metrics are only as honest as the caller.

**Seen in the lab:** `rogue-agent` reaches `team-payments.payments-mcp` and
`team-support.support-mcp` with no credentials.
**Fix:** Gateway as OAuth resource server with per-agent tokens (ADR-0003, PLAN Phase 4).

## F2. Calls that policy would deny run anyway

There is no policy point in the request path. Every call `policies/expectations.yaml` marks
`deny` or `approve` reaches the MCP server and executes.

**Seen in the lab:** the *Ungoverned calls* and *Approvals bypassed* panels grow
continuously, and *Expected blocks enforced* stays around 10-15%. The only calls the runtime
stops are calls to an unregistered server (`404`, the `not_found` outcome), which the rogue
agent makes about one time in ten by construction.
**Fix:** embedded OPA decisions on `(caller, server, tool)` plus approvals (ADR-0003, Phase 4).
The lab's expectations file is the acceptance test.

## F3. Gateway buffers responses

The proxy copies the upstream body with a single `io.Copy` (`api.go:178`) and never
flushes. A streamable-HTTP MCP server that answers with `text/event-stream` (progress
notifications, long-running tools) is held back until the upstream response ends, and an
open stream (the `GET` listening channel) never reaches the client.

**Seen in the lab:** lab servers run with `json_response=True, stateless_http=True` to avoid
it, so the default MCP SDK server configuration is *not* what the lab exercises.
**Fix:** flush per write (`http.ResponseController.Flush`, or `httputil.ReverseProxy` with
`FlushInterval: -1`) and a test with an SSE upstream.

## F4. Gateway metrics have no labels

`/metrics` (`api.go:117-127`) emits six global counters/gauges with no `route`, `status`,
`method` or caller labels and no `# HELP` / `# TYPE` lines. You cannot tell which server is
busy, which calls failed, or how long calls took.

**Seen in the lab:** the dashboard's per-agent, per-tool and latency panels come from the
lab's own servers and agents, not from Kavrynt.
**Fix:** `prometheus/client_golang` with `kavrynt_gateway_requests_total{route,code}` and a
request-duration histogram. Keep caller labels behind authentication (F1) to bound cardinality.

## F5. Nothing syncs the cluster to Kavrynt Cloud

`kavrynt-cloud` exposes `POST /v1/sync/mcpservers`, `/v1/audit-events` and
`/v1/usage-events`, but nothing in the runtime calls them, so the Cloud inventory, audit and
usage views stay empty for a real cluster.

**Fix:** the connector in the runtime (PLAN Phase 3).

## F6. `MCPServer` has no owner, description or tool metadata

`MCPServerSpec` (`api/v1alpha1/mcpserver_types.go:29`) has `version`, `transport`, `command`,
`args`, `endpoint`, `environment`. Ownership and description - needed for inventory and
approvals routing - have nowhere to live; the lab uses `kavrynt.io/owner` and
`kavrynt.io/description` annotations. Tool risk is only discoverable from the server itself
(the lab publishes it as MCP tool annotations plus `_meta["kavrynt.io/risk"]`).

**Fix:** decide whether owner/description belong in the spec, and have the connector record
`tools/list` (with annotations and `_meta`) per server version.

## F7. Gateway errors are plain JSON, not MCP errors

Unregistered routes and upstream failures return `{"error": "..."}` with `404`/`502`
(`api.go:136-171`). MCP clients do not see the HTTP status: the Python SDK (`mcp` 2.3) turns
the Gateway's `404` into JSON-RPC error `-32601 "Not Found"` - the *method not found* code - so an
unregistered server looks like a missing method, and an agent cannot tell "not registered" or
(later) "denied by policy" from "server down".

**Seen in the lab:** agents read the status through an HTTP response hook
(`lab/src/kavrynt_lab/agent.py`) because the client hides it.
**Fix:** for `POST` JSON-RPC requests, answer with a JSON-RPC error object carrying a
Kavrynt error code and reason (`not_registered`, `denied`, `approval_required`), keeping the
HTTP status. Decide this before Phase 4 so denials are actionable for agents.

## F8. Stale packaged subcharts render extra Deployments

`charts/kavrynt/charts/*.tgz` is git-ignored (`.gitignore:16`) but Helm still loads it. A
checkout that once ran `helm dependency build` keeps `gateway-0.0.1-beta.1.tgz`,
`k8s-operator-0.0.1-beta.1.tgz` and `registry-0.0.1-beta.1.tgz` beside the unpacked
subcharts, and `helm install ./charts/kavrynt` then also renders `kavrynt-k8s-operator` and
`kavrynt-registry`. The published chart is not affected.

**Seen in the lab:** `RUNTIME=source` copies the chart and deletes `charts/*.tgz` first.
**Fix:** add `charts/*.tgz` to `charts/kavrynt/.helmignore`, or remove them in `make clean`.

## F9. `helm pull` fails with a stale Docker Hub login

The chart and images are public on Docker Hub (`registry-1.docker.io/kavrynt/kavrynt`,
`docker.io/kavrynt/{gateway,operator}`); the GHCR packages are private. `helm pull oci://...`
reads Docker's credential store, and a stale Docker Hub login turns an anonymous pull into a
`401`.

**Workaround:** `scripts/fetch_chart.py` downloads the chart anonymously through the registry
API and checks the pinned digest. Worth a line in the install docs.
