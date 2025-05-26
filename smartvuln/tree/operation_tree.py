from moatless.search_tree import SearchTree
from moatless.node import Node
from moatless.selector import BestFirstSelector
from moatless.expander import Expander

from smartvuln.value.reward import VulnRewardFunction
from smartvuln.feedback.subtree_feedback import SubtreeFeedbackGenerator

class OperationTree(SearchTree):
    @classmethod
    def create(cls, message, agent, file_context=None):
        root = Node(node_id=0, message=message, max_expansions=2, file_context=file_context)

        return cls(
            root=root,
            selector=BestFirstSelector(),
            expander=Expander(max_expansions=2),
            agent=agent,
            value_function=VulnRewardFunction(),
            feedback_generator=SubtreeFeedbackGenerator(),
            max_iterations=5,
            max_depth=5,
        )
