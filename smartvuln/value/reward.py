from moatless.value_function.base import ValueFunction
from moatless.value_function.model import Reward

class VulnRewardFunction(ValueFunction):
    def get_reward(self, node):
        if "Overflow" in node.observation.message:
            return Reward(value=100, explanation="成功触发漏洞"), None
        return Reward(value=0, explanation="未触发"), None
