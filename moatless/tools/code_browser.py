# tools/code_browser.py

from clang.cindex import Index, CursorKind
import os
from typing import Dict
# from logger import logger
from colorama import Fore, Style

class CodeBrowser:
    def __del__(self):
        self.index = None

    def __init__(self):
        """Initialize CodeBrowser."""
        self.index = Index.create()

    def get_class_body(self, filename: str, class_name: str) -> Dict:
        if not os.path.exists(filename):
            raise FileNotFoundError(f"File not found: {filename}")

        tu = self.index.parse(filename, args=['-x', 'c++'])
        if not tu:
            raise ValueError(f"Failed to parse {filename}")

        class_node = None
        for node in tu.cursor.walk_preorder():
            if node.kind == CursorKind.CLASS_DECL and node.spelling == class_name:
                class_node = node
                break

        if not class_node:
            raise ValueError(f"Class '{class_name}' not found in {filename}")

        start = class_node.extent.start
        end = class_node.extent.end

        with open(filename, 'r') as f:
            print(f"[CodeBrowser] Reading lines from class file: {filename}")
            file_lines = f.readlines()

        class_lines = file_lines[start.line-1:end.line]
        numbered_lines = [
            f"{i+start.line}: {line.rstrip()}" for i, line in enumerate(class_lines)
        ]

        return {
            'filename': filename,
            'name': class_name,
            'type': 'class',
            'source': '\n'.join(numbered_lines),
            'lines': [line.strip() for line in class_lines if line.strip()]
        }

    def get_function_body(self, filename: str, function_name: str) -> Dict:
        
        if not filename.endswith(('.c', '.cpp', '.h')):
            raise ValueError("Only .c, .cpp and .h files are supported")

        if not os.path.exists(filename):
            print(f"[CodeBrowser] File not found: {filename}")
            raise FileNotFoundError(f"File not found: {filename}")

        if filename.endswith('.h'):
            with open(filename, 'r') as f:
                file_lines = f.readlines()
            numbered_lines = [
                f"{i+1}: {line.rstrip()}" for i, line in enumerate(file_lines)
            ]
            return {
                'filename': filename,
                'name': function_name,
                'type': 'header',
                'source': '\n'.join(numbered_lines),
                'lines': [line.strip() for line in file_lines if line.strip()]
            }

        tu = self.index.parse(filename)
        if not tu:
            raise ValueError(f"Failed to parse {filename}")

        function_node = None
        for node in tu.cursor.walk_preorder():
            if node.kind in [CursorKind.FUNCTION_DECL, CursorKind.CXX_METHOD] and node.spelling == function_name:
                function_node = node
                break

        if not function_node:
            try:
                return self.get_class_body(filename, function_name)
            except ValueError:
                # logger.info(f"{Fore.RED}***Tool Warning***: Function '{function_name}' not found in {filename}.{Style.RESET_ALL}")
                raise ValueError(f"Function '{function_name}' not found in {filename}.")

        start = function_node.extent.start
        end = function_node.extent.end

        with open(filename, 'r') as f:
            print(f"[CodeBrowser] Opening file: {filename}")
            file_lines = f.readlines()

        function_lines = file_lines[start.line-1:end.line]
        numbered_lines = [
            f"{i+start.line}: {line.rstrip()}" for i, line in enumerate(function_lines)
        ]

        return {
            'filename': filename,
            'name': function_name,
            'type': 'function',
            'source': '\n'.join(numbered_lines),
            'lines': [line.strip() for line in function_lines if line.strip()]
        }

    def code_browser_source(self, file: str, name: str) -> str:
        try:
            details = self.get_function_body(file, name)
            return details['source']
        except (ValueError, FileNotFoundError) as e:
            return str(e)
