# Reference research and provenance

Checked 2026-09-10/11 via GitHub repository metadata, source tree, README, SKILL and LICENSE where present. No upstream source code or substantial prose is incorporated into InterviewForge. All implementation and instructions here are original.

GitHub license metadata is only a discovery signal; the MIT LICENSE files were fetched and read. Repositories without a discovered license are behavioral/architectural references only.

## [CHfaithwy/cs-tech-interviewer-skill](https://github.com/CHfaithwy/cs-tech-interviewer-skill)

- Source snapshot: `7c50eaec828415f6ef4c6c4689b05416d1259bb7`.
- License observed: 未发现明确 License.
- Read: `README.md`, `SKILL.md`.
- 观察：简历/JD 风险、阶段状态、transcript、复盘与下一轮建议。
- 本项目选择：将风险、过程记录、下一轮目标落盘为版本化状态；避免把题库抽样当动态追问。

## [Ember452/smart-interview-prep](https://github.com/Ember452/smart-interview-prep)

- Source snapshot: `4bdee4bc9612efe91c896f6c32a4402ca5fd6215`.
- License observed: MIT.
- Read: `LICENSE`, `README.md`, `SKILL.md`.
- 观察：回答信号触发连续追问，单话题与跨子主题的不同深度控制。
- 本项目选择：分离 level 和 depth；回答信号路由、每 Claim 上限与知识新颖度共同停止，不复制复杂状态展示。

## [FoLaJJ/Mock-Interviewer-Skill](https://github.com/FoLaJJ/Mock-Interviewer-Skill)

- Source snapshot: `bed4284b0ff11a141ad908cabf2caa7be47edfd4`.
- License observed: 未发现明确 License.
- Read: `README.md`, `SKILL.md`.
- 观察：质疑个人职责、漂亮指标和项目选型依据。
- 本项目选择：把 Ownership 与 metric boldness 纳入风险，追问保持技术价值，不使用羞辱式人设。

## [noamseg/interview-coach-skill](https://github.com/noamseg/interview-coach-skill)

- Source snapshot: `634a8dd8689e0420c21e5f0c8ae3cfa9e1a7ab7e`.
- License observed: MIT.
- Read: `LICENSE`, `README.md`, `SKILL.md`.
- 观察：跨会话 coaching 状态、根据薄弱点选择练习和后续回访。
- 本项目选择：复测题和 human answer 持久化；新的表现更新学习任务。只保留技术闭环，不扩展薪资和求职通信功能。

## [wanyichen06/LLMInternSkill](https://github.com/wanyichen06/LLMInternSkill)

- Source snapshot: `e57ec94d8810dfeed8dec2c5fc515f0fbaa0a933`.
- License observed: MIT.
- Read: `LICENSE`, `README.md`, `SKILL.md`.
- 观察：真实性边界、证据合约、回答卡与补证据计划。
- 本项目选择：引用源片段与一般知识分栏；每个任务明确 evidence produced 和关联 Claim，禁止把规划写成经历。

## [xinkaichen97/agent-skills](https://github.com/xinkaichen97/agent-skills)

- Source snapshot: `caf9d32ea1deddc4aab75905112f5f11b21e6d7e`.
- License observed: 未发现明确 License.
- Read: `README.md`, `skills/ml-interview-prep/SKILL.md`.
- 观察：ml-interview-prep 的 Gap 驱动学习与理论、代码、应用练习。
- 本项目选择：从问答 Gap 生成任务，RAG 使用小评测实验；训练类型扩展为调试、实现、优化和消融，不照搬 ML 专用流程。

## Cross-project decisions

Resume-driven questioning remains isolated from repository inspection. Evidence matching is never promoted into candidate mastery. A bounded graph replaces an unbounded study tree; shared concepts retain all source questions. Offline curricula are explicitly a reproducible baseline, while the provider interface enables semantic generation without tying the core to one SDK.

Technical implementation references: [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/) and [Python urllib.request](https://docs.python.org/3/library/urllib.request.html).

## Technical learning references

The offline explanations were cross-checked against primary documentation. Redis
script execution blocks interleaving server work; the learning material treats this as
an execution guarantee rather than a broad production consistency claim.
See [Redis Lua scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/)
and [Redis transactions](https://redis.io/docs/latest/develop/using-commands/transactions/).

Two-stage retrieval uses a fast candidate stage before a more expensive ranking stage;
this does not establish the architecture of an injected ranker in an arbitrary repository.
See [Sentence Transformers retrieve and rerank](https://sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html).
