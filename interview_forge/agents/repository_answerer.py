"""Candidate answers and their audit trail are deliberately separate outputs."""
from __future__ import annotations

import ast
from dataclasses import dataclass
import heapq
import json
import re

from pydantic import Field

from interview_forge.curricula import TOPICS, topic_for
from interview_forge.llm import LLMClient, prompt
from interview_forge.materials.models import MaterialItem
from interview_forge.quality import check_general_knowledge
from interview_forge.repository.retrieval import select_evidence, terms
from interview_forge.schemas.models import Answer, CapabilityClaim, Dimension, InterviewQuestion, Model, RepoEvidence


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
        ("我会先设初始库存为 100，用 1,000 个不同请求并发争抢，检查成功扣减总数等于 100、库存非负，"
         "并把每个成功结果和订单逐条对账。",
         "接着对同一个 request_id 重放请求，在扣减后断开客户端连接，并注入订单写入失败，验证不会重复扣减，"
         "补偿任务多次执行也只产生一次效果。",
         "性能实验把数据库条件更新作为基线，固定机器、连接池和请求分布，逐档增加并发，"
         "同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间，观察瓶颈出现在哪一档。"),
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
        ("我会建立按时间或文档来源隔离的查询集，标注相关段落，并把简单查询、多条件查询和无答案查询分开统计。",
         "对照组保持 embedding、chunk 和生成模型一致，只切换是否重排；候选 top_k 分别取 20、50、100 做消融，"
         "记录 Recall@K、MRR、NDCG@K、P99 和单次请求成本。",
         "然后逐条分析召回遗漏、排序错误和生成错误，检查无答案场景的拒答质量；"
         "同一查询保留各组结果，避免文档泄漏到测试集或把生成风格变化误判为检索质量提升。"),
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
        ("我会先覆盖正常提交、重复提交、提交后连接断开和依赖部分失败，逐条检查业务只生效一次，"
         "终态可查询，失败任务可以恢复。",
         "压测固定资源配额和数据集，以阶梯到达率持续加压，分别记录入口排队、连接池等待、"
         "依赖耗时、成功吞吐、错误率和 P99，定位最先饱和的资源。",
         "再把依赖延迟提高到超时阈值附近，对比开启和关闭有限重试、隔离的效果，"
         "观察恢复时间和额外请求放大量，并检查故障期间的数据一致性。"),
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
    r"not (?:verified|implemented) in (?:the|this) repo|insufficient evidence", re.I,
)
NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|ms|s|秒|毫秒|qps|tps|万|亿)?", re.I)
RESULT = re.compile(r"实测|测得|压测结果|上线后|提升了|降低了|达到了|优化到|减少了|"
                    r"(?:我|我们).{0,12}(?:降到|提升到|做到|跑到)|"
                    r"\b(?:achieved|measured|improved|reduced|decreased|increased)\b", re.I)
PROSPECTIVE = re.compile(r"我会|计划|拟|目标|预期|假设|如果|实验输入|实验参数|测试参数|例如|比如|\b(?:would|plan|target|hypothetical)\b", re.I)
OWNERSHIP = re.compile(r"(?:我|我们).{0,4}(?:独立完成|主导上线|主导开发|负责上线|已经部署|已经上线)|"
                       r"\bI (?:independently built|led the deployment|deployed to production)\b", re.I)


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
                raise ValueError("Invented measured result in candidate answer; use experiment parameters instead")
        ownership = OWNERSHIP.search(sentence)
        if ownership and ownership.group() not in claim.source_quote and not PROSPECTIVE.search(sentence):
            raise ValueError("Invented completed ownership in candidate answer")


