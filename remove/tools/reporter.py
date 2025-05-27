import os
import json
from llm import LLM
from pathlib import Path
from prompts.report import Reporter_PROMPT

class Reporter:

    def __init__(self, filename):
        """
        Initialize the reporter.

        Args:
            filename: Filename of the file that was tested
        """
        self.llm = LLM("o4-mini")
        self.reports = []
        self.filename = filename
        
    def generate_summary_report(self, history):

        system_prompt = [{"role": "system", "content": Reporter_PROMPT}]
        messages = []
        for item in history:
            messages.append({"role": item["role"], "content": item["content"]})
        summary = self.llm.action(system_prompt + messages)
        base = os.path.splitext(os.path.basename(self.filename))[0]
        os.makedirs("results", exist_ok=True)
        with open(f"results/{base}_summary.md", "w") as f:
            f.write(summary)