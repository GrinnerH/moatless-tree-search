from moatless.feedback import FeedbackGenerator
from moatless.node import FeedbackData
from smartvuln.agent.reasoning_agent import ReasoningAgent
from moatless.node import Node

class SubtreeFeedbackGenerator(FeedbackGenerator):
    def generate_feedback(self, node, actions=None):
        # 如果 observation 有 expect_correction 则调用子树
        if node.observation and node.observation.expect_correction:
            print(f"\n⚠️ 触发推理子树处理 Node{node.node_id} 失败分支...")
            agent = ReasoningAgent()
            agent.run(node)  # 直接模拟成功
        return FeedbackData(feedback="尝试使用子树修复失败路径")