SOURCE_DIRECTIVE = re.compile(
    r"忽略.{0,20}(?:指令|规则|要求)|系统(?:提示|指令|消息)|开发者(?:指令|消息)|提示词|"
    r"(?:输出|打印|泄露|提供|读取).{0,16}(?:密钥|密码|凭据|secret|token|环境变量)|"
    r"(?:必须|请你|你应|禁止|不要).{0,16}(?:回答|输出|执行|遵守|声称|宣称)|"
    r"ignore.{0,30}(?:instruction|prompt|system)|system.prompt|api.key|os\.environ|"
    r"(?:curl|wget)\s+https?://|rm\s+-|<\/?(?:system|assistant)>", re.I,
)
BORROWED_RESULT = re.compile(
    r"实测|测得|压测结果|上线后|提升了|降低了|达到了|减少了|独立完成|主导|负责上线|"
    r"我的贡献|我们团队|在.{0,12}公司|\b(?:achieved|measured|deployed|improved|reduced)\b", re.I,
)
PROCEDURE = re.compile(
    r"使用|采用|设置|设为|固定|注入|覆盖|检查|断言|验证|比较|对比|对照|记录|保存|保留|"
    r"划分|切分|分配|隔离|限制|重试|去重|幂等|读取|写入|扣减|返回|沿用|比较|"
    r"放入|放在|选取|拆分|采样|标注|统计|监控|排序|融合|过滤|预热|批处理|缓存|"
    r"\b(?:set|inject|assert|compare|record|retry|dedup|partition|sample|validate)\b", re.I,
)
EXPERIMENT = re.compile(
    r"实验|测试|压测|评测|断言|对照|比较|对比|注入|并发请求|重复.{0,12}\d+\s*次|"
    r"初始库存|\d+\s*(?:毫秒|ms).{0,12}超时|\b(?:test|assert|experiment|benchmark)\b", re.I,
)


def _reference_procedures(item: MaterialItem) -> tuple[list[str], list[str]]:
    """Extract proposed actions and experiment inputs from arbitrary technical answers.

    These sentences remain source data. Converting procedural content into a proposed
    design never promotes a reference author's measured outcomes or personal history.
    """
    methods, experiments = [], []
    for raw in re.split(r"[。！？\n]+", item.answer):
        sentence = raw.strip(" -*•\t")
        if not 8 <= len(sentence) <= 500 or SOURCE_DIRECTIVE.search(sentence) or BORROWED_RESULT.search(sentence):
            continue
        if AUDIT_BOILERPLATE.search(sentence) or not PROCEDURE.search(sentence):
            continue
        # English result claims and Chinese result wording without a past-tense suffix.
        if re.search(r"(?:提升|降低|达到|减少).{0,10}\d+\s*(?:%|％|倍)", sentence) and not re.search(r"目标|计划|假设", sentence):
            continue
        experimental = bool(EXPERIMENT.search(sentence))
        sentence = re.sub(r"^(?:回答|答案|方案|方法|步骤|实现|实验设计|实验|测试设计|验证方法)\s*[:：]\s*", "", sentence)
        sentence = re.sub(r"^我的(?:方案|做法|处理思路|设计|思路)是", "", sentence)
        sentence = re.sub(r"^(?:在项目中|在项目里|本项目中|本项目|我们项目|我们|我)(?:已经|当时|会)?", "", sentence)
        sentence = re.sub(r"(使用|采用|设置|记录|保存|保留|固定|检查|划分|切分|分配|返回)了", r"\1", sentence)
        sentence = sentence.lstrip("，,:： ")
        if not sentence or re.search(r"我(?:们)?|个人贡献|生产.{0,8}(?:万|亿)", sentence):
            continue
        if experimental:
            if sentence.startswith("断言"):
                sentence = sentence[2:]
                rendered = "验证时，我会检查：" + sentence + "。"
            else:
                rendered = "实验上，我会这样安排：" + sentence + "。"
            if len(experiments) < 4 and rendered not in experiments:
                experiments.append(rendered)
        else:
            rendered = "具体处理时，我会采用这个流程：" + sentence + "。"
            if len(methods) < 2 and rendered not in methods:
                methods.append(rendered)
    return methods, experiments


