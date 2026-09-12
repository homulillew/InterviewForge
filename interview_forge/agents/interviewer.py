"""Render a controller-owned plan from a repository-blind view."""

import re
from pydantic import Field
from interview_forge.llm import LLMClient, prompt
from interview_forge.quality import question_quality
from interview_forge.schemas.models import (
    Dimension,
    InterviewQuestion,
    Model,
    QuestionPlan,
    QuestionProvenance,
    AttackSurface,
    EffectiveStyle,
    ChallengeOperator as O,
)
from interview_forge.semantics import technologies, tokens
from interview_forge.corpus.dedup import normalized
from interview_forge.corpus.patterns import SPEC


def infer_dimension(text: str, default: Dimension = Dimension.mechanism) -> tuple[Dimension, str, int]:
    """Classify the requested reasoning, keeping the dimension/branch/level coherent."""
    # A previous answer is context; its keywords must not classify the new question.
    text = text.rsplit("”；", 1)[-1].casefold()
    for pattern, dimension, subtopic, level in (
        (
            r"排查|诊断|定位.{0,16}(?:瓶颈|根因|故障|问题|异常|热点)|(?:故障|瓶颈|根因).{0,8}定位|debug|troubleshoot",
            Dimension.failure,
            "debugging",
            6,
        ),
        (
            r"验证|评测|测量|衡量|指标|压测|实验|证明|测试|对照组|消融|benchmark|evaluat|measur|experiment|\btest|\bprove|\bvalidat|"
            r"(?:比较|对比|compare).{0,80}(?:recall|ndcg|precision|延迟|吞吐|latency|p99|p95)",
            Dimension.evaluation,
            "evaluation",
            4,
        ),
        (
            r"故障|失效|重试|超时|恢复|报错|出错|回滚|补偿|重复执行|响应丢失|失败|断连|断开|连接中断|failure|timeout|retry|recover|disconnect|connection.{0,12}(?:lost|closed)",
            Dimension.failure,
            "failure",
            5,
        ),
        (
            r"禁止使用|不能使用|without.{0,25}(?:redis|database|cache)|counterfactual",
            Dimension.tradeoff,
            "counterfactual",
            9,
        ),
        (
            r"替代|选型|不用|权衡|选择|取舍|trade.?off|alternative|\bchoos|\bchose|\bversus\b|\bvs\.?\b",
            Dimension.decision,
            "decision",
            3,
        ),
        (r"规模|扩容|扩展|流量.{0,8}(?:翻|倍|放大)|scale|scaling", Dimension.scaling, "scaling", 7),
        (r"负责|主导|个人贡献|ownership|responsib", Dimension.ownership, "ownership", 0),
        (r"实现|落地|设计|implement|\bdesign", Dimension.engineering, "implementation", 1),
        (
            r"原理|机制|原子性|状态变化|为什么|为何|是什么|解释|how.{0,40}work|\bwhy\b|\bexplain|mechanism",
            Dimension.mechanism,
            "mechanism",
            2,
        ),
    ):
        if re.search(pattern, text):
            return dimension, subtopic, level
    branch, level = {
        Dimension.problem: ("clarification", 1),
        Dimension.mechanism: ("mechanism", 2),
        Dimension.decision: ("decision", 3),
        Dimension.engineering: ("implementation", 1),
        Dimension.tradeoff: ("counterfactual", 9),
        Dimension.failure: ("failure", 5),
        Dimension.evaluation: ("evaluation", 4),
        Dimension.scaling: ("scaling", 7),
        Dimension.ownership: ("ownership", 0),
    }[default]
    return default, branch, level


class SpokenTurn(Model):
    id: str
    question: str
    answer: str
    subtopic: str


class InterviewerView(Model):
    claim: dict
    surface: AttackSurface
    plan: QuestionPlan
    style: EffectiveStyle
    history: list[SpokenTurn] = Field(default_factory=list)
    abstract_patterns: list[str] = Field(default_factory=list)
    depth: int = 0


class RenderedQuestion(Model):
    text: str = Field(min_length=10, max_length=1200)


