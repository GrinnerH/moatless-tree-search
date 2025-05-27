# 放在 scripter.py 顶部
from moatless.completion.model import StructuredOutput
from pydantic import Field

class PythonCodeOutput(StructuredOutput):
    code: str = Field(..., description="格式化后的可运行 Python 脚本")
    def __str__(self):
        return self.code


# scripter.py
import subprocess
import tempfile
import os
import re
import json
from typing import Optional
from moatless.completion import CompletionModel
from moatless.completion.model import Completion
from pydantic import ValidationError

class ScriptRunner:
    def __init__(self, completion_model: CompletionModel, temp_dir: str = "temp"):
        self.completion_model = completion_model
        self.temp_dir = temp_dir

    def run_script(
        self,
        file_path: str,
        script_code: str,
        timeout: Optional[int] = 30
    ) -> str:
        # print(f"[Script Code]:\n{script_code}")

        base_filename = os.path.splitext(os.path.basename(file_path))[0]
        sub_dir = os.path.join(self.temp_dir, base_filename)
        os.makedirs(sub_dir, exist_ok=True)

        prompt = f"""
        Take this Python code, and fix any indentation or obvious syntax bugs.
        Do not change the logic.
        Return only revised code in raw form, without explanation or markdown code blocks.

        Code:
        {script_code}
        """.strip()

        # 💡 Equivalent to baby-naptime LLM(prompt)
        try:
            response = self.completion_model.create_completion(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a Python code fixer. Return raw code only.",
                response_model=PythonCodeOutput  # ✅ 正确方式
            )
            fixed_code = response.structured_output.code.strip()
            fixed_code = re.sub(r"```(?:python|json)?", "", fixed_code).strip()

        except Exception as e:
            print("[WARNING] Failed to clean script, running raw.")
            print(f"[DEBUG] Error: {e}")
            fixed_code = script_code

            #/wwh edit

        fd, script_path = tempfile.mkstemp(suffix='.py', dir=sub_dir)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(fixed_code)

            result = subprocess.run(
                ['python3', script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )

            return (
                f"[Script OK]\n{fixed_code}\n\n"
                f"[STDOUT]\n{result.stdout.strip()}\n"
                f"[STDERR]\n{result.stderr.strip()}"
            )

        except subprocess.CalledProcessError as e:
            return (
                f"[Script FAIL]\n{fixed_code}\n\n"
                f"[COMMAND]: {e.cmd}\n"
                f"[RC]: {e.returncode}\n"
                f"[STDOUT]:\n{e.stdout}\n"
                f"[STDERR]:\n{e.stderr}"
            )

        except Exception as e:
            return f"[UNEXPECTED ERROR] {type(e).__name__}: {str(e)}"