def _reference_extensions(items: list[MaterialItem], key: str, question: InterviewQuestion) -> tuple[list[str], list[str], list[str]]:
    """Combine source-specific procedures with authored explanations of common methods."""
    additions, experiments, used = [], [], []
    rules = {
        "redis": [
            (r"outbox|事务消息|事务发件箱", "跨库存和订单的衔接上，我会用持久化状态记录扣减结果，"
             "业务落库时通过 outbox 同事务记录待发送事件，再由消费者按事件 ID 幂等处理。"),
            (r"(?:令牌桶|token.bucket)", "入口限流我会用令牌桶允许有限突发，同时给库存扣减配置独立并发上限，"
             "把流量控制和库存正确性分开验证。"),
            (r"(?:对账|补偿|reconcil)", "对账任务我会按业务请求 ID 比较预扣、订单和补偿状态，"
             "只重放缺失的状态迁移，并保留重试次数和人工处理入口。"),
        ],
        "rag": [
            (r"bm25|rrf|混合检索|hybrid", "召回层我会并行保留 BM25 的关键词匹配和向量检索的语义匹配，"
             "用 RRF 融合排名后再重排；评测时单独比较两路召回和融合，定位互补收益。"),
            (r"hard.negative|困难负例|难负例", "评测集我会加入表面词汇相近但答案错误的困难负例，"
             "检查重排器是否真正识别问题约束，并把同源文档放在同一数据切分内。"),
            (r"消融|ablation", "消融时我会每次只改变一个因素，分别比较 chunk 粒度、召回数量和重排开关，"
             "对同一批查询做成对比较，再检查收益是否集中在少数查询类型。"),
        ],
        "service": [
            (r"outbox|事务消息|事务发件箱", "事务提交和消息发送之间，我会采用 outbox："
             "业务记录和待发送事件同事务落库，后台投递允许重试，消费端通过事件 ID 去重。"),
            (r"死信|dead.letter|dlq", "异步任务连续失败后我会进入死信队列，保留错误分类和业务键，"
             "修复原因后按原业务键重放，避免无限重试拖累正常任务。"),
            (r"令牌桶|token.bucket", "限流我会用令牌桶控制平均速率和可接受突发，"
             "再用并发限制保护慢依赖；观察限流率、排队时间和成功率是否符合服务目标。"),
        ],
    }
    query = _context_terms(_current_question(question))
    sources, method_candidates = [], []
    for index, item in enumerate(items[:4]):
        text = " ".join([item.question, item.answer, item.title, *item.topics, *item.tags])
        methods, plans = _reference_procedures(item)
        relevance = (5 * len(query & _context_terms(item.question + " " + item.title))
                     + len(query & _context_terms(item.answer)))
        sources.append((relevance, -index, item.id, plans))
        for pattern, explanation in rules[key]:
            if re.search(pattern, text, re.I):
                methods.append(explanation)
                break
        for position, method in enumerate(methods):
            score = 3 * len(query & _context_terms(method)) + relevance / 10
            method_candidates.append((score, -index, -position, item.id, method))
    # One source supplies a coherent experiment. Different loads in other documents
    # are alternatives, not extra parameters to silently merge into the same run.
    experimental_sources = [source for source in sources if source[3]]
    if experimental_sources:
        _, _, primary_id, experiments = max(experimental_sources)
        used.append(primary_id)
    seen_terms, covered_features = [], set()
    for _, _, _, source_id, method in sorted(method_candidates, reverse=True):
        method_terms = _context_terms(method.removeprefix("具体处理时，我会采用这个流程："))
        features = {name for name, pattern in {
            "stock": r"库存|stock", "script": r"Lua|脚本", "dedup": r"幂等|request_id|重复.*结果",
            "slot": r"hash.?tag|槽位", "expiry": r"TTL|过期|保留期|重试窗口", "recovery": r"补偿|对账",
            "outbox": r"outbox|事务消息", "rrf": r"RRF", "bm25": r"BM25",
        }.items() if re.search(pattern, method, re.I)}
        if (features and features <= covered_features) or any(
                len(method_terms & previous) / max(1, len(method_terms | previous)) > 0.55 for previous in seen_terms):
            continue
        if len(additions) == 3 or sum(map(len, additions)) + len(method) > 550:
            continue
        additions.append(method)
        seen_terms.append(method_terms)
        covered_features.update(features)
        used.append(source_id)
    return additions, experiments, list(dict.fromkeys(used))


