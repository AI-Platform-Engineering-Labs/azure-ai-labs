#!/usr/bin/env python3
"""Download a Helm chart from a public Docker Hub OCI repository without any credentials.

`helm pull oci://...` reuses Docker's credential store, so a stale Docker Hub login breaks
pulls of public charts with 401. This talks to the registry API anonymously instead and
verifies the chart layer's sha256 against the manifest. Standard library only.

    fetch_chart.py kavrynt/kavrynt 0.0.2-beta.1 .cache/charts [--digest sha256:...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REGISTRY = "https://registry-1.docker.io"
AUTH = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
MANIFEST_TYPES = "application/vnd.oci.image.manifest.v1+json"
CHART_LAYER = "application/vnd.cncf.helm.chart.content.v1.tar+gzip"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _get(url: str, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        if err.code in (301, 302, 303, 307, 308) and err.headers.get("Location"):
            # Blob downloads redirect to a CDN; never forward the registry token there.
            with urllib.request.urlopen(err.headers["Location"], timeout=120) as resp:
                return resp.read()
        raise


def fetch(repo: str, version: str, out_dir: Path, pinned: str | None = None) -> Path:
    token = json.loads(_get(AUTH.format(repo=repo)))["token"]
    auth = {"Authorization": f"Bearer {token}"}

    manifest = json.loads(_get(f"{REGISTRY}/v2/{repo}/manifests/{version}",
                               {**auth, "Accept": MANIFEST_TYPES}))
    layers = [layer for layer in manifest.get("layers", []) if layer.get("mediaType") == CHART_LAYER]
    if len(layers) != 1:
        raise SystemExit(f"{repo}:{version} is not a Helm chart (layers: {manifest.get('layers')})")
    digest = layers[0]["digest"]
    if pinned and digest != pinned:
        raise SystemExit(f"{repo}:{version} chart is {digest}, expected pinned {pinned}")

    blob = _get(f"{REGISTRY}/v2/{repo}/blobs/{digest}", auth)
    algo, expected = digest.split(":", 1)
    if algo != "sha256" or hashlib.sha256(blob).hexdigest() != expected:
        raise SystemExit(f"digest mismatch for {repo}:{version} ({digest})")

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{repo.rsplit('/', 1)[-1]}-{version}.tgz"
    target.write_bytes(blob)
    print(f"{target} {digest}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", help="Docker Hub repository, e.g. kavrynt/kavrynt")
    parser.add_argument("version", help="chart version (OCI tag)")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--digest", help="expected chart layer digest (sha256:...)")
    args = parser.parse_args()
    try:
        fetch(args.repo, args.version, args.out_dir, args.digest)
    except urllib.error.URLError as err:
        sys.exit(f"fetch failed: {err}")


if __name__ == "__main__":
    main()
