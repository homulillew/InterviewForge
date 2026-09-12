from interview_forge.schemas.models import Applicability, ChallengeOperator as O, ClaimType

TRANSFERABLE = {
    O.WHY_NECESSARY,
    O.WHY_NOT_SIMPLER,
    O.WHY_NOT_ALTERNATIVE,
    O.METRIC_PRESSURE,
    O.BASELINE_PRESSURE,
    O.COUNTEREXAMPLE,
    O.BOUNDARY_PRESSURE,
    O.CONSISTENCY_PRESSURE,
    O.SCALE_PRESSURE,
}


def applicability(claim, surface, pattern):
    shared = {t.casefold() for t in claim.technologies} & {t.casefold() for t in pattern.applicable_topics}
    if pattern.challenge_operator == O.OWNERSHIP_PRESSURE and claim.claim_type != ClaimType.ownership:
        return Applicability.reject, "Ownership was not asserted in this resume claim"
    if shared:
        return Applicability.direct, "Shared resume technology: " + ", ".join(sorted(shared))
    if (
        pattern.challenge_operator in TRANSFERABLE
        and surface.dimension == pattern.attack_dimension
        and claim.claim_type in pattern.trigger_claim_types
    ):
        return (
            Applicability.transferable,
            "Transfer abstract operator only; replace all source technology with the resume target",
        )
    if pattern.attack_dimension == surface.dimension and pattern.challenge_operator != O.FUNDAMENTAL_DRILL:
        return (
            Applicability.style_only,
            "Only probe frequency is reusable; source content does not match the resume",
        )
    return Applicability.reject, "No resume-relevant content or transferable operator"
