"""Local adapter: user-configured DeepSeek only; no public cache or answer services."""
import ast
from dataclasses import dataclass
from .DeepSeekAsk import DeepSeekAsk

@dataclass
class Question:
    type: str
    question: str
    options: list
    API: str

class AnswerAPI:
    def cache_answer(self, question, answer):
        pass  # Deliberately no persistent question/answer cache.

async def main(typ, question, options, api, driver=None):
    if not api:
        return []
    result = DeepSeekAsk(api, question + "\n选项：" + str(options), typ)
    try:
        answer = ast.literal_eval(result)
    except (ValueError, SyntaxError):
        return []
    return answer if isinstance(answer, list) and all(isinstance(a, str) for a in answer) else []
