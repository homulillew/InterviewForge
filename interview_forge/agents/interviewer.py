"""Interviewer receives a narrow view; repository evidence is never a dependency."""
from pydantic import Field
from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.quality import question_quality
from interview_forge.schemas.models import CapabilityClaim, Dimension, InterviewQuestion, Model


class SpokenTurn(Model):
    id: str
    question: str
    answer: str
    signals: list[str]
    subtopic: str


class InterviewerView(Model):
    claim: CapabilityClaim
    jd: str
    history: list[SpokenTurn]
    knowledge_titles: list[str]
    depth: int
    previous_topic_answer: SpokenTurn | None = Field(default=None)


class Interviewer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def ask(self, view: InterviewerView, question_id: str) -> InterviewQuestion:
        # Remove even evidence IDs and material scores before constructing a model context.
        payload = view.model_dump()
        payload["claim"] = view.claim.model_dump(exclude={"evidence_ids", "answerability", "risk_factors"})
        topic = TOPICS[topic_for(view.claim.topic)]
        used = {t.subtopic for t in view.history}
        last = view.history[-1] if view.history else view.previous_topic_answer
        initial = {
            Dimension.problem: "clarification", Dimension.mechanism: "mechanism",
            Dimension.decision: "decision", Dimension.engineering: "implementation",
            Dimension.tradeoff: "counterfactual", Dimension.failure: "failure",
            Dimension.evaluation: "evaluation", Dimension.scaling: "scaling",
            Dimension.ownership: "ownership",
        }
        candidates = [initial[view.claim.dimension]] if not view.history else []
        if view.history:
            routing = {"vague": "clarification", "api_only": "mechanism", "no_implementation": "implementation",
                       "no_decision": "decision", "no_measurement": "evaluation", "failure_gap": "failure"}
            candidates = [routing[s] for s in last.signals if s in routing]
        candidates += ["mechanism", "decision", "evaluation", "failure", "fundamentals", "scaling", "ownership", "debugging", "counterfactual"]
        subtopic = next((x for x in candidates if x not in used), "counterfactual")
        specs = {
            "mechanism": (topic.questions[0], Dimension.mechanism, 2),
            "decision": (topic.questions[2] if topic_for(view.claim.topic) == "rag" else topic.questions[1], Dimension.decision, 3),
            "evaluation": (topic.questions[1] if topic_for(view.claim.topic) == "rag" else topic.questions[2], Dimension.evaluation, 4),
            "failure": (topic.questions[3], Dimension.failure, 5),
            "fundamentals": (topic.questions[4], Dimension.mechanism, 8),
            "scaling": (topic.questions[5], Dimension.scaling, 7),
            "implementation": (f"关于{view.claim.topic}，如何把核心机制放入实际业务流程，并界定尚未验证的部分？", Dimension.engineering, 1),
            "clarification": (f"关于{view.claim.topic}，请用一个具体输入和状态变化解释你的方案为什么有效？", Dimension.problem, 1),
            "ownership": (f"对于{view.claim.topic}，你负责哪些决策，如何区分个人实现与团队已有能力？", Dimension.ownership, 0),
            "debugging": (f"对于{view.claim.topic}，线上指标突然恶化时如何通过观测缩小故障范围？", Dimension.failure, 6),
            "counterfactual": (f"如果禁止使用{view.claim.topic}中的核心组件，你会如何守住同样的业务不变量？", Dimension.tradeoff, 9),
        }
        text, dimension, level = specs[subtopic]
        if not view.history and view.previous_topic_answer:
            variations = {
                "decision": f"结合刚才的边界，如果业务更重视持久化一致性而不是吞吐，你会如何重新选择{view.claim.topic}的替代方案？",
                "failure": f"结合刚才的假设，如果操作只完成了一半，你如何定义{view.claim.topic}的恢复与补偿边界？",
                "evaluation": f"针对刚才提到的保证，你如何设计一个能推翻{view.claim.topic}有效性结论的反例实验？",
            }
            text = variations.get(subtopic, text)
        rationale = "首问验证简历能力主张"
        if last:
            rationale = f"上一答信号 {','.join(last.signals)}；继续验证 {subtopic}"
            anchor = last.answer.split("。", 1)[0].replace("\n", " ")
            if len(anchor) > 90:
                anchor = anchor[:90] + "…"
            text = f"上一答提到“{anchor}”；{text}"
        if self.client:
            payload.update({"question_id": question_id, "suggested_subtopic": subtopic})
            question = self.client.structured_generate(prompt("interviewer"), payload, InterviewQuestion)
            question.id = question_id
            question.claim_id = view.claim.id
            question.depth = view.depth
            question.based_on_turn = last.id if last else None
        else:
            question = InterviewQuestion(id=question_id, claim_id=view.claim.id, text=text, dimension=dimension,
                level=level, depth=view.depth, subtopic=subtopic, rationale=rationale,
                based_on_turn=last.id if last else None, expected_points=list(topic.rubric))
        ok, reason = question_quality(question.text)
        if not ok:
            raise ValueError(reason)
        if any(t.question == question.text for t in view.history):
            raise ValueError("Interviewer repeated the same question")
        return question
