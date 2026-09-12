"""Candidate answers and their audit trail are deliberately separate outputs."""

from __future__ import annotations
from interview_forge.schemas.models import MaterialGap

import ast
from dataclasses import dataclass
import re

from pydantic import Field

from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.quality import check_general_knowledge
from interview_forge.repository.retrieval import select_evidence
from interview_forge.schemas.models import (
    Answer,
    CapabilityClaim,
    Dimension,
    InterviewQuestion,
    Model,
    RepoEvidence,
)


class AnswerDraft(Model):
    evidence_ids: list[str] = Field(default_factory=list)
    reference_material_ids: list[str] = Field(default_factory=list)
    direct_interview_answer: str = Field(default="", max_length=12000)
    technical_explanation: str = Field(min_length=1, max_length=5000)
    technology_decision: str = Field(min_length=1, max_length=3000)
    failure_modes: list[str]
    unsupported_claims: list[str]
    likely_followups: list[str]
    related_knowledge: list[str]
    improvement_directions: list[str]
    reasoning_basis: list[str] = Field(default_factory=list)
    inferred_details: list[str] = Field(default_factory=list)
    experiment_plan: list[str] = Field(default_factory=list)
    signals: list[str]


@dataclass(frozen=True)
class AnswerBlueprint:
    mechanism: str
    decision: str
    application: str
    failure: str
    experiments: tuple[str, ...]
    scaling: str
    prerequisite: str


