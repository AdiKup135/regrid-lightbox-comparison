import json, sys
sys.path.insert(0, "/Users/adi/Documents/formX/site/gaudi-api-port")
from services.compute.parcel_edges.edge_labeling import (
  EdgeLabelingInput, FrontRuleOverride, ZoneomicsParcel, label_edges)

def parcel(d): return ZoneomicsParcel(**d)

out = []
for c in json.load(open("cases.json")):
  try:
    res = label_edges(EdgeLabelingInput(
      subject=parcel(c["subject"]),
      neighbors=[parcel(n) for n in c["neighbors"]],
      front_rule=c.get("frontRule"),
      front_rule_overrides=[FrontRuleOverride.from_db(o) for o in c["frontRuleOverrides"]]
                            if c.get("frontRuleOverrides") else None,
      zone=c.get("zone"),
      user_front_override_edge_index=c.get("userFrontOverrideEdgeIndex")))
    out.append({"name": c["name"], "result": res.to_dict()})
  except Exception as e:
    out.append({"name": c["name"], "error": str(e)})
json.dump(out, open("py_out.json", "w"))
print("py cases:", len(out), "errors:", sum(1 for o in out if "error" in o))
