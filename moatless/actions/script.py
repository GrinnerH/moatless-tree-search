# moatless/actions/script.py

import os
import tempfile
import subprocess
from typing import ClassVar, Type, Optional, List

from pydantic import Field, model_validator, PrivateAttr

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.file_context import FileContext
from moatless.workspace import Workspace
from moatless.completion.completion import CompletionModel


class ScriptArgs(ActionArguments):
    target_file: str = Field(..., description="与脚本关联的目标源文件路径（如 test.cpp）")
    script: str = Field(..., description="要运行的 Python 脚本内容，可包含格式错误")
    model_config = {
        "title": "script",
        "description": "用于运行 Python 脚本模拟漏洞利用或验证行为"
    }
    def to_prompt(self) -> str:
        return f"script('{self.target_file}', '''{self.script[:30]}...''')"

    def short_summary(self) -> str:
        return f"script({os.path.basename(self.target_file)})"

    # class Config:
    #     title = "script"
    #     description = "运行 Python 脚本，并使用 LLM 修复其格式错误（如缩进）"

    @model_validator(mode="after")
    def check_script(self) -> "ScriptArgs":
        if not self.script.strip():
            raise ValueError("script 不能为空")
        return self


class Script(Action):
    name: ClassVar[str] = "script"
    description: ClassVar[str] = "运行 Python 脚本，并使用 LLM 修复其格式错误（如缩进）"
    args_schema: ClassVar[Type[ActionArguments]] = ScriptArgs
    # args_schema: ScriptArgs
    completion_model: CompletionModel = Field(..., exclude=True)

    def _execute(
        self,
        args: ScriptArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        base_name = os.path.splitext(os.path.basename(args.target_file))[0]
        temp_dir = os.path.join("temp", base_name)
        os.makedirs(temp_dir, exist_ok=True)

        prompt = f"""
Take this python code and fix indentation or any obvious syntax bugs.
Do not change the logic or behavior. 
Return only fixed code, no markdown or explanations.
Code:
{args.script}
""".strip()

        try:
            # 调用模型修复脚本格式
            response = self.completion_model._litellm_base_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "text"},
            )
            fixed_code = response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return Observation(
                message=f"模型格式修复失败: {str(e)}",
                summary="脚本格式化失败",
                expect_correction=True,
            )

        # 写入修复后的脚本
        fd, path = tempfile.mkstemp(suffix='.py', dir=temp_dir)
        with os.fdopen(fd, 'w') as f:
            f.write(fixed_code)

        try:
            result = subprocess.run(
                ['python3', path],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            return Observation(
                message=result.stdout.strip(),
                summary="脚本运行成功",
                extra={
                    "stderr": result.stderr.strip(),
                    "script": fixed_code,
                }
            )
        except subprocess.CalledProcessError as e:
            return Observation(
                message="运行失败（CalledProcessError）",
                summary="脚本运行失败",
                extra={
                    "returncode": e.returncode,
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                    "script": fixed_code,
                },
                expect_correction=True,
            )
        except Exception as e:
            return Observation(
                message=f"执行异常: {type(e).__name__}: {str(e)}",
                summary="脚本运行异常",
                extra={"script": fixed_code},
                expect_correction=True,
            )

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="Run a Python script to compile and execute test.cpp.",
                action=ScriptArgs(
                    target_file="test.cpp",
                    script="import os\\nos.system('g++ test.cpp -o test && ./test')"
                )
            )
        ]
    

    @classmethod
    def get_value_function_prompt(cls) -> str:
        return """Your role is to evaluate the **last executed action** of the search tree that our AI agents are traversing in order to validate potential vulnerabilities in target programs.

    The agent has used the `script` tool to execute a custom Python script. This tool allows agents to compile the program, run it with crafted inputs, or automate test sequences aimed at **triggering memory-safety violations**.

    Important: Scripts can simulate exploits, mutate input payloads, or validate runtime behavior. Focus on whether the script’s purpose and effect meaningfully contributed to detecting, reproducing, or demonstrating a vulnerability.

    Your task is twofold:
    1. **Evaluation**: Assess whether the script execution advanced the vulnerability hypothesis. Did it produce a fault, unexpected output, or internal program failure?
    2. **Alternative Feedback**: Recommend another exploit strategy or input transformation that could help trigger unsafe behavior or reveal the root cause.
    """

    @classmethod
    def get_evaluation_criteria(cls, trajectory_length: int | None = None) -> List[str]:
        if trajectory_length is not None and trajectory_length < 3:
            return [
                "Hypothesis Forming: Does the script attempt a plausible way to trigger an overflow or runtime failure?",
                "Automation Value: Is the script enabling new or large-scale input generation / testing?",
                "Compile or Execution Success: Did the script run correctly, even if the exploit did not trigger?",
            ]
        else:
            return [
                "Impactful Behavior: Did the script execution lead to a crash, corrupted output, or fault?",
                "Exploit Simulation: Was the action a meaningful simulation of real exploit attempts?",
                "Edge Case Targeting: Did the script try lengths, characters, or data layouts likely to induce memory issues?",
                "Avoidance of Duplication: Does this attempt differ materially from prior PoC attempts?",
            ]