def _current_question(question: InterviewQuestion) -> str:
    return re.sub(r"^(?:上一答|你刚才).*?[”\"]\s*[；;，,]", "", question.text).split("”；", 1)[-1]


def _diagnostic_answer(question: InterviewQuestion, key: str) -> list[str]:
    text = _current_question(question)
    if re.search(r"(?:吞吐|QPS).*(?:不再|不增|平台|停滞|下降)|P99.*(?:变高|升高|增长|飙升)|定位瓶颈", text, re.I):
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
            component + ("同时检查订单数据库的锁等待和写入耗时。" if key == "redis" else "")
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
            (r"补偿|多加库存", "补偿本身也要幂等。我用原订单 ID 和补偿类型标识一次归还操作，"
             "只有状态从已扣减成功迁移到已补偿时才增加库存。状态检查、归还库存和保存补偿结果放在同一原子边界内；"
             "重复任务直接返回已补偿结果，不能每收到一条消息就再加一次库存。"),
            (r"回滚|脚本.*(?:报错|错误)|rollback", "Lua 脚本的原子执行解决的是并发插入问题。"
             "脚本执行到一半报错，已经完成的写入仍然保留，所以我会把参数、key 类型和业务条件检查放在写操作之前，"
             "缩短写入路径，并用幂等记录与补偿任务处理跨资源失败。"),
            (r"hash.?tag|槽位|cluster|集群.*key", "多 key 脚本要先把 key 放进同一个 Redis Cluster 槽位。"
             "我会让库存 key 和幂等 key 使用同一个业务 hash tag，把脚本涉及的 key 显式传入 KEYS；"
             "跨槽的数据改用分步状态迁移和补偿，避免让单次扣减依赖跨分片协调。"),
            (r"超时|重试|幂等|request_id", "超时后我首先按原 request_id 查询或重试，复用第一次处理结果。"
             "因为客户端超时可能发生在扣减之后，把重试当成新请求会重复扣库存；"
             "去重检查、扣减和保存结果需要放在同一个执行边界内。"),
        ],
        "rag": [
            (r"数据泄漏|切分|泄露|leakage", "评测切分我会按文档来源和时间隔离，再对近重复段落去重，"
             "同一文档的不同 chunk 放进同一个集合。调参只用验证集，测试集在配置冻结后使用，"
             "同时检查参考答案有没有进入索引，防止测到的是答案泄漏。"),
            (r"chunk|分块|切块", "分块我会先保留标题层级和段落边界，让每块能独立表达一个事实或步骤。"
             "长段落再按 token 预算切分，重叠区域用于衔接上下文；"
             "评测同时观察块级召回和最终答案质量，避免召回很多碎片却拼不出完整答案。"),
            (r"cross.encoder|bi.encoder|联合编码", "bi-encoder 分别编码 query 和文档，文档向量可以离线计算，"
             "适合大规模召回；cross-encoder 把 query 和文档放在一起编码，交互更充分，计算也更贵。"
             "我的处理是把较贵的逐对打分限制在小候选集内，用质量增益和延迟预算决定是否采用。"),
        ],
        "service": [
            (r"幂等|重复|重试|idempot", "我会让一次业务操作始终使用同一个唯一键，并把唯一约束和业务写入放进同一事务。"
             "并发重复请求由数据库约束收敛到同一结果，重试复用这个键；"
             "如果只先查缓存再写数据库，两个请求仍可能同时通过检查。"),
            (r"熔断|circuit", "熔断器我会按依赖和错误类型分别统计，持续失败时快速返回降级结果，"
             "经过冷却窗口后放少量半开探测请求。它需要配合超时和并发隔离："
             "超时控制单次等待，隔离控制被占用的资源，熔断减少持续访问失败依赖。"),
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
        names = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,48}", node.name)
                 and not node.name.startswith("test_")]
        if names:
            return f"讲实现时，我会从 {names[0]} 这个函数展开，把输入校验、核心处理和失败后的状态分别说明。"
    return ""



