from interview_forge.schemas.models import Exercise, StudyCard, StudyTask


def build_learning(session):
    cards, tasks = [], []
    previous = {t.id: t.status for t in session.study_plan}
    for n in session.knowledge_graph.nodes:
        active = (n.priority in {"P0", "P1"} and n.interview_distance <= 1) or (
            session.config.deep_dive and n.priority == "P2" and n.interview_distance <= 2)
        if not active:
            continue
        cards.append(StudyCard(node_id=n.id, one_liner=n.interview_one_liner,
            explanation=n.core_explanation + "\n机制：" + n.key_mechanism + "\n边界：" + "；".join(n.failure_modes[:2]),
            followups=n.likely_followups[:3]))
        weak_turns = [t for t in session.transcript if t.question.id in n.triggered_questions and t.weaknesses_observed]
        weak_retests = [r for r in session.retests if r.node_id == n.id and r.assessment and r.assessment.score < 0.8]
        if not weak_turns and not weak_retests:
            continue
        human = bool(weak_retests)
        sources = [r.id for r in weak_retests] if human else [t.id for t in weak_turns]
        weakness = "; ".join(weak_retests[-1].assessment.missed_points) if human else weak_turns[-1].weaknesses_observed[0]
        weakness = weakness or "尚未解释机制、边界与验证之间的联系"
        exercises = [Exercise(kind="mechanism", prompt=n.practice_questions[0], evidence_produced="一段脱离参考答案的解释，含机制、反例和边界"),
                     Exercise(kind="failure_mode", prompt=f"对{n.title}构造一个失败输入，解释状态变化，并给出可检查的不变量。", evidence_produced="反例、预期状态、实际结果与原因")]
        if n.category == "rag":
            exercises.append(Exercise(kind="mini_evaluation", prompt=f"针对{n.title}，建立至少 10 个带标签的查询，对比有无重排以及两个 top_k 的 NDCG、Recall 与延迟。", evidence_produced="可运行评测脚本、查询标签、配置和原始指标；禁止虚构结果"))
        elif n.category == "redis":
            exercises.append(Exercise(kind="implementation", prompt=f"针对{n.title}，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。", evidence_produced="可运行测试、失败日志、修复说明与运行环境"))
        else:
            exercises.append(Exercise(kind="debugging", prompt=f"针对{n.title}，注入慢依赖和重复请求，用日志定位并验证超时与幂等边界。", evidence_produced="故障注入脚本、请求轨迹、修复前后对比"))
        task_id = "task-" + n.id
        tasks.append(StudyTask(id=task_id, node_id=n.id, weakness=weakness,
            evidence_from_interview=sources, root_knowledge_gap=n.title,
            gap_kind="mastery_gap" if human else "material_gap",
            learning_objectives=[n.interview_one_liner, "区分项目证据、技术假设与改进方向"], exercises=exercises,
            project_task=f"为 {n.title} 补充对应源码/测试/测量证据，注明能支持的 Claim：{', '.join(n.source_claims)}",
            retest_questions=n.retest_questions, mastery_criteria=["脱稿说明核心机制", "给出一个反例和保证边界", "设计可复现验证", "准确说明项目证据与个人职责"],
            status=previous.get(task_id, "pending")))
    return cards, tasks