def authored_question(view):
    p = view.plan
    target = p.target_concept
    prompts = {
        O.WHY_NECESSARY: f"{target}具体解决了哪个原始瓶颈，为什么这个瓶颈需要引入当前方案？",
        O.WHY_NOT_SIMPLER: f"如果直接采用{p.alternative}，为什么在某个关键约束下无法达到{target}方案的效果？",
        O.WHY_NOT_ALTERNATIVE: f"在相同业务约束下，{target}与{p.alternative}相比，如何判断决定选型的关键代价？",
        O.MECHANISM_PRESSURE: f"请解释{target}从请求输入到状态变化的因果链，哪个步骤产生了你声称的效果？",
        O.IMPLEMENTATION_PRESSURE: f"请沿一次具体请求解释{target}的实现过程，包括关键状态变化与异常分支？",
        O.OWNERSHIP_PRESSURE: f"在{target}方案中，你独立作出的关键决策是什么，如何区分个人贡献与团队已有能力？",
        O.METRIC_PRESSURE: f"如何定义和测量{target}方案的效果，使这个结论能够被复现实验检验？",
        O.BASELINE_PRESSURE: f"验证{target}效果时，如何设置公平对照并排除资源、数据和负载变化的影响？",
        O.FAILURE_PRESSURE: f"假设{target}的一次操作完成后响应丢失，重试时如何恢复并避免重复状态变化？",
        O.BOUNDARY_PRESSURE: f"{target}声称的保证在哪个前提失效后不再成立，为什么？",
        O.SCALE_PRESSURE: f"假设固定资源下请求量持续增长，如何判断{target}最先遇到的瓶颈？",
        O.DEBUG_PRESSURE: f"假设{target}的线上表现突然恶化，如何用一次受控验证区分最可能的两个原因？",
        O.COUNTEREXAMPLE: f"如何构造一个能推翻{target}当前结论的具体反例？",
        O.CONSISTENCY_PRESSURE: f"如何检验{target}关于状态变化和结果保证的说法是否在同一个故障场景下自洽？",
        O.FUNDAMENTAL_DRILL: f"{target}依赖的核心基础概念是什么，如何用最小例子解释它与当前方案的关系？",
    }
    anchor = view.claim["proposition"].rstrip("。；")
    prefix = f"简历中提到“{anchor}”。"
    if p.previous_answer_trigger and view.history:
        trigger = view.history[-1].answer.split("。")[0][:85].replace("？", "").replace("?", "")
        prefix += f"上一答提到“{trigger}”。"
    return prefix + prompts[p.operator]