def _reference_speech(methods: list[str], experiments: list[str]) -> tuple[str, str]:
    """Keep source-derived detail without repeating extraction labels in speech."""
    procedure_prefix = "具体处理时，我会采用这个流程："
    experimental_prefix = "实验上，我会这样安排："
    methods_text = "".join(item.removeprefix(procedure_prefix) for item in methods)
    if methods_text:
        methods_text = "落地时，我会这样组织处理：" + methods_text
    steps = []
    for item in experiments:
        step = item.removeprefix(experimental_prefix)
        if step.startswith("验证时，我会检查："):
            step = "验收条件是：" + step.removeprefix("验证时，我会检查：")
        step = re.sub(r"^实验同时比较", "同时比较", step)
        steps.append(step)
    experiments_text = "实验上，我会这样安排：" + "".join(steps) if steps else ""
    return methods_text, experiments_text


def _offline_draft(question: InterviewQuestion, claim: CapabilityClaim,
                   selected: list[RepoEvidence], references: list[MaterialItem]) -> AnswerDraft:
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
    additions, reference_experiments, reference_ids = _reference_extensions(references, key, question)
    experiments = reference_experiments or list(blueprint.experiments)
    if reference_experiments and not any(re.search(r"P99|NDCG|MRR|吞吐", item, re.I) for item in reference_experiments):
        experiments = [*reference_experiments, blueprint.experiments[-1]]
    reference_flow, reference_experiment_speech = _reference_speech(additions, reference_experiments)
    application = reference_flow or blueprint.application
    diagnostic = _diagnostic_answer(question, key)
    if diagnostic:
        paragraphs = diagnostic
        explanation = diagnostic[0]
        diagnostic_terms = re.compile(
            r"P99|吞吐|CPU|连接池|排队" if diagnostic[0].startswith("吞吐")
            else r"提交|断连|断开连接|响应.{0,4}丢失|同一.{0,8}(?:业务键|request_id)", re.I)
        focused_plans = [plan for plan in reference_experiments if diagnostic_terms.search(plan)]
        if focused_plans:
            paragraphs.append(_reference_speech([], focused_plans[:1])[1])
        experiments = [diagnostic[-1], *focused_plans]
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
        validation = _reference_speech([], failure_plans[:2])[1]
        paragraphs = [lead, recovery, validation]
    elif question.dimension in {Dimension.decision, Dimension.tradeoff}:
        paragraphs = [blueprint.decision, explanation, experiments[-1]]
        if reference_flow:
            paragraphs.insert(2, reference_flow)
    elif question.dimension == Dimension.evaluation or "评测" in question.subtopic:
        experiment_speech = ([reference_experiment_speech, *experiments[len(reference_experiments):]]
                             if reference_experiments else experiments)
        paragraphs = [lead, *experiment_speech]
        if key == "rag" and reference_flow:
            paragraphs.append(reference_flow)
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
        evidence_ids=[item.id for item in selected[:3]], reference_material_ids=reference_ids,
        direct_interview_answer=direct, technical_explanation=explanation,
        technology_decision=blueprint.decision, failure_modes=[blueprint.failure],
        unsupported_claims=[], likely_followups=list(topic.questions[1:]),
        related_knowledge=[topic.title, topic.prerequisite],
        improvement_directions=[blueprint.scaling], inferred_details=[blueprint.application, *additions],
        experiment_plan=experiments, signals=["solid"],
    )


