# Copyright (c) Microsoft. All rights reserved.

import hashlib
from collections import defaultdict

from af_watch.models import Hypothesis, Opportunity, OpportunityType


class Consolidator:
    def consolidate(
        self,
        *,
        strategic: list[Opportunity],
        tactical_hypotheses: list[Hypothesis],
    ) -> list[Opportunity]:
        tactical = self._hypotheses_to_opportunities(tactical_hypotheses)
        all_opps = list(strategic) + tactical
        deduped = self._dedup(all_opps)
        return self._sort(deduped)

    def retier_after_repro(self, opps: list[Opportunity]) -> list[Opportunity]:
        for opp in opps:
            if opp.repro_status == "confirmed" and opp.type in (
                OpportunityType.BUG_FIX, OpportunityType.BUG_PORT
            ):
                opp.tier = 1
        return self._sort(opps)

    def _hypotheses_to_opportunities(self, hyps: list[Hypothesis]) -> list[Opportunity]:
        groups: dict[tuple[str, str], list[Hypothesis]] = defaultdict(list)
        for h in hyps:
            sig = self._signature(h.invariant)
            groups[(h.region_id, sig)].append(h)

        out: list[Opportunity] = []
        for (region_id, _sig), group in groups.items():
            personas = sorted({h.persona for h in group})
            best_conf = max(h.confidence for h in group)
            severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            severity = max(group, key=lambda h: severity_rank.get(h.severity, 0)).severity

            tier = 5
            if len(personas) >= 2:
                tier = 2
            risk = "medium" if severity in ("critical", "high") else "low"
            sample = group[0]
            target = f"{sample.repo}:{sample.file}"
            opp = Opportunity(
                id=f"{region_id}-{self._signature(sample.invariant)[:6]}",
                type=OpportunityType.BUG_FIX,
                target=target,
                action=f"PR (fix: {sample.invariant[:60]})",
                evidence=f"{len(personas)} persona(s); top confidence {best_conf:.2f}",
                effort="2h",
                risk=risk,
                risk_rationale=f"severity={severity}",
                rationale=sample.violation_condition,
                tier=tier,
                supporting_personas=personas,
            )
            out.append(opp)
        return out

    @staticmethod
    def _signature(text: str) -> str:
        normalized = " ".join(text.lower().split())
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()  # noqa: S324 — non-crypto fingerprint

    def _dedup(self, opps: list[Opportunity]) -> list[Opportunity]:
        seen: dict[tuple[str, str], Opportunity] = {}
        for opp in opps:
            key = (opp.type.value, opp.target)
            if key in seen:
                if opp.tier < seen[key].tier:
                    seen[key] = opp
            else:
                seen[key] = opp
        return list(seen.values())

    @staticmethod
    def _effort_minutes(effort: str) -> int:
        effort = effort.strip().lower()
        unit_to_min = {
            "min": 1,
            "h": 60, "hour": 60, "hours": 60,
            "d": 480, "day": 480, "days": 480,
            "w": 2400, "week": 2400, "weeks": 2400,
        }
        for unit, mult in unit_to_min.items():
            if unit in effort:
                num = "".join(c for c in effort if c.isdigit() or c == ".")
                try:
                    return int(float(num) * mult) if num else 60
                except ValueError:
                    return 60
        return 60

    @staticmethod
    def _risk_rank(risk: str) -> int:
        return {"very low": 0, "low": 1, "medium": 2, "high": 3}.get(risk, 99)

    def _sort(self, opps: list[Opportunity]) -> list[Opportunity]:
        return sorted(
            opps,
            key=lambda o: (o.tier, self._effort_minutes(o.effort), self._risk_rank(o.risk)),
        )
