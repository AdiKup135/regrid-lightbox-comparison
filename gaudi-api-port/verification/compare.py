import json, math

ts = {c["name"]: c for c in json.load(open("ts_out.json"))}
py = {c["name"]: c for c in json.load(open("py_out.json"))}

diffs = []
def cmp(path, a, b):
  if isinstance(a, float) or isinstance(b, float):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
      if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9):
        diffs.append(f"{path}: TS={a} PY={b}")
      return
  if type(a) is not type(b) and not (isinstance(a,(int,float)) and isinstance(b,(int,float))):
    diffs.append(f"{path}: type TS={type(a).__name__} PY={type(b).__name__}"); return
  if isinstance(a, dict):
    for k in sorted(set(a) | set(b)):
      # Deliberate additive extensions of the Python port over the TS
      # reference. Each entry must be additive-only: absent when its input
      # feature is unused, never changing any reference-era field.
      if k in ("streetNameSource",) and k not in a: continue
      if k not in a: diffs.append(f"{path}.{k}: missing in TS (PY={b[k]!r})")
      elif k not in b: diffs.append(f"{path}.{k}: missing in PY (TS={a[k]!r})")
      else: cmp(f"{path}.{k}", a[k], b[k])
  elif isinstance(a, list):
    if len(a) != len(b):
      diffs.append(f"{path}: length TS={len(a)} PY={len(b)}"); return
    for i, (x, y) in enumerate(zip(a, b)): cmp(f"{path}[{i}]", x, y)
  else:
    if a != b: diffs.append(f"{path}: TS={a!r} PY={b!r}")

for name in ts:
  cmp(name, ts[name], py[name])

# Flags are a set in the TS (insertion-ordered Set) — compare order-insensitively too.
order_only = [d for d in diffs if ".flags[" in d]
print(f"cases: {len(ts)}   total field diffs: {len(diffs)}")
for d in diffs[:40]: print("  ", d)
if len(diffs) > 40: print(f"   ... and {len(diffs)-40} more")

# Summarize what was actually exercised.
tags, bases, flags, confs = set(), set(), set(), set()
for c in py.values():
  r = c.get("result") or {}
  flags |= set(r.get("flags", []))
  for e in r.get("edges", []):
    tags.add(e["tag"]); bases.add(e["basis"]); confs.add(e["confidence"]); flags |= set(e["flags"])
print("\ncoverage")
print("  tags       :", sorted(tags))
print("  bases      :", sorted(bases))
print("  confidences:", sorted(confs))
print("  flags      :", sorted(flags))
print("  total edges compared:", sum(len((c.get('result') or {}).get('edges', [])) for c in py.values()))
