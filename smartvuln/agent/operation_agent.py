# smartvuln/agent/operation_agent.py

import os
from moatless.completion import CompletionModel, LLMResponseFormat
from moatless.agent.agent import ActionAgent
from moatless.actions.model import Observation

class OperationAgent(ActionAgent):
    def __init__(self):
        completion_model = CompletionModel(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            model_base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
            model_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            response_format=LLMResponseFormat.JSON,
            temperature=0.7,
        )

        super().__init__(
            completion=completion_model,
            actions=[],  # 暂时留空，后续添加动作类
            system_prompt="你是一个结构化漏洞验证代理。",
        )

    def run(self, node):
        print(f"🔵 [OPERATION] 执行主树节点 Node: {node.node_id}，执行动作")
        node.observation = Observation(
            message="主树执行失败，触发 NoOverflow",
            expect_correction=True,
            extra={"reason": "NoOverflow"}
        )
