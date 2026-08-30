"""
cli.py
------
Stdin/stdout JSON runner for label_edges — the site repo's debug bridge.

This is NOT part of the gaudi-api drop-in. In gaudi-api the same assembly
happens in a Flask route: parse the request, build EdgeLabelingInput, call
label_edges, return result.to_dict(). This script does exactly that over
stdin/stdout so the site repo's Express backend can run the Python engine
server-side, the way gaudi will, while the debug UI shows the output.

Request shape (stdin, one JSON object) — the wire names match the Zoneomics
and Google payloads they come from:

  {
    "subject":   {apn, address, lat, lng, boundary},      // Zoneomics parcel
    "neighbors": [ ...same shape... ],                    // Zoneomics parcels
    "front_rule": "shortest_frontage" | ...,              // jurisdiction db
    "front_rule_overrides": [...],                        // jurisdiction db, verbatim
    "zone": {"zone_code": ..., "zone_type": ...},         // Zoneomics zone_details
    "subject_street_name": "Madrono Avenue",              // Google Places `route`
    "user_front_override_edge_index": 2,                  // UI election
    "google_api_key": "..."                               // enables the Roads namer
  }

Only subject/neighbors are required. With google_api_key absent the engine
runs census-only — fully offline.

Standalone script: prints to stdout by design (see gaudi-api AGENTS.md — the
no-print rule binds live request paths, and the gaudi-api version of this
assembly logs through fx_logger instead).
"""
import json
import sys

from .edge_labeling import (
  EdgeLabelingInput,
  FrontRuleOverride,
  ZoneomicsParcel,
  label_edges,
)


def _parcel(record: dict) -> ZoneomicsParcel:
  return ZoneomicsParcel(
    apn=str(record.get("apn", "")),
    address=record.get("address") or "",
    lat=float(record["lat"]),
    lng=float(record["lng"]),
    boundary=record["boundary"],
  )


def main() -> int:
  request = json.load(sys.stdin)

  street_namer = None
  google_api_key = request.get("google_api_key")
  if google_api_key:
    from .street_naming import make_google_roads_namer
    street_namer = make_google_roads_namer(google_api_key)

  overrides = [FrontRuleOverride.from_db(o) for o in request.get("front_rule_overrides") or []]
  result = label_edges(EdgeLabelingInput(
    subject=_parcel(request["subject"]),
    neighbors=[_parcel(n) for n in request.get("neighbors") or []],
    front_rule=request.get("front_rule"),
    front_rule_overrides=overrides or None,
    zone=request.get("zone"),
    user_front_override_edge_index=request.get("user_front_override_edge_index"),
    subject_street_name=request.get("subject_street_name"),
    street_namer=street_namer,
  ))
  json.dump(result.to_dict(), sys.stdout)
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except Exception as error:  # one JSON error shape for the Express caller
    json.dump({"error": str(error)}, sys.stdout)
    sys.exit(1)
