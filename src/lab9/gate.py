"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    from lab9.graders import GRADERS

    problems: list[str] = []
    rows, man = pr.get("rows") or [], pr.get("manifest") or {}
    for mid, val in (pr.get("metrics") or {}).items():
        if isinstance(val, float) and not math.isfinite(val):
            problems.append(f"metric {mid} is {val}")
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): graders crashed, scores are incomplete")

    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item_id, seed) row(s)")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != base_keys:
        missing, extra = len(base_keys - set(keys)), len(set(keys) - base_keys)
        problems.append(f"(item_id, seed) set differs from the baseline's: {missing} missing, {extra} extra")

    graded = [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]
    for mid in graded:
        vals = [r.get(mid) for r in rows]
        nulls = sum(not isinstance(v, bool) for v in vals)      # None, NaN, a string: not a grade
        if nulls:
            problems.append(f"metric {mid}: {nulls} row(s) have no score (crashed grader drops out of the mean)")
            continue
        # The report's aggregate must be what its own rows say (same rule as lab9.eval.aggregate).
        if vals and mid in (pr.get("metrics") or {}) and isinstance(pr["metrics"][mid], (int, float)):
            mine = sum(vals) if mid in ("secret_leak", "approval_bypass") else round(sum(vals) / len(vals), 4)
            if math.isfinite(pr["metrics"][mid]) and abs(mine - pr["metrics"][mid]) > 1e-9:
                problems.append(f"metric {mid} is {pr['metrics'][mid]} but its rows give {mine}: report was edited")

    # pass_5 / pass^k / pass@k are derived from pass_rate rows; a hand-edited value has no row to back it.
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        by_item.setdefault(r.get("item_id"), []).append(r.get("pass_rate") is True)
    for mid, val in (pr.get("metrics") or {}).items():
        kind, _, k = mid.rpartition("_")
        if kind not in ("pass", "pass_hat", "pass_at") or not k.isdigit() or not isinstance(val, (int, float)):
            continue
        if not by_item or not math.isfinite(val) or min(len(v) for v in by_item.values()) < int(k):
            continue
        if kind == "pass":
            est = [float(all(v)) for v in by_item.values()]
        else:
            fn = stats.pass_hat_k if kind == "pass_hat" else stats.pass_at_k
            est = [fn(len(v), sum(v), int(k)) for v in by_item.values()]
        mine = round(sum(est) / len(est), 4)
        if abs(mine - val) > 1e-9:
            problems.append(f"metric {mid} is {val} but its rows give {mine}: report was edited")

    tags = lambda rep: {r.get("item_id"): frozenset(r.get("slices") or []) for r in rep.get("rows") or []}
    pr_tags, base_tags = tags(pr), tags(base)
    moved = sorted(i for i in pr_tags.keys() & base_tags.keys() if pr_tags[i] != base_tags[i])
    if moved:
        problems.append(f"slice tags differ from the baseline's for {len(moved)} item(s), e.g. {moved[0]}")

    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version: thresholds may only get stricter. Returns one problem per loosening."""
    out: list[str] = []

    def looser(label: str, new: dict | None, old: dict, new_th: dict, old_th: dict) -> None:
        if new is None:
            out.append(f"ratchet: {label} was removed")
            return
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: {label} is no longer blocking")
        for key, worse in (("min", lambda n, o: n < o), ("max", lambda n, o: n > o), ("max_increase", lambda n, o: n > o)):
            if key in old_th and (key not in new_th or worse(new_th[key], old_th[key])):
                out.append(f"ratchet: {label} {key} loosened {old_th[key]} -> {new_th.get(key)}")
        if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
            out.append(f"ratchet: {label} dropped no_significant_drop")

    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for old in base_spec.get("metrics") or []:
        new = new_m.get(old["id"])
        looser(f"metric {old['id']}", new, old, (new or {}).get("threshold") or {}, old.get("threshold") or {})
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        new = new_s.get((old["name"], old["metric"]))
        looser(f"slice {old['name']}/{old['metric']}", new, old, new or {}, old)
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"            # an empty slice hides a regression: never treat it as a pass
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<34} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