BLUEPRINTS = {
    "redis": AnswerBlueprint(
        "核心是把读库存、判断库存和扣减放进同一个 Redis Lua 脚本，让其他请求无法插入这段读写过程。"
        "我关注的是两个业务不变量：库存不能变成负数，同一个业务请求只能扣减一次。",
        "我的选型顺序是先看事务边界，再看热点竞争。如果订单和库存都能在同一个数据库事务里完成，"
        "条件 UPDATE 就很直接；热点库存需要快速拒绝无库存请求时，我会用 Redis 承接入口，订单落库和对账分别处理。",
        "实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；"
        "重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。",
        "最容易出问题的是扣减成功后客户端超时，随后重试又扣一次。我会让重试复用原来的 request_id，"
        "幂等记录的保留期覆盖重试窗口。订单写入失败则进入可重试的补偿和对账流程；Lua 的原子执行不提供数据库事务回滚。",
        (
            "我会先设初始库存为 100，用 1,000 个不同请求并发争抢，检查成功扣减总数等于 100、库存非负，"
            "并把每个成功结果和订单逐条对账。",
            "接着对同一个 request_id 重放请求，在扣减后断开客户端连接，并注入订单写入失败，验证不会重复扣减，"
            "补偿任务多次执行也只产生一次效果。",
            "性能实验把数据库条件更新作为基线，固定机器、连接池和请求分布，逐档增加并发，"
            "同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间，观察瓶颈出现在哪一档。",
        ),
        "流量放大后，我会先区分连接池排队和单个热 key 饱和。入口做排队与限流，缩短 Lua 执行时间；"
        "单个库存桶成为瓶颈时再考虑分桶预分配，配套总量校验和余量回收，避免把跨桶一致性成本带进每次请求。",
        "两个请求都读到库存为 1，各自判断可以扣减，再分别写回，就可能都返回成功。"
        "我的处理是让同步边界覆盖完整的读、检查、写；Lua 保证执行期间不被插入，幂等键负责处理重复请求。",
    ),
    "rag": AnswerBlueprint(
        "我把检索拆成候选召回和精排两层：第一层用较低成本把相关文档找全，第二层对 query 和候选逐对打分，"
        "把真正能回答问题的段落排到前面。两层要分别诊断，因为候选里漏掉的文档，重排阶段补不回来。",
        "我先抽样看错误落在哪一层：漏召回优先调整 chunk、检索方式和召回数量；候选里有答案但排名靠后，"
        "才引入 reranker。候选数由召回收益、重排耗时和上下文预算共同决定，我会选择质量与延迟曲线的拐点。",
        "落地时我会给每个 chunk 保留文档 ID、段落位置和版本，先召回候选，再去重、重排，"
        "按上下文预算选段并附上来源。评测日志同时保留召回前排名、重排后排名和最终入选段落，方便定位哪一层丢失了答案。",
        "我重点处理三类失败：分块把关键上下文切断，召回漏掉答案，以及高分段落彼此重复。"
        "分别通过相邻段补全、混合检索和按文档去重处理；重排服务超时时，设置耗时上限并降级到第一阶段排序。",
        (
            "我会建立按时间或文档来源隔离的查询集，标注相关段落，并把简单查询、多条件查询和无答案查询分开统计。",
            "对照组保持 embedding、chunk 和生成模型一致，只切换是否重排；候选 top_k 分别取 20、50、100 做消融，"
            "记录 Recall@K、MRR、NDCG@K、P99 和单次请求成本。",
            "然后逐条分析召回遗漏、排序错误和生成错误，检查无答案场景的拒答质量；"
            "同一查询保留各组结果，避免文档泄漏到测试集或把生成风格变化误判为检索质量提升。",
        ),
        "扩容时我会把向量召回和重排拆开监控，按候选 token 数估算重排负载。"
        "文档向量离线计算，热门查询可以缓存，重排采用批处理和有界队列；"
        "高峰时降低候选数或跳过低收益重排，同时观察不同查询类型的质量变化。",
        "Recall@K 看相关文档有没有进入候选，MRR 看第一个相关结果排在第几位，NDCG 看多个结果的相关等级和位置。"
        "我会先用 Recall@K 判断召回上限，再用 MRR、NDCG 分析重排，最后结合答案正确率验证端到端收益。",
    ),
    "service": AnswerBlueprint(
        "我会先把一次请求拆成接入、业务处理和持久化三段，为每段定义超时和错误返回。"
        "关键点是超时只代表调用方没有拿到结果，服务端可能已经完成操作，所以写请求的重试必须配合业务幂等。",
        "我的决策依据是业务不变量、响应时限和依赖的稳定性。能够在单个数据库事务里完成的写入优先用事务；"
        "耗时长、允许稍后完成的工作再拆成异步任务，并为任务状态和重复执行设计约束。",
        "实现上我会给写请求分配业务唯一键，把去重检查和业务写入放在同一个事务内，"
        "利用唯一约束处理并发重复提交。请求链路传递 deadline，重试设置次数上限、退避和抖动，任务状态单独持久化。",
        "我重点防止慢依赖把线程和连接池拖满：每个依赖设置超时、并发上限和隔离，"
        "只对可恢复错误进行有限重试。跨资源部分成功通过任务状态、补偿和对账恢复，"
        "并用 trace_id 串起入口耗时、依赖耗时和最终提交结果。",
        (
            "我会先覆盖正常提交、重复提交、提交后连接断开和依赖部分失败，逐条检查业务只生效一次，"
            "终态可查询，失败任务可以恢复。",
            "压测固定资源配额和数据集，以阶梯到达率持续加压，分别记录入口排队、连接池等待、"
            "依赖耗时、成功吞吐、错误率和 P99，定位最先饱和的资源。",
            "再把依赖延迟提高到超时阈值附近，对比开启和关闭有限重试、隔离的效果，"
            "观察恢复时间和额外请求放大量，并检查故障期间的数据一致性。",
        ),
        "扩容前我会先看 CPU、连接池、数据库锁等待和外部依赖配额，区分计算饱和与资源等待。"
        "无状态请求可以水平扩展；写热点通过索引、批处理或队列削峰处理；"
        "异步化后持续观测积压时长，并给消费速率和失败重试设置上限。",
        "幂等是重复执行仍得到同一个业务效果。我的处理是给操作一个稳定的业务键，"
        "通过数据库唯一约束把并发请求收敛到同一条记录，再返回已保存的处理结果；仅在入口查一次缓存会留下并发竞争窗口。",
    ),
}

