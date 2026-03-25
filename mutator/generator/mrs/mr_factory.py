from .mr import MetamorphicRelation
from .mr_data import MRData
from .mr_state import MRState
from .mr_cancel import MRCancel

from transition_graph import GraphManager

class MRFactory:
    @staticmethod
    def create_mr(mr_type: str, graph_mgr: GraphManager, config: dict = None) -> MetamorphicRelation:
        config = config or {}
        if mr_type == "MRData":
            return MRData(graph_mgr=graph_mgr, config=config)
        elif mr_type == "MRState":
            return MRState(graph_mgr=graph_mgr, config=config)
        elif mr_type == "MRCancel":
            return MRCancel(graph_mgr=graph_mgr, config=config)
        else:
            raise ValueError(f"Unknown MR type: {mr_type}")
    