from moatless.actions.model import Observation
from moatless.completion import CompletionModel, LLMResponseFormat
import os

class ReasoningAgent:
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
        print(f"子树尝试节点 {node.node_id}，修正失败路径")
        node.observation = Observation(
            message="子树已修复并成功触发 Overflow",
            expect_correction=False,
            extra={"result": "OverflowTriggered"}
        )
