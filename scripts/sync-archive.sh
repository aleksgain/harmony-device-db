#!/usr/bin/env bash
# Sync the vendored Harmony IR archive snapshot from upstream.
#
# Upstream (pickysysadmin/logitech-harmony-ir-archive) publishes its data as a
# git tree (~0.8 GB, ~340k JSON files), and marks data releases with
# date-stamped tags (YYYYMMDD). `raw-*` tags are raw captures and are skipped.
#
# This repo pins one upstream tag+commit in archive.lock.json and commits only
# the small top-level files (api/v1/manifest.json, api/v1/index.json) so that
# sync PRs stay reviewable. The full tree is fetched on demand into api/v1/
# (gitignored) and shipped as a release tarball by release.yml.
#
# Usage:
#   scripts/sync-archive.sh check            print current/latest/needs_update (key=value)
#   scripts/sync-archive.sh update [TAG]     pin TAG (default: latest), fetch metadata, write lock
#   scripts/sync-archive.sh fetch            fetch the FULL pinned tree into api/v1/
#
# Env:
#   UPSTREAM_URL  override the upstream git URL (e.g. a local mirror)
set -euo pipefail

UPSTREAM_REPO="pickysysadmin/logitech-harmony-ir-archive"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/${UPSTREAM_REPO}.git}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/archive.lock.json"
DEST="$ROOT/api/v1"
TAG_RE='^[0-9]{8}$'
BULK_PATHS=(devices codesets protocols)
META_PATHS=(manifest.json index.json LICENSE)

WORK=""
cleanup() { [ -n "$WORK" ] && rm -rf "$WORK"; return 0; }
trap cleanup EXIT

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing required tool: $1"; }
need git; need jq; need sha256sum

lock_get() { [ -f "$LOCK" ] && jq -r ".$1 // empty" "$LOCK" || true; }

latest_tag() {
  git ls-remote --tags --refs "$UPSTREAM_URL" \
    | awk '{sub("refs/tags/","",$2); print $2}' \
    | grep -E "$TAG_RE" | sort -n | tail -1
}

# Resolve a tag to the commit it points at (peels annotated tags).
tag_commit() {
  local tag="$1" out
  out="$(git ls-remote --tags "$UPSTREAM_URL" "refs/tags/$tag" "refs/tags/$tag^{}")"
  [ -n "$out" ] || die "upstream tag '$tag' not found"
  # Prefer the peeled ^{} line when the tag is annotated.
  echo "$out" | awk '/\^\{\}$/ {print $1; found=1} END {if (!found) exit 1}' \
    || echo "$out" | awk 'NR==1 {print $1}'
}

# Shallow clone of one commit. With sparse paths it is also a partial clone,
# so only those blobs are downloaded; a full checkout fetches one packfile.
checkout_commit() {
  local commit="$1" dir="$2"; shift 2
  git init -q "$dir"
  git -C "$dir" remote add origin "$UPSTREAM_URL"
  git -C "$dir" config core.sparseCheckout true
  local filter=()
  if [ "$#" -gt 0 ]; then
    git -C "$dir" sparse-checkout set --no-cone "$@"
    filter=(--filter=blob:none)   # fetch only the blobs we check out
  else
    git -C "$dir" sparse-checkout disable
  fi
  git -C "$dir" fetch -q --depth 1 "${filter[@]}" origin "$commit"
  git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
}

copy_meta() {
  local src="$1"
  mkdir -p "$DEST"
  for f in manifest.json index.json; do
    [ -f "$src/$f" ] || die "upstream commit has no $f"
    cp "$src/$f" "$DEST/$f"
  done
  cp "$src/LICENSE" "$DEST/LICENSE-DATA" 2>/dev/null || true
}

cmd_check() {
  local current latest
  current="$(lock_get tag)"; current="${current:-none}"
  latest="$(latest_tag)"
  [ -n "$latest" ] || die "no YYYYMMDD tags found upstream"
  echo "current=$current"
  echo "latest=$latest"
  if [ "$latest" != "$current" ]; then echo "needs_update=true"; else echo "needs_update=false"; fi
}

cmd_update() {
  local tag="${1:-$(latest_tag)}" commit tree
  [[ "$tag" =~ $TAG_RE ]] || die "'$tag' is not a YYYYMMDD data tag"
  commit="$(tag_commit "$tag")"
  WORK="$(mktemp -d)"; local tmp="$WORK"
  echo "pinning $UPSTREAM_REPO@$tag ($commit)" >&2
  checkout_commit "$commit" "$tmp/src" "${META_PATHS[@]/#//}"
  tree="$(git -C "$tmp/src" rev-parse "HEAD^{tree}")"
  copy_meta "$tmp/src"
  jq -n \
    --arg upstream "$UPSTREAM_REPO" --arg tag "$tag" --arg commit "$commit" --arg tree "$tree" \
    --arg msha "$(sha256sum "$DEST/manifest.json" | cut -d' ' -f1)" \
    --arg isha "$(sha256sum "$DEST/index.json" | cut -d' ' -f1)" \
    --slurpfile m "$DEST/manifest.json" \
    '{upstream: $upstream, tag: $tag, commit: $commit, tree: $tree,
      schemaVersion: $m[0].schemaVersion, generated: $m[0].generated,
      counts: $m[0].counts,
      sha256: {"manifest.json": $msha, "index.json": $isha}}' > "$LOCK"
  echo "wrote $LOCK" >&2
}

cmd_fetch() {
  local tag commit tree want got
  tag="$(lock_get tag)"; commit="$(lock_get commit)"
  [ -n "$commit" ] || die "archive.lock.json has no pinned commit; run 'update' first"
  WORK="$(mktemp -d)"; local tmp="$WORK"
  echo "fetching full tree $UPSTREAM_REPO@$tag ($commit)" >&2
  checkout_commit "$commit" "$tmp/src"
  tree="$(git -C "$tmp/src" rev-parse "HEAD^{tree}")"
  [ "$tree" = "$(lock_get tree)" ] || die "tree mismatch: lock $(lock_get tree), fetched $tree"
  for p in "${BULK_PATHS[@]}"; do
    rm -rf "${DEST:?}/$p"
    [ -d "$tmp/src/$p" ] && cp -a "$tmp/src/$p" "$DEST/$p"
  done
  copy_meta "$tmp/src"
  # The committed metadata must match what the lock recorded.
  for f in manifest.json index.json; do
    want="$(jq -r --arg f "$f" '.sha256[$f]' "$LOCK")"
    got="$(sha256sum "$DEST/$f" | cut -d' ' -f1)"
    [ "$want" = "$got" ] || die "$f checksum mismatch (lock $want, fetched $got)"
  done
  echo "api/v1 populated from $tag" >&2
}

case "${1:-}" in
  check) cmd_check ;;
  update) shift; cmd_update "$@" ;;
  fetch) cmd_fetch ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
