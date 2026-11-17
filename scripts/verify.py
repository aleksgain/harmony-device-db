#!/usr/bin/env python3
"""Validate a Harmony IR archive snapshot (schemaVersion 2).

Stdlib only. Checks structure, not semantics.

  verify.py [ROOT]            metadata only: manifest.json + index.json
  verify.py [ROOT] --full     also every manufacturer index, device, code set
                              and protocol, and the counts in manifest.json
  verify.py [ROOT] --full --sample 2000
                              --full, but only a random sample of device files

ROOT defaults to api/v1 next to this script. Exit code 0 = valid.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA = 2
COUNT_KEYS = {
    "manufacturers", "devices", "devicesWithCodes", "devicesWithTiming",
    "devicesWithControl", "commands", "commandsWithPronto", "codesets", "protocols",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CODESET_RE = re.compile(r"^codesets/[0-9a-f]{2}/[0-9a-f]+\.json$")
POWER_TYPES = {"discrete", "toggle", "none", "unknown"}
# Optional device fields are absent, never null (upstream convention).
DEVICE_REQUIRED = {"manufacturer": str, "model": str, "globalDeviceId": int, "deviceType": int}
DEVICE_NULLABLE = {"codeset"}
# Known upstream quirk: a handful of devices (3 in 20261110) have model: null.
# Reported as warnings so they do not block a sync.
DEVICE_WARN_NULL = {"model"}


class Report:
    def __init__(self, max_errors: int = 50) -> None:
        self.errors: list[str] = []
        self.max_errors = max_errors
        self.total = 0
        self.warnings: list[str] = []

    def warn(self, where: Path | str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def err(self, where: Path | str, msg: str) -> None:
        self.total += 1
        if len(self.errors) < self.max_errors:
            self.errors.append(f"{where}: {msg}")


def load(path: Path, rep: Report) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        rep.err(path, "missing")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        rep.err(path, f"invalid JSON: {exc}")
    return None


def is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_manifest(root: Path, rep: Report) -> dict[str, Any] | None:
    p = root / "manifest.json"
    m = load(p, rep)
    if not isinstance(m, dict):
        if m is not None:
            rep.err(p, "must be an object")
        return None
    if m.get("schemaVersion") != SUPPORTED_SCHEMA:
        rep.err(p, f"schemaVersion {m.get('schemaVersion')!r}, this verifier supports {SUPPORTED_SCHEMA}")
    if not isinstance(m.get("generated"), str) or not DATE_RE.match(m["generated"]):
        rep.err(p, "generated must be YYYY-MM-DD")
    counts = m.get("counts")
    if not isinstance(counts, dict):
        rep.err(p, "counts must be an object")
    else:
        missing = COUNT_KEYS - counts.keys()
        if missing:
            rep.err(p, f"counts missing {sorted(missing)}")
        for k, v in counts.items():
            if not is_int(v) or v < 0:
                rep.err(p, f"counts.{k} must be a non-negative integer")
    if not isinstance(m.get("layout"), dict):
        rep.err(p, "layout must be an object")
    return m


def check_index(root: Path, rep: Report) -> list[dict[str, Any]]:
    p = root / "index.json"
    idx = load(p, rep)
    if not isinstance(idx, list):
        if idx is not None:
            rep.err(p, "must be an array")
        return []
    seen: set[str] = set()
    good = []
    for i, e in enumerate(idx):
        if not (isinstance(e, dict) and isinstance(e.get("n"), str)
                and isinstance(e.get("s"), str) and is_int(e.get("c"))):
            rep.err(p, f"[{i}] needs n:str, s:str, c:int")
            continue
        if "/" in e["s"] or e["s"] in ("", ".", ".."):
            rep.err(p, f"[{i}] unsafe slug {e['s']!r}")
            continue
        if e["s"] in seen:
            rep.err(p, f"[{i}] duplicate slug {e['s']!r}")
        seen.add(e["s"])
        good.append(e)
    return good


def check_device(path: Path, root: Path, rep: Report, codesets: list[str]) -> dict[str, bool]:
    d = load(path, rep)
    flags = {"codes": False, "timing": False, "control": False}
    if not isinstance(d, dict):
        if d is not None:
            rep.err(path, "must be an object")
        return flags
    for k, t in DEVICE_REQUIRED.items():
        v = d.get(k)
        if v is None and k in DEVICE_WARN_NULL and k in d:
            rep.warn(path, f"{k} is null")
            continue
        if not (is_int(v) if t is int else isinstance(v, t)):
            rep.err(path, f"{k} must be {t.__name__}")
    for k, v in d.items():
        if v is None and k not in DEVICE_NULLABLE | DEVICE_WARN_NULL:
            rep.err(path, f"optional field {k!r} is null (should be absent)")
    cs = d.get("codeset")
    if cs is not None:
        if not isinstance(cs, str) or not CODESET_RE.match(cs):
            rep.err(path, f"bad codeset path {cs!r}")
        else:
            flags["codes"] = True
            codesets.append(cs)
            if not (root / cs).is_file():
                rep.err(path, f"codeset {cs} does not exist")
    elif "codeset" not in d:
        rep.err(path, "codeset key missing (use null for no commands)")
    power = d.get("power")
    if power is not None and (not isinstance(power, dict) or power.get("type") not in POWER_TYPES):
        rep.err(path, f"power.type must be one of {sorted(POWER_TYPES)}")
    flags["timing"] = isinstance(d.get("timing"), dict)
    flags["control"] = any(k in d for k in ("power", "inputs", "channelTuning", "states"))
    return flags


def check_codeset(path: Path, rep: Report) -> tuple[int, int]:
    c = load(path, rep)
    cmds = c.get("commands") if isinstance(c, dict) else None
    if not isinstance(cmds, list):
        if c is not None:
            rep.err(path, "commands must be an array")
        return 0, 0
    pronto = 0
    for i, cmd in enumerate(cmds):
        if not isinstance(cmd, dict) or not isinstance(cmd.get("name"), str):
            rep.err(path, f"commands[{i}] needs name:str")
            continue
        if "pronto" in cmd:
            if isinstance(cmd["pronto"], str):
                pronto += 1
            else:
                rep.err(path, f"commands[{i}].pronto must be a string")
    return len(cmds), pronto


def check_full(root: Path, manifest: dict[str, Any], mfrs: list[dict[str, Any]],
               rep: Report, sample: int | None) -> None:
    device_files: list[Path] = []
    for e in mfrs:
        mdir = root / "devices" / e["s"]
        midx = load(mdir / "index.json", rep)
        if not isinstance(midx, list):
            continue
        if len(midx) != e["c"]:
            rep.err(mdir / "index.json", f"{len(midx)} models, index.json says {e['c']}")
        for i, m in enumerate(midx):
            f = m.get("f") if isinstance(m, dict) else None
            if not isinstance(f, str) or "/" in f or not f.endswith(".json") or f == "index.json":
                rep.err(mdir / "index.json", f"[{i}] bad file name {f!r}")
                continue
            device_files.append(mdir / f)

    counts = manifest.get("counts", {})
    full_scan = sample is None or sample >= len(device_files)
    if not full_scan:
        device_files = random.Random(0).sample(device_files, sample)
    referenced: list[str] = []
    with_codes = with_timing = with_control = 0
    for f in device_files:
        flags = check_device(f, root, rep, referenced)
        with_codes += flags["codes"]
        with_timing += flags["timing"]
        with_control += flags["control"]

    codeset_files = sorted((root / "codesets").glob("*/*.json"))
    sizes: dict[str, tuple[int, int]] = {}
    for f in codeset_files:
        sizes[str(f.relative_to(root))] = check_codeset(f, rep)
    # manifest counts commands per device, so shared code sets count once per device.
    commands = sum(sizes.get(cs, (0, 0))[0] for cs in referenced)
    with_pronto = sum(sizes.get(cs, (0, 0))[1] for cs in referenced)

    pidx_path = root / "protocols" / "index.json"
    pidx = load(pidx_path, rep)
    nprot = 0
    if isinstance(pidx, list):
        for i, p in enumerate(pidx):
            f = p.get("f") if isinstance(p, dict) else None
            if not isinstance(f, str) or "/" in f:
                rep.err(pidx_path, f"[{i}] bad file name {f!r}")
            elif not isinstance(load(root / "protocols" / f, rep), dict):
                rep.err(root / "protocols" / f, "must be an object")
            nprot += 1

    def expect(key: str, got: int) -> None:
        if key in counts and counts[key] != got:
            rep.err("manifest.json", f"counts.{key}={counts[key]} but found {got}")

    expect("manufacturers", len(mfrs))
    expect("codesets", len(codeset_files))
    expect("protocols", nprot)
    if full_scan:
        expect("commands", commands)
        expect("commandsWithPronto", with_pronto)
        expect("devices", len(device_files))
        expect("devicesWithCodes", with_codes)
        expect("devicesWithTiming", with_timing)
        expect("devicesWithControl", with_control)
        unused = set(sizes) - set(referenced)
        if unused:
            rep.err("codesets", f"{len(unused)} code sets not referenced by any device")
    print(f"checked {len(device_files)} devices, {len(codeset_files)} code sets, "
          f"{commands} device commands, {nprot} protocols")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", type=Path,
                    default=Path(__file__).resolve().parent.parent / "api" / "v1")
    ap.add_argument("--full", action="store_true", help="validate the whole tree")
    ap.add_argument("--sample", type=int, help="with --full, check only N random device files")
    args = ap.parse_args()

    rep = Report()
    manifest = check_manifest(args.root, rep)
    mfrs = check_index(args.root, rep)
    if manifest is not None:
        expected = manifest.get("counts", {}).get("manufacturers")
        if expected is not None and expected != len(mfrs):
            rep.err("index.json", f"{len(mfrs)} manufacturers, manifest says {expected}")
    if args.full and manifest is not None:
        check_full(args.root, manifest, mfrs, rep, args.sample)

    for w in rep.warnings[:20]:
        print(f"WARN  {w}", file=sys.stderr)
    if len(rep.warnings) > 20:
        print(f"... and {len(rep.warnings) - 20} more warnings", file=sys.stderr)
    for e in rep.errors:
        print(f"ERROR {e}", file=sys.stderr)
    if rep.total > len(rep.errors):
        print(f"... and {rep.total - len(rep.errors)} more", file=sys.stderr)
    print("OK" if rep.total == 0 else f"FAILED with {rep.total} error(s)")
    return 0 if rep.total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