# The patterns identify audit boilerplate, not useful engineering limits such as Lua rollback.
AUDIT_BOILERPLATE = re.compile(
    r"当前仓库|证据不足|未核实|无法确认|不能声称|尚未验证|改进方向[（(]未证明|源码观察|项目边界|"
    r"缺乏.{0,8}证据|没有足够.{0,8}证据|不能独立证明|静态源码不证明|仓库.{0,10}没有.{0,6}实现|"
    r"not (?:verified|implemented) in (?:the|this) repo|insufficient evidence",
    re.I,
)
NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|ms|s|秒|毫秒|qps|tps|万|亿)?", re.I)
RESULT = re.compile(
    r"实测|测得|压测结果|上线后|提升了|降低了|达到了|优化到|减少了|"
    r"(?:我|我们).{0,12}(?:降到|提升到|做到|跑到)|"
    r"\b(?:achieved|measured|improved|reduced|decreased|increased)\b",
    re.I,
)
PROSPECTIVE = re.compile(
    r"我会|计划|拟|目标|预期|假设|如果|实验输入|实验参数|测试参数|例如|比如|\b(?:would|plan|target|hypothetical)\b",
    re.I,
)
OWNERSHIP = re.compile(
    r"(?:我|我们).{0,4}(?:独立完成|主导上线|主导开发|负责上线|已经部署|已经上线)|"
    r"\bI (?:independently built|led the deployment|deployed to production)\b",
    re.I,
)


def _strip_audit_boilerplate(text: str) -> str:
    if not AUDIT_BOILERPLATE.search(text):
        return text.strip()
    parts = re.split(r"(?<=[。！？.!?])|\n+", text)
    return "\n".join(part.strip() for part in parts if part.strip() and not AUDIT_BOILERPLATE.search(part))


def _check_candidate_assertions(text: str, claim: CapabilityClaim) -> None:
    """Catch unsupported result/ownership stories; design parameters are welcome."""
    resume_numbers = {match.group().replace(" ", "").lower() for match in NUMBER.finditer(claim.source_quote)}
    for sentence in re.split(r"[。！？\n]", text):
        if RESULT.search(sentence) and not PROSPECTIVE.search(sentence):
            claimed_numbers = {match.group().replace(" ", "").lower() for match in NUMBER.finditer(sentence)}
            if claimed_numbers - resume_numbers:
                raise ValueError(
                    "Invented measured result in candidate answer; use experiment parameters instead"
                )
        ownership = OWNERSHIP.search(sentence)
        if ownership and ownership.group() not in claim.source_quote and not PROSPECTIVE.search(sentence):
            raise ValueError("Invented completed ownership in candidate answer")


def _current_question(question: InterviewQuestion) -> str:
    return (
        re.sub(r"^(?:上一答|你刚才).*?[”\"]\s*[；;，,]", "", question.text)
        .split("”；", 1)[-1]
        .rsplit("”。", 1)[-1]
    )


