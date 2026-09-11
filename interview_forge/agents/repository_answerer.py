from pydantic import Field
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.quality import check_general_knowledge
from interview_forge.repository.retrieval import select_evidence
from interview_forge.schemas.models import Answer, CapabilityClaim, InterviewQuestion, Model, RepoEvidence


class AnswerDraft(Model):
    evidence_ids: list[str] = Field(default_factory=list)
    technical_explanation: str = Field(min_length=1, max_length=5000)
    technology_decision: str = Field(min_length=1, max_length=3000)
    failure_modes: list[str]
    unsupported_claims: list[str]
    likely_followups: list[str]
    related_knowledge: list[str]
    improvement_directions: list[str]
    signals: list[str]


class RepositoryAnswerer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def answer(self, question: InterviewQuestion, claim: CapabilityClaim, evidences: list[RepoEvidence]) -> Answer:
        selected, matches = select_evidence(question, claim, evidences)
        topic = TOPICS[topic_for(claim.topic)]
        if self.client:
            draft = self.client.structured_generate(prompt("repo_answerer"), {
                "question": question.model_dump(), "claim": claim.model_dump(exclude={"mastery"}),
                "evidences": [e.model_dump() for e in selected]}, AnswerDraft)
        else:
            explanation = topic.mechanism
            if topic.prerequisite in question.subtopic or question.subtopic == "fundamentals":
                explanation = topic.prerequisite_explanation
            if "评测" in question.subtopic:
                explanation = topic.validation
            if question.dimension.value == "Evaluation / Measurement":
                explanation = topic.validation
            elif question.dimension.value == "Failure Handling":
                explanation = topic.failure + " " + topic.mechanism
            elif question.dimension.value in {"Technology Decision", "Trade-off Awareness"}:
                explanation = topic.decision
            draft = AnswerDraft(evidence_ids=[e.id for e in selected[:3]], technical_explanation=explanation,
                technology_decision=topic.decision, failure_modes=[topic.failure],
                unsupported_claims=[], likely_followups=list(topic.questions[1:4]),
                related_knowledge=[topic.title, topic.prerequisite],
                improvement_directions=["改进方向（未证明已实现）：" + topic.validation], signals=[])
        valid = {e.id: e for e in selected}
        if any(eid not in valid for eid in draft.evidence_ids):
            raise ValueError("Answerer cited evidence outside the provided claim context")
        for text in [draft.technical_explanation, draft.technology_decision, *draft.failure_modes, *draft.improvement_directions]:
            check_general_knowledge(text)
        citations = list(dict.fromkeys(draft.evidence_ids))
        code = [valid[eid] for eid in citations if valid[eid].evidence_type == "implementation"]
        tests = [valid[eid] for eid in citations if valid[eid].evidence_type in {"test", "evaluation"}]
        # Search hits never certify the broad capability. High requires future semantic/runtime verification.
        answerability = "medium" if code else "low"
        unsupported = list(dict.fromkeys(draft.unsupported_claims + [
            f"简历陈述仍需核实：{claim.source_quote}",
            "源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。",
        ]))
        if tests:
            unsupported.append("当前引用包含测试或评测材料，但静态源码不证明已经执行；正确性结果和性能提升仍未核验。")
        else:
            unsupported.append("当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。")
        if not code:
            unsupported.append("当前扫描未找到足够实现证据；不能把通用机制说成项目已经实现。")
        signals = [x for x in draft.signals if x in {"vague", "api_only", "no_implementation", "no_decision", "no_measurement", "failure_gap", "solid"}]
        if not code:
            signals.append("no_implementation")
        # All current evidence types are static source observations, including test/evaluation code.
        signals.append("no_measurement")
        signals = [signal for signal in signals if signal != "solid"]
        if not signals:
            signals = ["solid"]
        grounding = "当前项目材料可引用 " + "、".join(f"[{eid}]" for eid in citations) + "；源码原文另列。"
        if not citations:
            grounding = "当前仓库没有足够的相关证据，我不能声称这项能力已经在项目中实现。"
        direct = (draft.technical_explanation + "\n\n选型考虑：" + draft.technology_decision +
                  "\n\n项目边界：" + grounding +
                  "源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。")
        return Answer(question_id=question.id, direct_interview_answer=direct, evidence_selection=matches,
            evidence_ids=citations, technical_explanation=draft.technical_explanation,
            technology_decision=draft.technology_decision, failure_modes=draft.failure_modes,
            unsupported_claims=unsupported, likely_followups=draft.likely_followups,
            related_knowledge=draft.related_knowledge, improvement_directions=draft.improvement_directions,
            answerability=answerability, signals=list(dict.fromkeys(signals)), provenance="model" if self.client else "offline")
