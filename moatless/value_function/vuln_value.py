from typing import List
from pydantic import Field
from moatless.value_function.base import ValueFunction
from moatless.value_function.model import Reward
from moatless.completion import CompletionModel  # ✅ 需要导入

class VulnRewardFunction(ValueFunction):
    trigger_keywords: List[str] = Field(default_factory=lambda: ["OverflowTriggered"])
    completion_model: CompletionModel | None = None  # ✅ 显式声明可为空

    def get_reward(self, node):
        obs = node.observation
        msg = obs.message if obs else ""
        if any(k in msg for k in self.trigger_keywords):
            return Reward(value=100, explanation="触发成功"), None
        return Reward(value=0, explanation="未触发"), None
