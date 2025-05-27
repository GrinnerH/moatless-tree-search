# demo.py
import os
from moatless.repository.file import FileRepository
from moatless.file_context import FileContext
from moatless.index import CodeIndex
from moatless.runtime.testbed import TestbedEnvironment
from testbeds.sdk import TestbedSDK
from moatless.search_tree import SearchTree
from moatless.completion import CompletionModel
from moatless.feedback import FeedbackGenerator
from moatless.feedback.reward_feedback import RewardFeedbackGenerator

from moatless.index.settings import IndexSettings
from moatless.index.code_index import default_vector_store
from llama_index.core.storage.docstore import SimpleDocumentStore

from moatless.agent.vuln_agent import create_vuln_agent
# from moatless.value_function.vuln_value import VulnRewardFunction
from moatless.value_function.base import ValueFunction
from moatless.selector import VulnPathSelector 
from dotenv import load_dotenv
load_dotenv()
print("加载任务描述")
# === 自定义任务描述 ===
task = '''

int main(int argc, char* argv[]) {

  std::istream* input;

  std::ifstream file;

  if (argc < 2) {

    input = &std::cin; // No file name provided, read from stdin

  } else {

    file.open(argv[1]);

    if (!file) {

      std::cerr << "Could not open the file.\n";

      return 1;

    }

    input = &file; // File opened successfully, read from file

  }

  string content(

      (std::istreambuf_iterator<char>(*input)),

      std::istreambuf_iterator<char>());

    Reader reader(content);

    SE_TARGET_STATE(!parse_content(reader));

  return 0;

}

'''

task_spec = {
    "message": task,
    "repo_path": "tmp/index_store",    # 修改为你的真实代码路径
    "target_file": "test3.cpp",                     # 要操作的目标源文件
    "trigger_keywords": ["OverflowTriggered", "success"],  # 判断是否触发漏洞的关键词
}

input_message=f"""
任务目标：
你将分析以下代码并验证其中存在的漏洞：
The use of strcpy to copy content into buffer1 (line 70) without bounds checking is the principal vulnerability. If content has more than 32 characters, it will overflow buffer1 and can overwrite adjacent memory, which includes buffer2. This typical buffer overflow security issue could be exploited to control adjacent memory, corrupt buffer2, and potentially alter program behavior or crash the program.

[源代码文件]: {task_spec["target_file"]}
[触发关键词]: {', '.join(task_spec["trigger_keywords"])}

=== 源代码内容 ===
{task_spec["message"]}
"""


# === 初始化基础组件 ===
print("🔧 加载代码仓库与上下文 ...")
repository = FileRepository(repo_path=task_spec["repo_path"])
file_context = FileContext(repo=repository)

# 若你需要使用基于索引的动作，可启用索引
index_settings = IndexSettings()
vector_store = default_vector_store(index_settings)
docstore = SimpleDocumentStore()

code_index = CodeIndex(
    file_repo=repository,
    vector_store=vector_store,
    docstore=docstore,
    settings=index_settings,
)

# print("⚙️ 正在构建索引 (run_ingestion)...")
# indexed_nodes, tokens = code_index.run_ingestion(
#     repo_path="tmp/index_store",  # 你的代码路径
#     input_files=["test2.cpp"],    # 要索引的目标文件
# )
# print(f"✅ 索引完成，共 {indexed_nodes} 个代码块，{tokens} tokens")
# code_index.persist("tmp/repos")
code_index = CodeIndex.from_persist_dir(
    persist_dir="tmp/repos",
    file_repo=repository
)


# runtime = TestbedEnvironment(
#     repository=repository,
#     testbed_sdk=TestbedSDK(),
#     instance={"instance_id": "demo"},
#     log_dir="./logs"
# )


# === 初始化 Completion Model（兼容 Azure OpenAI） ===
print("📦 初始化模型 ...")
completion_model = CompletionModel(
    model="azure/gpt-4o",
    model_base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
    model_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    temperature=0.4,
    metadata={"azure_deployment_id": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")},
    mode="tool", 
)

# === 构建 Agent 与 reward 评估器 ===
agent = create_vuln_agent(repository, code_index, completion_model)
# print("🧪 Registered actions:")
# for action in agent.actions:
#     print(f" - {action.name}: {action.args_schema}, bases={action.args_schema.__bases__}")


value_function = ValueFunction(completion_model=completion_model)

selector = VulnPathSelector(
    use_average_reward=False,
    exploitation_weight=1.0,
    exploration_weight=1.0,
)

# === 创建 Search Tree ===
print("🌲 创建搜索树...")
search_tree = SearchTree.create(
    message=input_message,
    agent=agent,
    file_context=file_context,
    selector=selector,
    value_function=value_function,
    feedback_generator=RewardFeedbackGenerator(),
    max_iterations=20,
    max_expansions=5,
    max_depth=10,
    persist_path="trajectory.json",
)

# print(f"树结构：\n {search_tree}")
print("🔍 启动搜索... ")
# === 启动搜索过程 ===
final_node = search_tree.run_search()

# === 输出结果 ===
print("\n🧾 最终搜索结果：")
if final_node and final_node.observation:
    print("流程正常执行:", final_node.observation.message)
else:
    print("❌ 未能成功触发漏洞")

from pprint import pprint

# print("\n🧾 最终节点结构预览：\n")
# if final_node:
#   from pprint import pprint
#   pprint(final_node.model_dump(), depth=None, width=200)


