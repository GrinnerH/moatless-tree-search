import subprocess
import tempfile
import os
from typing import Dict, Optional, Union, Literal

import pexpect
import sys

class Debugger:
    def __init__(self):
        """Initialize GDB debugger for CTF analysis."""
        try:
            subprocess.run(['gdb', '--version'], capture_output=True, check=True)
            self.gdbcursor = pexpect.spawn('gdb --quiet')
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("GDB not found")

    def is_binary_by_extension(self,file_path)-> bool:
        TEXT_EXTENSIONS = {'.c', '.cpp', '.py', '.java', '.txt', '.h'}
        return os.path.splitext(file_path)[1].lower() not in TEXT_EXTENSIONS
    
    def _create_gdb_script(self, file: str, line: int, exprs: str) -> str:
        """Create GDB script focused on CTF-relevant information."""
        expressions = [e.strip() for e in exprs.split(',')]
        
        if self.is_binary_by_extension(file):
            break_cmd = f"break *{line}"  # 地址前加*
        else:
            break_cmd = f"break {line}"


        script = f"""
        set verbose off
        file {file}
        {break_cmd}
        run
        
        # Function layout
        printf "\\n=== FUNCTION LAYOUT ===\\n"
        x/20i $pc-8
        
        # Stack & heap info
        printf "\\n=== MEMORY LAYOUT ===\\n"
        #info proc mappings
        printf "\\nStack pointer: "
        print/x $sp
        printf "Base pointer: "
        print/x $bp
        
        # Register state
        printf "\\n=== REGISTERS ===\\n"
        info registers
        
        printf "\\n=== TARGET VARIABLES ===\\n"
        """

        # Add analysis for each requested variable/expression
        for expr in expressions:
            script += f"""
        printf "\\n{expr}:\\n"
        printf "  Address: "
        print/x &{expr}
        printf "  Value: "
        print {expr}
        printf "  Raw bytes: "
        x/32xb {expr}
        printf "  As string: "
        x/s {expr}
        """

        script += """
        # Check for common CTF gadgets
        printf "\\n=== USEFUL GADGETS ===\\n"
        find $pc,+1000,"/bin/sh"
        find $pc,+1000,"flag"
        find $pc,+1000,"system"
        
        # Look for writable sections
        printf "\\n=== WRITABLE SECTIONS ===\\n"
        maintenance info sections WRITABLE
        
        quit
        """
        
        fd, path = tempfile.mkstemp(suffix='.gdb')
        with os.fdopen(fd, 'w') as f:
            f.write(script)
        return path

    def _compile_with_protections(self, file: str, lang: Literal['c', 'cpp'] = 'cpp') -> str:
        """Compile with common CTF protections for testing.
        
        Args:
            file: Source file path
            lang: Language to use for compilation ('c' or 'cpp'). Defaults to 'cpp'.
        """
        output = os.path.splitext(file)[0]
        
        # Select compiler based on language
        compiler = 'g++' if lang == 'cpp' else 'gcc'
        # print(output)
        try:
            # Compile with standard CTF protections
            subprocess.run(
                [compiler, '-std=c++17', '-g', file, '-o', output,
                 '-fno-stack-protector',  # Disable stack canaries
                 '-z', 'execstack',       # Make stack executable
                 '-no-pie'],             # Disable PIE
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Compilation failed: {e.stderr}")
        return output

    def renew(self):
        """Renew GDB session."""
        if self.gdbcursor:
            self.gdbcursor.close()
        self.gdbcursor = pexpect.spawn('gdb --quiet')
        self.gdbcursor.before = None

    def execute_command(self, command):
        """使用pexpect方式执行GDB命令"""
        # 清除之前可能残留的输出
        while True:
            try:
                self.gdbcursor.read_nonblocking(size=4096, timeout=0.1)
            except:
                break
        # 发送命令
        self.gdbcursor.sendline(command)
        
        # 等待(gdb)提示符
        index = self.gdbcursor.expect([r'\(gdb\)', pexpect.TIMEOUT, pexpect.EOF], timeout=5)
        
        if index == 0:
            # 获取命令输出，去除命令本身和提示符
            output = self.gdbcursor.before.decode('utf-8', errors='ignore')
            # 移除发送的命令和命令行回显
            lines = output.split('\n')
            if len(lines) > 0 and command in lines[0]:
                output = '\n'.join(lines[1:])
            return output.strip()
        else:
            return "命令执行超时或遇到错误"

    
    def debug(self, executable_file: str, file: str, line: int, cmd: str, exprs: str) -> str:
        """Run CTF-focused debug analysis.
        
        Args:
            executable_file: Executable file path
            file: Source file path
            line: Line number to break at source file
            cmd: The content entered when the executable file is running
            exprs: Comma-separated expressions to examine
        Example:
            debugger.debug("/home/wjj/baby-naptime/wyl_test/test", "/home/wjj/baby-naptime/wyl_test/test.c" , 8 , "1212", "buffer, buffer[0]")
        """
        # self.gdbcursor.logfile_read=sys.stdout
        if executable_file is None:
            # 如果没有提供可执行文件路径，则尝试编译
            binary = self._compile_with_protections(file, cpp=True)  # 假设cpp为True
        elif not os.path.exists(executable_file):
            raise FileNotFoundError(f"File not found: {executable_file}")
        else:
            binary = executable_file

        gdb_session = ""
        self.execute_command("set pagination off")
        # 启动 gdb 并加载可执行文件
        gdb_cmd = f"file {binary} "
        gdb_session += gdb_cmd + "\n"
        self.execute_command(gdb_cmd)

        file = os.path.abspath(file)
        # 设置断点
        breakpoint_cmd = f"break {file}:{line}"
        gdb_session += breakpoint_cmd + "\n"
        self.execute_command(breakpoint_cmd)
        # 运行程序
        if cmd:
            if isinstance(cmd, bytes):
                # 如果是 bytes 类型，使用 bytes.replace()
                cmd = cmd.replace(b",", b"\n")  # 将逗号替换为换行符
                cmd = cmd.replace(b" ", b"")    # 删除空格
                with open("./temp.txt", "wb") as f:
                    f.write(cmd)
        
            elif isinstance(cmd, str):
                # 如果是 str 类型，使用 str.replace()
                cmd = cmd.replace(",", "\n")  # 将逗号替换为换行符
                cmd = cmd.replace(" ", "")    # 删除空格
                with open("./temp.txt", "w") as f:
                    f.write(cmd)
        
            gdb_session += self.execute_command("run < temp.txt")

            # 删除临时文件
            os.remove("temp.txt")
            

        else:
            gdb_session += "Please input the command you want to run"
            self.gdbcursor = pexpect.spawn('gdb --quiet')
            return gdb_session
    
        if "Breakpoint" not in gdb_session:
            gdb_session += "!!!!!Error: Breakpoint not hit !!!!!"
            self.gdbcursor = pexpect.spawn('gdb --quiet')
            return gdb_session

        # 打印表达式
        for expr in exprs.split(","):
            expr = expr.strip()
            if expr:
                gdb_session += f"print {expr}" + "\n"
                gdb_session += self.execute_command(f"print {expr}")
        
        self.gdbcursor = pexpect.spawn('gdb --quiet')
        gdb_session = gdb_session.replace("\r\n\r\n", "\r\n")
        gdb_session += "=====External note: The above is the output you need. ====="
        return gdb_session


if __name__ == "__main__":
    debugger = Debugger()
    # de=debugger.debug("/home/wjj/baby-naptime/wyl_test/test", "/home/wjj/baby-naptime/wyl_test/test.c" , 14 , 'A'*40,  "buffer1, buffer1[0]")
    # print(de)  # 输出前500字符'
    # de=debugger.debug("/home/wjj/baby-naptime/wyl_test/test", "/home/wjj/baby-naptime/wyl_test/test.c" , 14 , "3, 4, 5", "buffer3, buffer3[0]")
    # print(de)  # 输出前500字符'
    # de = debugger.debug('./code/test2', './code/test2.cpp', 125, program_input , 'buffer1,buffer2')
    # print(de)  # 输出前500字符'
