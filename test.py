from smartvuln.tree.operation_tree import OperationTree  # 新增封装类
from smartvuln.agent.operation_agent import OperationAgent
from smartvuln.value.reward import VulnRewardFunction
from smartvuln.feedback.subtree_feedback import SubtreeFeedbackGenerator

# 1. 构建操作层级 Agent
agent = OperationAgent(actions=actions, completion_model=completion_model)

# 2. 创建操作树（主流程搜索器）
operation_tree = OperationTree.create(
    message=instance["vuln_goal_description"],
    agent=agent,
    file_context=file_context,
    selector=selector,
    value_function=VulnRewardFunction(trigger_tags=["OverflowTriggered"]),
    feedback_generator=SubtreeFeedbackGenerator(),
    ...
)

# 3. 运行漏洞验证搜索过程
final_node = operation_tree.run_search()

# 4. 输出最终结果
print("最终触发状态：", final_node.observation.message if final_node else "验证失败")
