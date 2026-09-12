"""Conservative structural guards; these complement, not replace, semantic review."""
import re

TRIVIA = re.compile(
    r"(?:在哪个|在哪一|哪个).{0,5}(?:文件|目录|配置)|"
    r"(文件|目录|类名|配置文件).{0,8}(在哪|哪里|叫什么)|"
    r"(有没有|是否存在|存在).{0,35}(依赖|文件|脚本|dependency|class)|"
    r"(仓库|项目)里?有没有|where.{0,40}(file|class|config)|"
    r"which (file|directory|class)|does.{0,35}(contain|have|depend on)", re.I,
)
VALUE = re.compile(
    r"为什么|为何|如何|怎么|怎样|能否|会不会|区别|瓶颈|回滚|补偿|重试|超时|机制|原子|边界|失效|故障|权衡|替代|验证|并发|负责|理解|能够|解释|设计|"
    r"why|how|trade.?off|failure|mechanism|validate|explain|design|understand|responsib", re.I,
)
PROJECT_ASSERTION = re.compile(
    r"(我们|本项目|该项目|当前项目|项目中|项目里).{0,18}(实现了|使用了|采用了|提升了|降低了|部署了|保证了)|"
    r"\b(we|our (?:project|system))\s+(?:implemented|use|used|achieved|deployed|improved)\b", re.I,
)


def claim_quality(text: str) -> tuple[bool, str]:
    if TRIVIA.search(text):
        return False, "Claim must test capability, not repository existence"
    return (True, "capability proposition") if VALUE.search(text) else (False, "No testable technical capability")


def question_quality(text: str) -> tuple[bool, str]:
    if TRIVIA.search(text):
        return False, "Repository trivia is not an interview question"
    if len(text.strip()) < 10 or not VALUE.search(text):
        return False, "Question lacks technical reasoning or a decision"
    return True, "technical reasoning required"


def check_general_knowledge(text: str) -> None:
    if PROJECT_ASSERTION.search(text):
        raise ValueError("Project assertion in general-knowledge field; use source excerpts instead")
