"""AC topology resolution — is this site split-phase, single-phase or three-phase?

The FranklinWH API reports every AC measurement as an L1/L2 pair regardless of
what is installed. On a split-phase North American site those are two real 120 V
legs in antiphase. On an AU/NZ single-phase site they are an artifact: the
supply is ``230/240 VAC L/N/PE`` (CONFIRMED — *System Datasheet aGate X-01-AU &
aPower X-02-AU*), so there is no second active conductor and the "legs" are one
L-N measurement halved or repeated.

OBSERVED on a live AU gateway: ``L1 119.7 V``, ``L2 119.7 V``,
``Line 239.4 V``, at 49.93 Hz.

See ``docs/AC_TOPOLOGY.md``. Resolved here once rather than re-derived in each
renderer — ``discover`` had this right while ``bms``, ``support`` and ``schema``
did not, which is precisely what per-renderer logic produces.
"""

#: ``countryId`` for Australia. AU/NZ supply is L/N/PE single-phase, or 415 V
#: three-phase — neither is split-phase, so the L1/L2 pair is never two real
#: legs there whatever ``isThreePhaseInstall`` says.
COUNTRY_ID_AU = 3

#: Markets whose residential supply is split-phase, where L1/L2 ARE two real
#: legs. Kept as a set rather than "not AU" so an unlisted market resolves to
#: unknown instead of being silently assumed split-phase.
#:
#: ASSUMED, and weaker than the AU branch: the US entry rests on the market
#: standard and the US datasheets, **not on an observation**. The capture corpus
#: is a single Australian gateway and no US metrics have been obtained, so
#: nobody has confirmed what a split-phase site actually reports in these
#: fields. See DEF-AC-TOPOLOGY-NO-US-SAMPLE.
SPLIT_PHASE_COUNTRY_IDS = frozenset({2})  # United States


def legs_are_real(*, three_phase=None, country_id=None):
    """Are the reported L1/L2 values two independent conductors?

    Parameters
    ----------
    three_phase : bool | int | None
        ``isThreePhaseInstall``. ``None`` when the caller does not have it.
    country_id : int | None
        Site ``countryId``. ``None`` when unavailable.

    Returns
    -------
    bool | None
        ``True``  — split-phase; L1/L2 are two real legs.
        ``False`` — they are an API artifact; use the line value instead.
        ``None``  — not determinable. Callers must **show** the values and
        caveat them rather than hide them: discarding data on a guess is worse
        than presenting it with a qualification.

    Note
    ----
    **ASSUMED**, per AP-14: that ``country_id`` implies supply topology. It
    matches the AU/NZ and US datasheets but is inferred from market, not read
    from the device. A US 208 V commercial install may not follow the
    residential rule.

    No **cloud** field is known to report topology directly. The Modbus
    register map may expose an ``ACType``-style value that would settle it from
    the device instead of by inference — untested, and no such register has
    been located here. See DEF-PHASE-FLAG-AMBIGUOUS.
    """
    if three_phase:
        # Three-phase is L1/L2/L3. How those map onto a two-leg field pair is
        # NOT established — no three-phase capture exists in the corpus — so
        # the pair is certainly not "two split-phase legs".
        return False
    if country_id == COUNTRY_ID_AU:
        return False
    if country_id in SPLIT_PHASE_COUNTRY_IDS:
        return True
    return None


def leg_caveat(legs_real):
    """One-line caveat for a renderer, or None when no qualification is needed."""
    if legs_real is True:
        return None
    if legs_real is False:
        return ("L1/L2 are reported by the API for every install; this site is "
                "not split-phase, so use the Line value as the real measurement")
    return ("AC topology undetermined — if this site is single-phase, L1/L2 are "
            "an API artifact rather than two conductors")
