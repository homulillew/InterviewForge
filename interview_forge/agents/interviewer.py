"""Interviewer receives a narrow view; repository evidence is never a dependency."""
import re

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


class QuestionSeed(Model):
    id: str
    question: str
    followups: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    company: str = ""
    role: str = ""


def infer_dimension(text: str, default: Dimension = Dimension.mechanism) -> tuple[Dimension, str, int]:
    """Classify the requested reasoning, keeping the dimension/branch/level coherent."""
    # A previous answer is context; its keywords must not classify the new question.
    text = text.rsplit("”；", 1)[-1].casefold()
    for pattern, dimension, subtopic, level in (
        (r"排查|诊断|定位.{0,16}(?:瓶颈|根因|故障|问题|异常|热点)|(?:故障|瓶颈|根因).{0,8}定位|debug|troubleshoot",
         Dimension.failure, "debugging", 6),
        (r"验证|评测|测量|衡量|指标|压测|实验|证明|测试|对照组|消融|benchmark|evaluat|measur|experiment|\btest|\bprove|\bvalidat|"
         r"(?:比较|对比|compare).{0,80}(?:recall|ndcg|precision|延迟|吞吐|latency|p99|p95)",
         Dimension.evaluation, "evaluation", 4),
        (r"故障|失效|重试|超时|恢复|报错|出错|回滚|补偿|重复执行|响应丢失|失败|断连|断开|连接中断|failure|timeout|retry|recover|disconnect|connection.{0,12}(?:lost|closed)",
         Dimension.failure, "failure", 5),
        (r"禁止使用|不能使用|without.{0,25}(?:redis|database|cache)|counterfactual", Dimension.tradeoff, "counterfactual", 9),
        (r"替代|选型|不用|权衡|选择|取舍|trade.?off|alternative|\bchoos|\bchose|\bversus\b|\bvs\.?\b",
         Dimension.decision, "decision", 3),
        (r"规模|扩容|扩展|流量.{0,8}(?:翻|倍|放大)|scale|scaling", Dimension.scaling, "scaling", 7),
        (r"负责|主导|个人贡献|ownership|responsib", Dimension.ownership, "ownership", 0),
        (r"实现|落地|设计|implement|\bdesign", Dimension.engineering, "implementation", 1),
        (r"原理|机制|原子性|状态变化|为什么|为何|是什么|解释|how.{0,40}work|\bwhy\b|\bexplain|mechanism",
         Dimension.mechanism, "mechanism", 2),
    ):
        if re.search(pattern, text):
            return dimension, subtopic, level
    branch, level = {
        Dimension.problem: ("clarification", 1), Dimension.mechanism: ("mechanism", 2),
        Dimension.decision: ("decision", 3), Dimension.engineering: ("implementation", 1),
        Dimension.tradeoff: ("counterfactual", 9), Dimension.failure: ("failure", 5),
        Dimension.evaluation: ("evaluation", 4), Dimension.scaling: ("scaling", 7),
        Dimension.ownership: ("ownership", 0),
    }[default]
    return default, branch, level


def _question_key(text: str) -> str:
    """Ignore OCR punctuation/spacing differences when checking previously used seeds."""
    return re.sub(r"\W+", "", text.casefold())


class InterviewerView(Model):
    claim: CapabilityClaim
    jd: str
    history: list[SpokenTurn]
    knowledge_titles: list[str]
    depth: int
    previous_topic_answer: SpokenTurn | None = Field(default=None)
    experience_questions: list[QuestionSeed] = Field(default_factory=list)
    used_material_questions: list[str] = Field(default_factory=list)


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
            "implementation": (f"关于{view.claim.topic}，如何把核心机制放入实际业务流程，并说明请求在各组件之间如何流转？", Dimension.engineering, 1),
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
        source_id, source_question = None, None
        seed_candidates = []
        used_questions = {_question_key(question) for question in view.used_material_questions}
        for rank, seed in enumerate(view.experience_questions):
            for index, candidate in enumerate([seed.question, *seed.followups]):
                if _question_key(candidate) in used_questions or not question_quality(candidate)[0]:
                    continue
                kind, branch, candidate_level = infer_dimension(candidate, dimension)
                priority = (3 if kind == dimension else 0) + (2 if bool(index) == bool(last) else 0) - rank * 0.1
                seed_candidates.append((priority, seed.id, candidate, kind, branch, candidate_level))
        if seed_candidates and not self.client:
            _, source_id, source_question, dimension, subtopic, level = max(seed_candidates, key=lambda row: row[0])
            text = f"结合{view.claim.project}，{source_question}"
        rationale = "首问验证简历能力主张"
        if last:
            rationale = f"上一答信号 {','.join(last.signals)}；继续验证 {subtopic}"
            anchor = last.answer.split("。", 1)[0].replace("\n", " ")
            if len(anchor) > 90:
                anchor = anchor[:90] + "…"
            text = f"上一答提到“{anchor}”；{text}"
        if source_id:
            rationale += f"；面经来源 {source_id}"
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
                based_on_turn=last.id if last else None, expected_points=list(topic.rubric),
                material_ids=[source_id] if source_id else [], material_question=source_question)
        seeds = {seed.id: seed for seed in view.experience_questions}
        if not set(question.material_ids) <= seeds.keys():
            raise ValueError("Interviewer cited an unknown experience item")
        if question.material_ids and question.material_question is None:
            seed = seeds[question.material_ids[0]]
            question.material_question = seed.question or next(iter(seed.followups), "")
        if question.material_question is not None and not any(question.material_question in
                [seeds[mid].question, *seeds[mid].followups] for mid in question.material_ids):
            raise ValueError("Interviewer source question is not present in cited experience")
        if question.material_question is not None and _question_key(question.material_question) in used_questions:
            raise ValueError("Interviewer repeated an experience question already covered")
        if self.client and question.material_question is not None:
            question.dimension, question.subtopic, question.level = infer_dimension(question.text, question.dimension)
        ok, reason = question_quality(question.text)
        if not ok:
            raise ValueError(reason)
        if any(t.question == question.text for t in view.history):
            raise ValueError("Interviewer repeated the same question")
        return question
