"""
street_names.py
---------------
The single owner of street-name normalization.

Street names reach this engine from three sources that spell them differently:
a Zoneomics situs address ("1590 Madrono AV"), a Google Places ``route``
component ("Madrono Avenue"), and a Google Roads API road name. They are only
comparable if all three collapse to one key, so every producer routes through
``normalize_street_key`` and every comparison goes through ``street_keys_match``.

Two rules keep the key safe to compare on:

* Suffixes are canonicalized but **kept**, so "Oak St" and "Oak Ave" stay
  different streets.
* Directionals are canonicalized but **kept**, so "N Main St" and "S Main St"
  stay different streets.

Comparison is exact equality on the key. Substring matching is deliberately not
offered: "Oakland Ave" contains "Oak Ave" once suffixes are stripped, and a name
that normalizes to empty would otherwise match everything.
"""
from typing import Dict, List, Optional, Set

STREET_SUFFIXES: Set[str] = {
  "ave", "avenue", "st", "street", "rd", "road", "dr", "drive", "blvd",
  "boulevard", "ln", "lane", "ct", "court", "pl", "place", "way", "ter",
  "terrace", "cir", "circle", "hwy", "highway", "pkwy", "parkway", "aly",
  "alley",
}

SUFFIX_CANON: Dict[str, str] = {
  "avenue": "ave", "av": "ave", "street": "st", "road": "rd", "drive": "dr",
  "boulevard": "blvd", "lane": "ln", "court": "ct", "place": "pl", "wy": "way",
  "terrace": "ter", "circle": "cir", "highway": "hwy", "parkway": "pkwy",
  "alley": "aly",
}

# Directionals are canonicalized to their short form and kept as tokens, so
# "N Main St" and "S Main St" do not collapse onto each other.
DIRECTIONAL_CANON: Dict[str, str] = {
  "north": "n", "south": "s", "east": "e", "west": "w",
  "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}

# A house number: digits, optionally with fractions or hyphenated ranges.
_NUMBER_CHARS = set("0123456789/-")

# Cap on tokens taken before a suffix is seen, so a full address without a
# recognizable suffix still yields a usable key instead of the whole line.
_MAX_TOKENS = 4
_UNSUFFIXED_TOKENS = 3


def _is_house_number(token: str) -> bool:
  return bool(token) and token[0].isdigit() and all(c in _NUMBER_CHARS for c in token)


def _tokenize(value: str) -> List[str]:
  return value.strip().lower().replace(".", "").replace(",", "").split()


def normalize_street_key(name: Optional[str]) -> Optional[str]:
  """Reduce a bare street name to its comparable key.

  Takes a name only — no house number, no city, no state. Use
  ``extract_street_name`` for a full situs address.

  "Madrono Avenue" and "Madrono AV" both become "madrono ave"; "N Main St"
  becomes "n main st" and stays distinct from "s main st".

  @param name A street name, e.g. a Google ``route`` component or road name.

  @return The comparable key, or None when nothing usable is present.
  """
  if not name:
    return None
  return _key_from_tokens(_tokenize(name))


def _key_from_tokens(tokens: List[str]) -> Optional[str]:
  """Shared tail of both producers: canonicalize, stop at the first suffix."""
  out: List[str] = []
  for token in tokens:
    if len(out) >= _MAX_TOKENS:
      break
    canon = SUFFIX_CANON.get(token, DIRECTIONAL_CANON.get(token, token))
    out.append(canon)
    if canon in STREET_SUFFIXES:
      return " ".join(out)
  return " ".join(out[:_UNSUFFIXED_TOKENS]) or None


def extract_street_name(address: Optional[str]) -> Optional[str]:
  """Reduce a full situs address to the same key ``normalize_street_key`` yields.

  "804 Lennox Ct Sunnyvale CA" -> "lennox ct". Leading house numbers are
  skipped, then the shared normalizer takes over.

  @param address Situs address as it appears in the parcel record.

  @return The comparable key, or None when nothing usable is present.
  """
  if not address:
    return None
  tokens = _tokenize(address)
  i = 0
  while i < len(tokens) and _is_house_number(tokens[i]):
    i += 1
  if i >= len(tokens):
    return None
  return _key_from_tokens(tokens[i:])


def street_keys_match(left: Optional[str], right: Optional[str]) -> bool:
  """True when two normalized keys name the same street.

  Exact equality only. Substring containment is not a match: "oakland ave"
  must not match "oak ave", and an empty key must not match anything.
  """
  return bool(left) and bool(right) and left == right