def guard_question(text, view, corpus_questions=()):
    ok, reason = question_quality(text)
    if not ok:
        return reason
    if len(re.findall(r"[？?]", text)) > 1 or re.search(r"(?:\n|；)\s*(?:[2-9][.、]|第二|第三)", text):
        return "Ask one primary question"
    allowed = set(
        technologies(
            view.claim["source_quote"] + " " + view.plan.target_concept + " " + (view.plan.alternative or "")
        )
    )
    if set(technologies(text)) - allowed:
        return "Question introduced an unrelated technology"
    if not tokens(text) & tokens(view.claim["proposition"] + " " + view.plan.target_concept):
        return "Question lost its resume anchor"
    for number in re.findall(r"\d+(?:\.\d+)?%?", text):
        if number not in view.claim["source_quote"] and not re.search(r"假设|如果|例如|设定", text):
            return "Question invented a measured premise"
    if re.search(r"你的|你们|已经|上线后|线上发生过", text) and not re.search(r"假设|如果", text):
        for premise in ("集群", "分片", "主从", "上线", "负责", "部署", "跨机房"):
            if premise in text and premise not in view.claim["source_quote"]:
                return "Question invented an architectural or ownership premise"
    focus = text.rsplit("”。", 1)[-1]
    operator_terms = {
        O.WHY_NECESSARY: r"必要|需要|瓶颈|为什么|为何|why",
        O.WHY_NOT_SIMPLER: r"直接|简单|simpler",
        O.WHY_NOT_ALTERNATIVE: r"替代|相比|选型|不用|alternative|compare",
        O.MECHANISM_PRESSURE: r"机制|原理|因果|原子|状态变化|mechanism|causal",
        O.IMPLEMENTATION_PRESSURE: r"实现|流程|步骤|请求|implement",
        O.OWNERSHIP_PRESSURE: r"负责|贡献|独立|个人|ownership",
        O.METRIC_PRESSURE: r"测量|指标|评测|实验|衡量|证明|metric|measure",
        O.BASELINE_PRESSURE: r"基线|对照|归因|控制|baseline",
        O.FAILURE_PRESSURE: r"故障|失败|超时|丢失|重试|failure|timeout",
        O.BOUNDARY_PRESSURE: r"边界|前提|保证|失效|boundary",
        O.SCALE_PRESSURE: r"资源|规模|增长|容量|scale|load",
        O.DEBUG_PRESSURE: r"排查|定位|原因|验证区分|诊断|debug",
        O.COUNTEREXAMPLE: r"反例|推翻|counterexample|falsif",
        O.CONSISTENCY_PRESSURE: r"矛盾|自洽|一致|冲突|consisten",
        O.FUNDAMENTAL_DRILL: r"基础|概念|定义|fundamental|concept",
    }
    if not re.search(operator_terms[view.plan.operator], focus, re.I):
        return "Question does not implement the planned challenge operator"
    key = normalized(text)
    for source in corpus_questions:
        source = normalized(source)
        if len(source) >= 24 and any(source[i : i + 24] in key for i in range(len(source) - 23)):
            return "Question copied corpus wording"
    for previous in view.history:
        if normalized(previous.question) == key:
            return "Question repeated history"
        left, right = tokens(text), tokens(previous.question)
        if len(left & right) / max(1, len(left | right)) > 0.90:
            return "Question nearly repeated history"
    return None


class Interviewer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def ask(
        self,
        view: InterviewerView,
        question_id: str,
        provenance: QuestionProvenance,
        corpus_questions=(),
        previous_questions=(),
    ) -> InterviewQuestion:
        text = authored_question(view)
        if self.client:
            # Renderer sees abstractions only; IDs and corpus raw text stay in the controller.
            payload = {
                "claim": view.claim,
                "surface": {"dimension": view.surface.dimension.value},
                "plan": view.plan.model_dump(
                    exclude={"corpus_match_ids", "pattern_ids", "transition_ids", "style_profile_id"}
                ),
                "style": view.style.model_dump(exclude={"id", "profile_weights", "backoff_path"}),
                "abstract_patterns": view.abstract_patterns,
                "history": [t.model_dump() for t in view.history],
            }
            for attempt in range(2):
                text = self.client.structured_generate(prompt("interviewer"), payload, RenderedQuestion).text
                problem = guard_question(text, view, corpus_questions)
                if not problem:
                    break
                payload["rewrite_requirement"] = problem
            else:
                raise ValueError("Question renderer failed guards: " + problem)
        problem = guard_question(text, view, corpus_questions)
        if any(
            normalized(text.rsplit("”。", 1)[-1]) == normalized(q.rsplit("”。", 1)[-1])
            for q in previous_questions
        ):
            problem = "Question repeated an already tested project probe"
        if problem:
            raise ValueError(problem)
        intent, _, _ = SPEC[view.plan.operator]
        branch = {"boundary": "counterfactual", "implementation": "implementation"}.get(
            intent.value, intent.value
        )
        return InterviewQuestion(
            id=question_id,
            claim_id=view.plan.claim_id,
            text=text,
            dimension=view.surface.dimension,
            level={
                "ownership": 0,
                "implementation": 1,
                "problem": 1,
                "mechanism": 2,
                "decision": 3,
                "evaluation": 4,
                "failure": 5,
                "debugging": 6,
                "scaling": 7,
                "fundamentals": 8,
                "boundary": 9,
            }[intent.value],
            depth=min(9, view.depth),
            subtopic=branch,
            rationale=view.plan.adaptation_reason,
            based_on_turn=view.history[-1].id if view.history else None,
            expected_points=view.plan.expected_points,
            plan=view.plan,
            provenance=provenance,
        )