def _spoken_signals(draft: AnswerDraft, direct: str) -> list[str]:
    allowed = {"vague", "api_only", "no_implementation", "no_decision", "no_measurement", "failure_gap", "solid"}
    signals = [signal for signal in draft.signals if signal in allowed and signal != "solid"]
    coverage = {
        "no_implementation": bool(re.search(r"脚本|事务|唯一约束|chunk|去重|幂等|hash tag|request_id", direct, re.I)),
        "no_decision": bool(re.search(r"选型|优先|对比|权衡|决策|而不是|选择|相比|取舍", direct)),
        "no_measurement": bool(re.search(r"验证|实验|测试|压测|评测|对照", direct)
                               and re.search(r"P99|NDCG|MRR|Recall|吞吐|成功率|成功.*总数|对账|错误率", direct, re.I)),
        "failure_gap": bool(re.search(r"失败|超时|故障|补偿|降级|重试|漏召回", direct)),
    }
    signals = [signal for signal in signals if not coverage.get(signal, False)]
    return list(dict.fromkeys(signals)) or ["solid"]



REFERENCE_ITEM_BUDGET = 4000
REFERENCE_TOTAL_BUDGET = 12000


def _context_terms(text: str) -> set[str]:
    result = terms(text)
    stop = {"如何", "为什么", "什么", "怎么", "我们", "可以", "这个", "一个", "问题", "设计"}
    for word in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        result.update(word[index:index + 2] for index in range(len(word) - 1))
    return result - stop


def _relevant_reference_excerpt(text: str, question: InterviewQuestion, claim: CapabilityClaim,
                                budget: int) -> str:
    if len(text) <= budget:
        return text
    query = _context_terms(question.text.split("”；", 1)[-1][-2000:] + " " + question.subtopic)
    context = _context_terms(claim.topic[:300] + " " + claim.proposition[:500])
    ranked = []
    # Retain only twelve candidates while scanning the full document, including its tail.
    # Long paragraphs are windowed; no list of every sentence or full document copy is built.
    for match in re.finditer(r"[^\n。！？]+[。！？]?", text):
        for start in range(match.start(), match.end(), 900):
            passage = text[start:min(start + 900, match.end())].strip()
            lowered = passage.lower()
            score = 3 * sum(term in lowered for term in query) + sum(term in lowered for term in context)
            if question.dimension == Dimension.evaluation and EXPERIMENT.search(passage):
                score += 3
            candidate = (score, -start, start, passage)
            if len(ranked) < 12:
                heapq.heappush(ranked, candidate)
            elif candidate[:2] > ranked[0][:2]:
                heapq.heapreplace(ranked, candidate)
    chosen, remaining = [], budget
    for _, _, start, passage in sorted(ranked, reverse=True):
        if len(passage) + 1 <= remaining:
            chosen.append((start, passage))
            remaining -= len(passage) + 1
    if not chosen and ranked:
        best = max(ranked)
        return best[3][:budget]
    return "\n".join(passage for _, passage in sorted(chosen))


def _bounded_reference_context(question: InterviewQuestion, claim: CapabilityClaim,
                               references: list[MaterialItem]) -> tuple[list[MaterialItem], list[dict]]:
    bounded, payloads = [], []
    remaining = REFERENCE_TOTAL_BUDGET - 2  # JSON list brackets.
    for item in references[:4]:
        metadata = {
            "id": item.id, "kind": item.kind, "title": item.title[:160], "question": item.question[:320],
            "topics": [topic[:40] for topic in item.topics[:5]], "tags": [tag[:40] for tag in item.tags[:5]],
        }
        allowance = min(REFERENCE_ITEM_BUDGET, remaining - 2)
        overhead = len(json.dumps({**metadata, "answer": ""}, ensure_ascii=False))
        if allowance - overhead < 100:
            continue
        excerpt = _relevant_reference_excerpt(item.answer, question, claim, min(3200, allowance - overhead))
        payload = {**metadata, "answer": excerpt}
        cost = len(json.dumps(payload, ensure_ascii=False))
        # JSON escaping adds characters for line breaks and literal backslashes.
        while cost > allowance and excerpt:
            excerpt = excerpt[:max(0, len(excerpt) - (cost - allowance))]
            payload["answer"] = excerpt
            cost = len(json.dumps(payload, ensure_ascii=False))
        bounded.append(item.model_copy(update={**metadata, "answer": excerpt, "source_quote": ""}))
        payloads.append(payload)
        remaining -= cost + 2
    return bounded, payloads


