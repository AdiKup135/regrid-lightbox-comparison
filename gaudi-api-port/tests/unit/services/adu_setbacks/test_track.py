"""Unit tests for the track decision — the size and height gates of Gov. Code
§ 66323(a)(2), the one-per-lot entitlement, and the Q1 assumption flags."""
from __future__ import annotations

import pytest

from services.compute.adu_setbacks.track import (
  TRACK_LOCAL_66314,
  TRACK_STATE_66323,
  UnitFacts,
  determine_track,
  state_height_limit_ft,
)


def _unit(**overrides) -> UnitFacts:
  base = dict(unit_size=800.0, unit_height_in_feet=16.0, near_transit=False)
  base.update(overrides)
  return UnitFacts(**base)


class TestSizeGate:
  def test_800_sqft_is_on_the_state_track(self) -> None:
    decision = determine_track(_unit(unit_size=800.0))
    assert decision.track == TRACK_STATE_66323
    assert decision.reasons == ['fits_66323_a2']

  def test_801_sqft_is_local(self) -> None:
    decision = determine_track(_unit(unit_size=800.5))
    assert decision.track == TRACK_LOCAL_66314
    assert 'unit_size_over_800_sqft' in decision.reasons


class TestHeightGate:
  def test_16_ft_anywhere(self) -> None:
    assert determine_track(_unit(unit_height_in_feet=16.0, near_transit=False)).track == TRACK_STATE_66323

  def test_17_ft_needs_transit(self) -> None:
    away = determine_track(_unit(unit_height_in_feet=17.0, near_transit=False))
    near = determine_track(_unit(unit_height_in_feet=17.0, near_transit=True))
    assert away.track == TRACK_LOCAL_66314 and 'unit_height_over_16_ft' in away.reasons
    assert near.track == TRACK_STATE_66323
    # The buffer is straight-line; the statute says walking distance (FOR-1422).
    assert 'transit_straight_line_buffer' in near.flags

  def test_18_ft_near_transit_passes_18_point_1_does_not(self) -> None:
    assert determine_track(_unit(unit_height_in_feet=18.0, near_transit=True)).track == TRACK_STATE_66323
    over = determine_track(_unit(unit_height_in_feet=18.1, near_transit=True))
    assert over.track == TRACK_LOCAL_66314 and 'unit_height_over_18_ft' in over.reasons

  def test_roof_pitch_allowance_is_not_modelled(self) -> None:
    # 20 ft with matching roof pitch is legal near transit; by decision it is
    # left to a human override, so the engine sends it to the local track.
    assert determine_track(_unit(unit_height_in_feet=20.0, near_transit=True)).track == TRACK_LOCAL_66314

  def test_failed_transit_lookup_grants_only_16_ft_and_flags(self) -> None:
    decision = determine_track(_unit(unit_height_in_feet=17.0, near_transit=None))
    assert decision.track == TRACK_LOCAL_66314
    assert 'transit_lookup_failed' in decision.flags
    assert state_height_limit_ft(None) == 16.0


class TestLotGates:
  def test_existing_detached_adu_closes_the_state_track(self) -> None:
    decision = determine_track(_unit(existing_detached_adu=True))
    assert decision.track == TRACK_LOCAL_66314
    assert 'a2_entitlement_already_used' in decision.reasons
    assert 'existing_detached_adu_declared' in decision.flags
    assert 'existing_detached_adu_assumed_no' not in decision.flags

  def test_q1_assumptions_are_always_flagged(self) -> None:
    flags = determine_track(_unit()).flags
    for expected in ('zone_use_assumed_residential', 'dwelling_type_assumed_sfr',
                     'sb9_split_assumed_no', 'existing_detached_adu_assumed_no'):
      assert expected in flags

  def test_sb9_split_is_allowed_but_unverified(self) -> None:
    decision = determine_track(_unit(sb9_split=True))
    assert decision.track == TRACK_STATE_66323
    assert 'sb9_split_declared_unit_count_unverified' in decision.flags
    assert 'sb9_split_assumed_no' not in decision.flags


class TestInputs:
  def test_non_positive_numbers_are_rejected(self) -> None:
    with pytest.raises(AssertionError):
      determine_track(_unit(unit_size=0))
    with pytest.raises(AssertionError):
      determine_track(_unit(unit_height_in_feet=-1))
