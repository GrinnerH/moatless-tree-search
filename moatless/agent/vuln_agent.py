from moatless.agent.code_agent import CodingAgent
from moatless.agent.agent import ActionAgent
from moatless.actions import (
    Debugger,
    CodeBrowser,
    Script,
    Finish,
    Reject,
)
#FindFunction,
from prompts.system_prompt import SYSTEM_PROMPT
# from prompts.tooluse_prompt import TOOLUSE_PROMPT

def create_vuln_agent(repository, code_index, completion_model):
    actions = [
        Debugger(),
        CodeBrowser(),
        Script(completion_model=completion_model),
        Finish(),
        Reject(),
    ]
    

    return ActionAgent(
        completion=completion_model,
        actions=actions,
        system_prompt=SYSTEM_PROMPT,
        use_few_shots=True
    )