class RepositoryAnswerer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def answer(self, question: InterviewQuestion, claim: CapabilityClaim, evidences: list[RepoEvidence],
               reference_materials: list[MaterialItem] | None = None) -> Answer:
        selected, matches = select_evidence(question, claim, evidences)
        references, reference_payloads = _bounded_reference_context(
            question, claim, [item for item in (reference_materials or []) if item.kind == "answer"])
        if self.client:
            draft = self.client.structured_generate(prompt("repo_answerer"), {
                "question": question.model_dump(), "claim": claim.model_dump(exclude={"mastery"}),
                "evidences": [item.model_dump() for item in selected],
                "reference_materials": reference_payloads,
                "answer_mode": "confident_candidate_with_separate_audit",
            }, AnswerDraft)
        else:
            draft = _offline_draft(question, claim, selected, references)
        valid = {item.id: item for item in selected}
        valid_references = {item.id: item for item in references}
        if any(eid not in valid for eid in draft.evidence_ids):
            raise ValueError("Answerer cited evidence outside the provided claim context")
        if any(mid not in valid_references for mid in draft.reference_material_ids):
            raise ValueError("Answerer cited reference material outside the provided answer context")
        for text in [draft.technical_explanation, draft.technology_decision, *draft.failure_modes, *draft.improvement_directions]:
            check_general_knowledge(text)
        citations = list(dict.fromkeys(draft.evidence_ids))
        reference_ids = list(dict.fromkeys(draft.reference_material_ids))
        code = [valid[eid] for eid in citations if valid[eid].evidence_type == "implementation"]
        tests = [valid[eid] for eid in citations if valid[eid].evidence_type in {"test", "evaluation"}]
        unsupported = list(dict.fromkeys(draft.unsupported_claims + [
            f"简历自述：{claim.source_quote}",
            "源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。",
        ]))
        if tests:
            unsupported.append("当前引用包含测试或评测材料，但静态源码不证明已经执行；正确性结果和性能提升仍未核验。")
        else:
            unsupported.append("当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。")
        if not code:
            unsupported.append("当前扫描未找到相关实现；工程步骤作为方案推演保留，未登记为仓库事实。")
        if reference_ids:
            unsupported.append("参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。")
        raw_direct = draft.direct_interview_answer or "\n\n".join([
            draft.technical_explanation, draft.technology_decision,
            *draft.inferred_details, *draft.failure_modes, *draft.experiment_plan,
        ])
        _check_candidate_assertions(raw_direct, claim)
        direct = _strip_audit_boilerplate(raw_direct)
        if not direct:
            direct = _offline_draft(question, claim, selected, references).direct_interview_answer
        removed = raw_direct.strip() != direct.strip() and AUDIT_BOILERPLATE.search(raw_direct)
        if removed:
            unsupported.append("模型输出中的来源审计措辞已从口述回答移出；来源状态以本审计记录为准。")
        basis = [f"简历项目与能力：{claim.project} / {claim.topic}"]
        basis.extend(f"源码依据：[{eid}] {valid[eid].file_path}:{valid[eid].line_start}" for eid in citations)
        basis.extend(f"参考方法：[{mid}] {valid_references[mid].title}" for mid in reference_ids)
        basis.extend(draft.reasoning_basis)
        if draft.inferred_details or draft.experiment_plan:
            basis.append("工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。")
        return Answer(
            question_id=question.id, direct_interview_answer=direct, evidence_selection=matches,
            evidence_ids=citations, reference_material_ids=reference_ids,
            technical_explanation=draft.technical_explanation, technology_decision=draft.technology_decision,
            failure_modes=draft.failure_modes, unsupported_claims=unsupported,
            likely_followups=draft.likely_followups, related_knowledge=draft.related_knowledge,
            improvement_directions=draft.improvement_directions, reasoning_basis=list(dict.fromkeys(basis)),
            inferred_details=draft.inferred_details, experiment_plan=draft.experiment_plan,
            answerability="medium" if code else "low", signals=_spoken_signals(draft, direct),
            provenance="model" if self.client else "offline",
        )