def _diagnostic_answer(question: InterviewQuestion, key: str) -> list[str]:
    text = _current_question(question)
    if re.search(
        r"(?:吞吐|QPS).*(?:不再增长|不增长|平台|停滞|下降)|P99.*(?:变高|升高|增长|飙升)|定位瓶颈", text, re.I
    ):
        component = {
            "redis": "Redis 侧看 CPU、SLOWLOG 和脚本耗时：单线程已满或 Lua 耗时增加，重点检查热 key 与长脚本；"
            "服务端耗时稳定而客户端等待变长，则转查连接池容量、网络往返和入口排队。",
            "rag": "检索侧把向量召回和重排分别计时，观察候选数、输入 token 数、批处理等待和设备利用率；"
            "重排排队增长时，先检查候选量和服务容量，再判断是否需要减少候选或扩容。",
            "service": "应用侧看 CPU、线程池与连接池等待，数据库侧看慢查询、锁等待和活跃连接；"
            "CPU 空闲而等待上升通常说明请求卡在依赖或资源队列，需要沿调用链继续定位。",
        }[key]
        return [
            "吞吐已经进入平台期，而 P99 继续升高，我首先怀疑请求在某个饱和资源前排队。"
            "先把端到端耗时拆成入口排队、连接池等待、服务端执行和下游调用四段，找出随并发一起增长的那一段。",
            component
            + ("同时检查订单数据库的锁等待和写入耗时。" if key == "redis" else "")
            + "另外检查压测机自身的 CPU、连接数和网络，排除发压端先饱和。",
            "复验时固定机器和数据分布，逐档提高到达率，每档保留吞吐、P99、队列长度、拒绝率和资源利用率。"
            "每轮只改一个变量，例如缩短脚本、调整连接池或降低热点集中度；看瓶颈位置是否移动，"
            "再决定优化还是扩容。资源已饱和时先限制并发和排队长度，防止超时与重试继续放大负载。",
        ]
    if re.search(r"(?:数据库|事务).*(?:提交|成功).*(?:断|超时|丢失)|提交.*(?:连接断|响应丢失)", text):
        return [
            "数据库已经提交时，连接断开只影响结果送达。我会用原业务唯一键查询持久化的处理状态和结果，"
            "完成态直接返回原结果，处理中返回可查询的任务状态；客户端继续沿用这个键，避免发起第二次业务操作。",
            "实现上，业务写入与最终结果记录放在同一个事务里，用唯一约束处理并发重放。"
            "如果还涉及消息发送，则记录待投递事件并重试投递，消费端按事件 ID 去重；"
            "恢复任务只推进缺失的状态，不重新执行已经提交的扣减。",
            "验证时在提交成功到写回响应之间断开连接，随后并发重试同一个业务键，"
            "检查每次返回都对应同一条结果、业务只生效一次，再覆盖恢复进程重启和重复投递。",
        ]
    return []


def _question_focus(question: InterviewQuestion, key: str) -> str:
    # Follow-up questions may quote the preceding answer; match the new question itself.
    text = _current_question(question)
    rules = {
        "redis": [
            (
                r"补偿|多加库存",
                "补偿本身也要幂等。我用原订单 ID 和补偿类型标识一次归还操作，"
                "只有状态从已扣减成功迁移到已补偿时才增加库存。状态检查、归还库存和保存补偿结果放在同一原子边界内；"
                "重复任务直接返回已补偿结果，不能每收到一条消息就再加一次库存。",
            ),
            (
                r"回滚|脚本.*(?:报错|错误)|rollback",
                "Lua 脚本的原子执行解决的是并发插入问题。"
                "脚本执行到一半报错，已经完成的写入仍然保留，所以我会把参数、key 类型和业务条件检查放在写操作之前，"
                "缩短写入路径，并用幂等记录与补偿任务处理跨资源失败。",
            ),
            (
                r"hash.?tag|槽位|cluster|集群.*key",
                "多 key 脚本要先把 key 放进同一个 Redis Cluster 槽位。"
                "我会让库存 key 和幂等 key 使用同一个业务 hash tag，把脚本涉及的 key 显式传入 KEYS；"
                "跨槽的数据改用分步状态迁移和补偿，避免让单次扣减依赖跨分片协调。",
            ),
            (
                r"超时|重试|幂等|request_id",
                "超时后我首先按原 request_id 查询或重试，复用第一次处理结果。"
                "因为客户端超时可能发生在扣减之后，把重试当成新请求会重复扣库存；"
                "去重检查、扣减和保存结果需要放在同一个执行边界内。",
            ),
        ],
        "rag": [
            (
                r"数据泄漏|切分|泄露|leakage",
                "评测切分我会按文档来源和时间隔离，再对近重复段落去重，"
                "同一文档的不同 chunk 放进同一个集合。调参只用验证集，测试集在配置冻结后使用，"
                "同时检查参考答案有没有进入索引，防止测到的是答案泄漏。",
            ),
            (
                r"chunk|分块|切块",
                "分块我会先保留标题层级和段落边界，让每块能独立表达一个事实或步骤。"
                "长段落再按 token 预算切分，重叠区域用于衔接上下文；"
                "评测同时观察块级召回和最终答案质量，避免召回很多碎片却拼不出完整答案。",
            ),
            (
                r"cross.encoder|bi.encoder|联合编码",
                "bi-encoder 分别编码 query 和文档，文档向量可以离线计算，"
                "适合大规模召回；cross-encoder 把 query 和文档放在一起编码，交互更充分，计算也更贵。"
                "我的处理是把较贵的逐对打分限制在小候选集内，用质量增益和延迟预算决定是否采用。",
            ),
        ],
        "service": [
            (
                r"幂等|重复|重试|idempot",
                "我会让一次业务操作始终使用同一个唯一键，并把唯一约束和业务写入放进同一事务。"
                "并发重复请求由数据库约束收敛到同一结果，重试复用这个键；"
                "如果只先查缓存再写数据库，两个请求仍可能同时通过检查。",
            ),
            (
                r"熔断|circuit",
                "熔断器我会按依赖和错误类型分别统计，持续失败时快速返回降级结果，"
                "经过冷却窗口后放少量半开探测请求。它需要配合超时和并发隔离："
                "超时控制单次等待，隔离控制被占用的资源，熔断减少持续访问失败依赖。",
            ),
        ],
    }
    for pattern, explanation in rules[key]:
        if re.search(pattern, text, re.I):
            return explanation
    return ""


