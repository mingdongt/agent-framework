# Copyright (c) Microsoft. All rights reserved.

from af_watch.consolidator import Consolidator
from af_watch.models import Hypothesis, Opportunity, OpportunityType


def _opp(
    *,
    id_: str = "x",
    type_: OpportunityType = OpportunityType.FEATURE_PARITY,
    tier: int = 4,
    target: str = "t",
    repro: str = "not_attempted",
) -> Opportunity:
    return Opportunity(
        id=id_, type=type_, target=target,
        action="a", evidence="e", effort="2h",
        risk="low", risk_rationale="x", rationale="r", tier=tier,
        repro_status=repro,  # type: ignore[arg-type]
    )


def _hyp(*, persona: str, region_id: str = "r1", confidence: float = 0.7) -> Hypothesis:
    return Hypothesis(
        region_id=region_id, repo="microsoft/agent-framework", file="python/x.py",
        persona=persona,
        invariant="i", violation_condition="v", repro_sketch="s",
        severity="medium", confidence=confidence,
    )


def test_promotes_two_persona_hypothesis_to_tier_2() -> None:
    hyps = [
        _hyp(persona="security_boundary"),
        _hyp(persona="async_concurrency"),
    ]
    consolidator = Consolidator()
    opps = consolidator.consolidate(strategic=[], tactical_hypotheses=hyps)
    assert len(opps) == 1
    assert opps[0].tier == 2
    assert set(opps[0].supporting_personas) == {"security_boundary", "async_concurrency"}
    assert opps[0].target.startswith("microsoft/agent-framework:python/x.py")


def test_single_persona_hypothesis_tier_5() -> None:
    hyps = [_hyp(persona="security_boundary")]
    opps = Consolidator().consolidate(strategic=[], tactical_hypotheses=hyps)
    assert opps[0].tier == 5


def test_repro_confirmed_hypothesis_tier_1() -> None:
    hyps = [_hyp(persona="security_boundary")]
    base = Consolidator().consolidate(strategic=[], tactical_hypotheses=hyps)
    base[0].repro_status = "confirmed"
    opps = Consolidator().retier_after_repro(base)
    assert opps[0].tier == 1


def test_dedup_by_target_and_type() -> None:
    a = _opp(id_="a", target="file.py:L10")
    b = _opp(id_="b", target="file.py:L10", tier=2)  # better tier
    opps = Consolidator().consolidate(strategic=[a, b], tactical_hypotheses=[])
    assert len(opps) == 1
    assert opps[0].tier == 2


def test_orders_by_tier_then_effort() -> None:
    o_t1 = _opp(id_="t1", tier=1, target="t1")
    o_t2 = _opp(id_="t2", tier=2, target="t2")
    o_t4 = _opp(id_="t4", tier=4, target="t4")
    opps = Consolidator().consolidate(strategic=[o_t4, o_t1, o_t2], tactical_hypotheses=[])
    assert [o.id for o in opps] == ["t1", "t2", "t4"]
