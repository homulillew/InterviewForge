import re
from interview_forge.interview.engine import review_session
from interview_forge.knowledge.graph import tree_view
from interview_forge.storage.session import atomic_write


def literal_block(text):
    fence = "`" * max(3, max((len(part) for part in re.findall(r"`+", text)), default=0) + 1)
    return fence + "text\n" + text + "\n" + fence


def source_quotes(ids, sources):
    return "\n\n".join(
        f"[{eid}] {sources[eid].file_path}:{sources[eid].line_start}-{sources[eid].line_end} "
        f"({sources[eid].evidence_type})\n\n" + literal_block(sources[eid].excerpt)
        for eid in ids) or "No verified source"


def export_reports(store, session):
    review = review_session(session)
    def write(name, text):
        atomic_write(store.directory / name, text.rstrip() + "\n")
    write("resume.md", session.resume)
    write("jd.md", session.jd)
    for name, value in {
        "repository_map.json": session.repository_map.model_dump(),
        "claims.json": [c.model_dump() for c in session.claims],
        "attack_surfaces.json": [a.model_dump() for a in session.attack_surfaces],
        "evidence_relations.json": [r.model_dump() for r in session.evidence_relations],
        "question_provenance.json": [t.question.provenance.model_dump() for t in session.transcript],
        "interview_style_trace.json": {"pin": session.corpus_pin.model_dump() if session.corpus_pin else None,
            "effective_style": session.effective_style.model_dump()},
        "evidences.json": [e.model_dump() for e in session.evidences],
        "transcript.json": [t.model_dump() for t in session.transcript],
        "knowledge_graph.json": session.knowledge_graph.model_dump(),
        "study_plan.json": [t.model_dump() for t in session.study_plan],
        "study_cards.json": [c.model_dump() for c in session.study_cards],
        "retests.json": [r.model_dump() for r in session.retests],
        "materials.json": [m.model_dump() for m in session.materials],
        "post_interview_review.json": review.model_dump(),
    }.items():
        store.export_json(name, value)
    style = session.effective_style
    write("interview_style_trace.md", "# Interview Style Trace\n\n" +
        f"Target: {session.config.company or '*'} / {session.config.role or '*'} / {session.config.round or '*'}\n\n" +
        f"Mode: {session.config.style}; independent samples: {style.sample_size}; confidence: {style.confidence:.3f}\n\n" +
        "\n".join(style.backoff_path) + "\n\n" +
        "\n\n".join(f"{t.question.id}: {t.question.provenance.model_dump_json()}" for t in session.transcript))
    risk = ["# Claim Risk Report", "", "Risk is an explainable heuristic, not interview probability calibration.", ""]
    for c in session.claims:
        risk += [f"## {c.id} · {c.risk_score} · {c.proposition}", f"来源：{c.source_quote}",
                 f"Answerability: {c.answerability}; Mastery: {c.mastery.status}", "; ".join(c.risk_reasons), ""]
    write("claim_risk_report.md", "\n\n".join(risk))
    grounding = ["# Repository Evidence Map", "", *session.repository_map.limitations]
    for e in session.evidences:
        grounding += [f"## {e.id}: {e.file_path}:{e.line_start}-{e.line_end}",
                      f"Claims: {', '.join(e.related_claim_ids)} · {e.evidence_type} · sha256: {e.sha256}",
                      literal_block(e.excerpt), "; ".join(e.limitations)]
    write("repository_evidence_map.md", "\n\n".join(grounding))
    transcript, answers, chains = ["# Adversarial Interview Transcript"], ["# Best Answer Cards"], ["# Follow-up Chains"]
    sources = {e.id: e for e in session.evidences}
    for t in session.transcript:
        transcript += [f"## {t.id} · {t.question.claim_id} · L{t.question.level}", t.question.text,
                       t.answer.direct_interview_answer]
        a = t.answer
        answers += [f"## {t.question.id}: {t.question.text}", a.direct_interview_answer,
                    "### 可能的追问", "\n".join("- " + q for q in a.likely_followups)]
        chains += [f"{t.question.based_on_turn or 'start'} → {t.id}: {t.question.text}", t.question.rationale]
    write("transcript.md", "\n\n".join(transcript))
    write("best_answer_cards.md", "\n\n".join(answers))
    write("followup_chains.md", "\n\n".join(chains))
    feedback = ["# Candidate Retest Feedback"]
    for attempt in session.retests:
        if attempt.human_answer is None:
            continue  # No rubric or reference material before submission.
        feedback += [f"## {attempt.id} · {attempt.node_id}", attempt.question.text,
                     "### Submitted Answer", literal_block(attempt.human_answer)]
        if attempt.assessment:
            assessment = attempt.assessment
            feedback += [f"### Assessment ({assessment.assessor}, {assessment.score:.2f})",
                         assessment.rationale, "Missed points: " + "; ".join(assessment.missed_points)]
        if attempt.reference:
            feedback += ["### Reference Answer", attempt.reference.direct_interview_answer]
        if attempt.reference is None or attempt.assessment is None:
            feedback.append("答案已保存，反馈待完成。使用 grade-retest 继续，无需重交答案。")
    write("retest_feedback.md", "\n\n".join(feedback))
    # Audit/provenance is retained independently from what a candidate says aloud.
    audits = []
    usage = []
    material_map = {m.id: m for m in session.materials}
    answer_records = [(t.id, t.question, t.answer) for t in session.transcript]
    answer_records += [(r.id, r.question, r.reference) for r in session.retests if r.human_answer and r.reference]
    audit_text = ["# Answer Reasoning and Source Audit"]
    for record_id, question, answer in answer_records:
        record = {"record_id": record_id, "question_id": question.id,
                  "repository_evidence": answer.evidence_ids,
                  "reference_material_ids": answer.reference_material_ids,
                  "reasoning_basis": answer.reasoning_basis, "inferred_details": answer.inferred_details,
                  "experiment_plan": answer.experiment_plan, "unsupported_claims": answer.unsupported_claims}
        audits.append(record)
        audit_text += [f"## {record_id} · {question.text}", "### Project Grounding", source_quotes(answer.evidence_ids, sources),
            "### Retrieval Rationale (relevance, not proof)",
            "\n".join(f"- {m.evidence_id}: {m.relevance_score} — {'; '.join(m.reasons)}" for m in answer.evidence_selection),
            "### Reasoning Basis", "\n".join(answer.reasoning_basis),
            "### Inferred Design Details", "\n".join(answer.inferred_details),
            "### Experiment Plan", "\n".join(answer.experiment_plan),
            "### Unsupported / Unverified", "\n".join(answer.unsupported_claims)]
        for mid in [*question.material_ids, *answer.reference_material_ids]:
            material = material_map[mid]
            usage.append({"record_id": record_id, "question_id": question.id, **material.model_dump()})
            audit_text += [f"### Reference {mid}", f"{material.source_file} · {material.location}", literal_block(material.source_quote)]
    store.export_json("answer_audit.json", audits)
    store.export_json("material_usage.json", usage)
    write("answer_audit.md", "\n\n".join(audit_text))
    write("knowledge_tree.md", "# Interview Knowledge Tree\n\n```text\n" + tree_view(session.knowledge_graph) + "```\n")
    cards = ["# Study Cards", "默认 P0/P1、distance 0/1；模拟产物不代表个人已经掌握。"]
    for c in session.study_cards:
        cards += [f"## {c.title or c.node_id} · {c.priority} · distance {c.interview_distance} · {c.time_minutes} min",
            c.one_liner, c.explanation, "Must know: " + "; ".join(c.must_know), "Traps: " + "; ".join(c.common_traps),
            *[f"Q: {qa.question}\n\nA: {qa.answer}" for qa in c.followup_qa],
            "Project anchors: " + "; ".join(c.project_anchors), "Retest: " + "; ".join(c.retest_questions)]
    write("study_cards.md", "\n\n".join(cards))
    practice = ["# Targeted Practice"]
    retest = ["# Retest Questions", "这是题目清单。CLI retest 在用户提交前不生成参考答案。"]
    for task in session.study_plan:
        practice += [f"## {task.id}: {task.root_knowledge_gap}", f"{task.gap_kind}: {task.weakness}",
                     "Interview evidence: " + ", ".join(task.evidence_from_interview),
                     *[f"{e.kind}: {e.prompt}\n\nEvidence produced: {e.evidence_produced}" for e in task.exercises], task.project_task]
        retest += [f"## {task.node_id}", *task.retest_questions]
    write("practice_questions.md", "\n\n".join(practice))
    write("retest_questions.md", "\n\n".join(retest))
    report = ["# Post Interview Review", review.interpretation,
              f"Turns: {len(session.transcript)}; covered claims: {sum(v > 0 for v in review.claim_coverage.values())}/{len(session.claims)}; stop: {session.stop_reason or session.status}"]
    for key, value in review.model_dump().items():
        if key == "interpretation":
            continue
        report += ["## " + key.replace("_", " ").title()]
        if isinstance(value, dict):
            report += ["\n".join(f"- {k}: {v}" for k, v in value.items())]
        else:
            report += ["\n".join("- " + str(x) for x in value) or "当前没有足够观察；不据此推断已掌握。"]
    write("post_interview_review.md", "\n\n".join(report))
    write("knowledge_gap_report.md", "# Knowledge Gaps\n\n" + "\n".join(
        f"- {t.root_knowledge_gap}: {t.weakness} ({', '.join(t.evidence_from_interview)})" for t in session.study_plan))
    write("next_round_plan.md", "# Next Round\n\n" + "\n".join("- " + x for x in review.recommended_next_round))