def _implementation_anchor(selected: list[RepoEvidence]) -> str:
    # AST parsing reads structure without executing code or repeating source comments.
    for evidence in selected:
        if evidence.evidence_type != "implementation" or not evidence.file_path.endswith(".py"):
            continue
        try:
            tree = ast.parse(evidence.excerpt)
        except (SyntaxError, ValueError, RecursionError):
            continue
        names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,48}", node.name)
            and not node.name.startswith("test_")
        ]
        if names:
            return f"讲实现时，我会从 {names[0]} 这个函数展开，把输入校验、核心处理和失败后的状态分别说明。"
    return ""


def _experiment_speech(experiments: list[str]) -> str:
    return "实验上，我会这样安排：" + "".join(experiments) if experiments else ""


def _offline_draft(
    question: InterviewQuestion, claim: CapabilityClaim, selected: list[RepoEvidence]
) -> AnswerDraft:
    key = topic_for(claim.topic)
    topic, blueprint = TOPICS[key], BLUEPRINTS[key]
    explanation = blueprint.mechanism
    if topic.prerequisite in question.subtopic or question.subtopic == "fundamentals":
        explanation = blueprint.prerequisite
    if question.dimension == Dimension.failure:
        lead = blueprint.failure
    elif question.dimension in {Dimension.decision, Dimension.tradeoff}:
        lead = blueprint.decision
    elif question.dimension == Dimension.evaluation or "评测" in question.subtopic:
        lead = "我会把实验拆成正确性验证、对照实验和故障测试三部分，先固定输入与资源，再比较结果。"
    elif question.dimension == Dimension.scaling:
        lead = blueprint.scaling
    elif question.dimension == Dimension.ownership:
        lead = "我会按需求约束、关键实现、验证和故障定位来讲这项工作，重点解释每个决策解决了什么问题。"
    else:
        lead = explanation
    focus = _question_focus(question, key)
    if focus and question.dimension not in {Dimension.evaluation, Dimension.scaling}:
        lead = focus
    experiments = list(blueprint.experiments)
    application = blueprint.application
    diagnostic = _diagnostic_answer(question, key)
    if diagnostic:
        paragraphs = diagnostic
        explanation = diagnostic[0]
        experiments = [diagnostic[-1]]
    elif question.dimension == Dimension.failure:
        recovery = {
            "redis": "恢复时我会按业务键核对幂等结果、库存变化和订单状态：结果已保存就复用，"
            "订单缺失则推进补偿，状态不一致则进入对账。每一步都记录状态迁移，重复执行仍得到相同结果。",
            "rag": "定位时按同一个 query 查看召回候选、重排分数和最终上下文，确定答案在哪一步丢失。"
            "分别调整召回、排序或上下文拼接，并保留超时降级路径，避免改动无关阶段。",
            "service": "恢复时我会先查询业务唯一键对应的持久化状态，区分未开始、处理中、已完成和待补偿。"
            "已完成直接返回原结果，待补偿只执行缺失的状态迁移，并限制重试次数与并发。",
        }[key]
        failure_pattern = r"超时|重试|断连|断开|失败|故障|丢失|过期|重放|补偿|重复|回滚|错误|无答案"
        failure_plans = [plan for plan in experiments if re.search(failure_pattern, plan)]
        if not failure_plans:
            failure_plans = [plan for plan in blueprint.experiments if re.search(failure_pattern, plan)]
        validation = _experiment_speech(failure_plans[:2])
        paragraphs = [lead, recovery, validation]
    elif question.dimension in {Dimension.decision, Dimension.tradeoff}:
        paragraphs = [blueprint.decision, explanation, experiments[-1]]
    elif question.dimension == Dimension.evaluation or "评测" in question.subtopic:
        paragraphs = [lead, *experiments]
    elif question.dimension == Dimension.scaling:
        paragraphs = [lead, application, experiments[-1]]
    elif question.dimension in {Dimension.engineering, Dimension.ownership}:
        paragraphs = [lead, application, blueprint.failure]
    else:
        paragraphs = [lead, application]
    anchor = _implementation_anchor(selected)
    if anchor and question.dimension in {Dimension.engineering, Dimension.ownership}:
        paragraphs.insert(1, anchor)
    direct = "\n\n".join(dict.fromkeys(paragraphs))
    return AnswerDraft(
        evidence_ids=[item.id for item in selected[:3]],
        reference_material_ids=[],
        direct_interview_answer=direct,
        technical_explanation=explanation,
        technology_decision=blueprint.decision,
        failure_modes=[blueprint.failure],
        unsupported_claims=[],
        likely_followups=list(topic.questions[1:]),
        related_knowledge=[topic.title, topic.prerequisite],
        improvement_directions=[blueprint.scaling],
        inferred_details=[blueprint.application],
        experiment_plan=experiments,
        signals=["solid"],
    )


