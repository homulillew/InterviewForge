> Historical schema 1.0 material-library documentation. Current runtime behavior: [v0.3.1](../docs/iteration-0.3.1.md); new sessions pin corpus and isolate the defender.

# v0.3：随时追加面经，生成完整的候选人口述

本轮把面经与参考回答接入已有双 Agent 面试闭环，并把候选人口述与来源审计拆开。
简历或源码缺少某个环节时，回答可以补足合理的实现思路和实验设计，连续回答问题、
选型、失败与验证，而无需在每句话后插入材料限制。

## 面经与参考回答库

- `library add/list/search/show/remove` 管理独立持久化资料库。
- TXT/MD、DOCX 段落和表格、PDF 文字页与扫描页、PNG/JPEG/WebP 均可读取。
- 图片支持本地 Tesseract 和兼容模型视觉识别，记录页码、段落、行号和识别方式。
- 离线提取问答、编号题目、标题、追问与主题；模型模式按批整理全文。
- 按文件内容与类型去重，保留来源文本及哈希；每份文档完整提取后原子提交。
- 中文词组与技术主题参与检索；读取资料库时验证记录关联和原文引用。

默认目录为 `.interviewforge/library`。通过 `start --library` 或 `attach-library`
关联会话，之后每轮重新检索，所以面经可以在练习过程中随时加入。历史轮次保存
自己的资料快照，删除资料库文档不会破坏已完成回答的出处。
重新提取同一文件时，内容变化会生成新条目版本，既有会话继续保留旧引用。

## 提问与回答

Interviewer 使用面经题目和显式追问来选择切入点，再根据前一轮回答深入机制、
选型、失败与验证。其输入不包含源码片段、参考答案或审计内容。
检索先过滤已覆盖题目，再选择候选，避免前几条面经挡住后续新题；显式主题过滤
防止 Redis 面试仅因“延迟”等通用词取到 RAG 题。问题维度由实际问句决定。

Repository Answerer 使用简历能力主张、相关源码和参考回答组织自然口述。允许
推演具体实现与实验细节，例如初始库存、请求量、对照方案、失败注入和观测指标。
这些内容放在连贯的技术回答里，不用“当前仓库没有”“证据不足”等句式打断表达。
参考回答按问题选取相关片段，单条模型上下文最多 4,000 字符、总计最多 12,000；
完整原文仍保存在资料库和快照中。不同参考实验选择一套连贯参数，避免直接拼接。

`transcript.md` 与 `best_answer_cards.md` 只展示候选人需要练习的回答及追问。
`answer_audit.md/.json` 独立记录源码依据、参考材料、推演细节、实验方案与待核实项。
实验方案不登记为已完成测量，外部参考中的业绩不会转成用户项目事实。

保留真人复测与学习闭环：模拟回答不会提升个人 Mastery；提交真人答案后才生成
参考与反馈，反馈失败可恢复，显式人工复核仍决定面试就绪状态。

## 复现

```bash
python -m pip install -e '.[dev,documents]'
interview-forge library add examples/materials/interview.md --kind interview
interview-forge library add examples/materials/reference_answer.md --kind answer

# 本地 OCR 需另行安装 Tesseract 与 chi_sim、eng 语言数据。
interview-forge library add examples/materials/redis-interview.png \
  --kind interview --ocr local --ocr-language chi_sim+eng
interview-forge library add examples/materials/redis-answer.docx --kind answer

interview-forge start --resume examples/redis/resume.md --repo examples/redis/repo \
  --session sessions/material-demo --max-turns 6 --run
```

`examples/materials/` 中的文本、图片和 Word 均为本仓库自制演示材料。
图片与 Word 示例用于复现实际识别/解析入库；手写问答展示更完整的深挖与实验设计。
完整参数见 [CLI reference](../references/cli.md)。

激活安装好依赖的环境后，也可以直接运行 `bash scripts/run_material_demo.sh`，
一次完成图片/Word 入库与六轮面试；默认输出位于 `sessions/material-demo/session`。

## 验证范围

最终本地回归：**156 项测试通过**，ruff 与 `git diff --check` 通过。
六轮混合资料示例均引用面经和参考回答，已检查主题一致、参数不冲突、来源快照可恢复。

验证包括材料去重、中文检索、来源校验、文档删除、并发写入与失败回滚；
文本/Word/PDF/图片读取、真实本地 OCR 与视觉接口契约；会话中途追加资料、
问题/回答来源隔离、快照恢复、自然口述与独立审计，以及既有复测与 Demo 回归。
发布前还检查 Skill、lint、JSON Schema、源码包、wheel 和独立安装运行。

真实远程模型的提取效果与回答质量需要在所配置的模型上另行评估；本地 fixture
与兼容 HTTP 测试覆盖调用结构、错误恢复和引用契约。