def _spoken_signals(draft: AnswerDraft, direct: str) -> list[str]:
    allowed = {
        "vague",
        "api_only",
        "no_implementation",
        "no_decision",
        "no_measurement",
        "failure_gap",
        "solid",
    }
    signals = [signal for signal in draft.signals if signal in allowed and signal != "solid"]
    coverage = {
        "no_implementation": bool(
            re.search(r"脚本|事务|唯一约束|chunk|去重|幂等|hash tag|request_id", direct, re.I)
        ),
        "no_decision": bool(re.search(r"选型|优先|对比|权衡|决策|而不是|选择|相比|取舍", direct)),
        "no_measurement": bool(
            re.search(r"验证|实验|测试|压测|评测|对照", direct)
            and re.search(r"P99|NDCG|MRR|Recall|吞吐|成功率|成功.*总数|对账|错误率", direct, re.I)
        ),
        "failure_gap": bool(re.search(r"失败|超时|故障|补偿|降级|重试|漏召回", direct)),
    }
    signals = [signal for signal in signals if not coverage.get(signal, False)]
    return list(dict.fromkeys(signals)) or ["solid"]


class RepositoryAnswerer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def answer(
        self,
        question: InterviewQuestion,
        claim: CapabilityClaim,
        evidences: list[RepoEvidence],
    ) -> Answer:
        selected, matches = select_evidence(question, claim, evidences)
        if self.client:
            draft = self.client.structured_generate(
                prompt("repo_answerer"),
                {
                    "question": {"id": question.id, "text": question.text},
                    "claim": claim.model_dump(
                        include={
                            "id",
                            "statement_id",
                            "proposition",
                            "source_quote",
                            "project",
                            "claim_type",
                            "technologies",
                            "concepts",
                            "topic",
                        }
                    ),
                    "evidences": [item.model_dump() for item in selected],
                    "answer_mode": "confident_candidate_with_separate_audit",
                },
                AnswerDraft,
            )
        else:
            draft = _offline_draft(question, claim, selected)
        valid = {item.id: item for item in selected}
        if any(eid not in valid for eid in draft.evidence_ids):
            raise ValueError("Answerer cited evidence outside the provided claim context")
        if draft.reference_material_ids:
            raise ValueError("Answerer cited reference material outside the provided answer context")
        for text in [
            draft.technical_explanation,
            draft.technology_decision,
            *draft.failure_modes,
            *draft.improvement_directions,
        ]:
            check_general_knowledge(text)
        citations = list(dict.fromkeys(draft.evidence_ids))
        code = [valid[eid] for eid in citations if valid[eid].evidence_type == "implementation"]
        tests = [valid[eid] for eid in citations if valid[eid].evidence_type in {"test", "evaluation"}]
        unsupported = list(
            dict.fromkeys(
                draft.unsupported_claims
                + [
                    f"简历自述：{claim.source_quote}",
                    "源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。",
                ]
            )
        )
        if tests:
            unsupported.append(
                "当前引用包含测试或评测材料，但静态源码不证明已经执行；正确性结果和性能提升仍未核验。"
            )
        else:
            unsupported.append("当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。")
        if not code:
            unsupported.append("当前扫描未找到相关实现；工程步骤作为方案推演保留，未登记为仓库事实。")
        raw_direct = draft.direct_interview_answer or "\n\n".join(
            [
                draft.technical_explanation,
                draft.technology_decision,
                *draft.inferred_details,
                *draft.failure_modes,
                *draft.experiment_plan,
            ]
        )
        _check_candidate_assertions(raw_direct, claim)
        direct = _strip_audit_boilerplate(raw_direct)
        if not direct:
            direct = _offline_draft(question, claim, selected).direct_interview_answer
        removed = raw_direct.strip() != direct.strip() and AUDIT_BOILERPLATE.search(raw_direct)
        if removed:
            unsupported.append("模型输出中的来源审计措辞已从口述回答移出；来源状态以本审计记录为准。")
        basis = [f"简历项目与能力：{claim.project} / {claim.topic}"]
        basis.extend(f"源码依据：[{eid}] {valid[eid].file_path}:{valid[eid].line_start}" for eid in citations)
        basis.extend(draft.reasoning_basis)
        if draft.inferred_details or draft.experiment_plan:
            basis.append("工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。")
        return Answer(
            question_id=question.id,
            direct_interview_answer=direct,
            evidence_selection=matches,
            evidence_ids=citations,
            reference_material_ids=[],
            technical_explanation=draft.technical_explanation,
            technology_decision=draft.technology_decision,
            failure_modes=draft.failure_modes,
            unsupported_claims=unsupported,
            likely_followups=draft.likely_followups,
            related_knowledge=draft.related_knowledge,
            improvement_directions=draft.improvement_directions,
            reasoning_basis=list(dict.fromkeys(basis)),
            inferred_details=draft.inferred_details,
            experiment_plan=draft.experiment_plan,
            answerability="medium" if code else "low",
            signals=_spoken_signals(draft, direct),
            material_gaps=[MaterialGap(description=x) for x in unsupported],
            provenance="model" if self.client else "offline",
        )
