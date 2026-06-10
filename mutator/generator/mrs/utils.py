"""
Utility functions and data structures for Metamorphic Relations.

This module provides reusable path manipulation, graph traversal, and validation
utilities for all MR implementations.

Contents:
- Data
- Path Analysis Utilities
- Path Construction Utilities
- Path Filtering and Validation
- Path Discovery and Search Algorithms
"""

from typing import List, Tuple, Optional, Union, Set, Dict, Any
from dataclasses import dataclass
from collections import deque, Counter

import numpy as np
from transition_graph import AbstractStateNode, StateNode, InternalStateNode, AbstractEvent, PageNode, GraphManager, ScriptPath, PathNode, InternalPathNode

try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore
    _SENTENCE_TRANSFORMERS_AVAILABLE = False

# Data
@dataclass
class PathSearchConfig:
    """Configuration for path discovery algorithms."""
    max_depth: int = 30
    allow_cycles: bool = True
    page_constraints: Optional[List[PageNode]] = None
    max_results: int = 40
    prefer_shorter_paths: bool = False
    max_repeat_per_page: int = 2


# Path Analysis Utilities

def extract_page_sequence(script_path: ScriptPath) -> List[PageNode]:
    """
    Extract the sequence of pages traversed by a script path.
    
    Args:
        script_path: The script path to analyze
        
    Returns:
        List of page nodes in traversal order
    """
    from transition_graph import StateNode
    
    if script_path.start_path_node is None:
        return []
    
    pages = []
    current_node = script_path.start_path_node
    
    while current_node is not None:
        # Only consider regular StateNode, not InternalStateNode
        if isinstance(current_node.state, StateNode):
            page = current_node.state.parent_page_node
            # Add page if it's different from the last one
            if not pages or pages[-1] != page:
                pages.append(page)
        
        current_node = current_node.next_path_node
    
    return pages


def extract_state_sequence(script_path: ScriptPath) -> List[AbstractStateNode]:
    """
    Extract the sequence of states in a script path.
    
    Args:
        script_path: The script path to analyze
        
    Returns:
        List of states in traversal order (including internal states)
    """
    if script_path.start_path_node is None:
        return []
    
    states = []
    current_node = script_path.start_path_node
    
    while current_node is not None:
        states.append(current_node.state)
        current_node = current_node.next_path_node
    
    return states


def identify_border_states(
    script_path: ScriptPath,
    start_page: PageNode,
    end_page: PageNode
) -> Tuple[Optional[StateNode], Optional[StateNode]]:
    """
    Identify entry and exit states for a page segment.
    
    Args:
        script_path: The script path to analyze
        start_page: The starting page of the segment
        end_page: The ending page of the segment
        
    Returns:
        Tuple of (entry_state, exit_state), or (None, None) if not found
    """
    from transition_graph import StateNode
    
    states = extract_state_sequence(script_path)
    entry_state = None
    exit_state = None
    in_segment = False
    
    for state in states:
        if isinstance(state, StateNode):
            if state.parent_page_node == start_page and not in_segment:
                entry_state = state
                in_segment = True
            
            if state.parent_page_node == end_page and in_segment:
                exit_state = state
    
    return entry_state, exit_state


def get_all_border_states_for_path(
    script_path: ScriptPath,
) -> List[Tuple[PageNode, PageNode, StateNode, StateNode]]:
    """
    For the whole path, get a list of `(exit_state, entry_state)` pairs for every adjacent
    semantic page pair `(p_k, p_{k+1})`.
    Intended for MR-State (and similar MRs) to inject a subpath between two neighboring pages.

    Returns:
        List of (page_k, page_k_plus_1, exit_state_from_p_k, entry_state_to_p_k_plus_1)
    """
    from transition_graph import StateNode

    pages = extract_page_sequence(script_path)
    if len(pages) < 2:
        return []

    result = []
    states = extract_state_sequence(script_path)
    # For each `(p_k, p_{k+1})`, find the last state belonging to `p_k` and the first state
    # belonging to `p_{k+1}`.
    for k in range(len(pages) - 1):
        p_k = pages[k]
        p_next = pages[k + 1]
        exit_s = None
        entry_s = None
        seen_exit = False
        for state in states:
            if not isinstance(state, StateNode):
                continue
            if state.parent_page_node == p_k:
                exit_s = state
                seen_exit = True
            elif state.parent_page_node == p_next and seen_exit:
                entry_s = state
                break
        if exit_s is not None and entry_s is not None:
            result.append((p_k, p_next, exit_s, entry_s))
    return result

def extract_event_sequence(script_path: ScriptPath) -> List[AbstractEvent]:
    """
    Extract the sequence of events in a script path.
    
    Args:
        script_path: The script path to analyze
        
    Returns:
        List of events in traversal order
    """
    if script_path.start_path_node is None:
        return []
    
    events = []
    current_node = script_path.start_path_node
    
    while current_node is not None:
        events.append(current_node.event)
        current_node = current_node.next_path_node
    
    return events

# Path Construction Utilities

def build_script_path_from_states(
    states: List[AbstractStateNode],
    events: List[AbstractEvent]
) -> ScriptPath:
    """
    Construct ScriptPath from state and event sequences.
    
    Args:
        states: Sequential states in the path
        events: Events triggering transitions (length = len(states) - 1 or len(states))
        
    Returns:
        Constructed ScriptPath object
    """
    from transition_graph import ScriptPath
    
    if not states:
        return ScriptPath()
    
    path = ScriptPath()
    
    for i, state in enumerate(states):
        # Get corresponding event (or None for last state)
        event = events[i] if i < len(events) else None
        
        # Create appropriate path node
        path_node = create_path_node(state, event)
        path.add_path_node(path_node)
    
    return path


def create_path_node(
    state: AbstractStateNode,
    event: Optional[AbstractEvent]
) -> Union[PathNode, InternalPathNode]:
    """
    Create appropriate path node type based on state type.
    
    Args:
        state: The state node
        event: The event triggering transition from this state
        
    Returns:
        PathNode for regular states, InternalPathNode for internal states
    """
    
    if isinstance(state, InternalStateNode):
        return InternalPathNode(state, event)
    elif isinstance(state, StateNode):
        return PathNode(state, event)
    else:
        raise ValueError(f"Unknown state type: {type(state)}")


def concatenate_path_segments(
    prefix: Optional[ScriptPath],
    middle: Optional[ScriptPath],
    suffix: Optional[ScriptPath]
) -> ScriptPath:
    """
    Merge multiple path segments into one.
    
    Args:
        prefix: Path segment before the middle
        middle: Path segment to insert
        suffix: Path segment after the middle
        
    Returns:
        Combined ScriptPath
    """
    from transition_graph import ScriptPath
    
    # Convert to arrays for easier manipulation
    prefix_array = prefix.to_array() if prefix and prefix.start_path_node else []
    middle_array = middle.to_array() if middle and middle.start_path_node else []
    suffix_array = suffix.to_array() if suffix and suffix.start_path_node else []
    
    # Combine arrays
    combined = prefix_array + middle_array + suffix_array
    
    # Build new path
    return ScriptPath(path_array=combined) if combined else ScriptPath()


def clone_path_segment(
    script_path: ScriptPath,
    start_index: int,
    end_index: int
) -> ScriptPath:
    """
    Extract and clone a portion of a path.
    
    Args:
        script_path: The source path
        start_index: Starting index (inclusive)
        end_index: Ending index (inclusive)
        
    Returns:
        Cloned path segment
    """
    from transition_graph import ScriptPath
    
    path_array = script_path.to_array()
    
    if start_index < 0 or end_index >= len(path_array) or start_index > end_index:
        return ScriptPath()
    
    segment_array = path_array[start_index:end_index + 1]
    return ScriptPath(path_array=segment_array)


def clone_script_path(script_path: ScriptPath) -> ScriptPath:
    """
    Deep-copy a script path (create new `PathNode` instances; `state`/`event` still reference
    objects from the graph).

    Used when an MR (e.g., MR-Data) needs to "copy a path and replace the `event` at a node".
    """
    if script_path.start_path_node is None:
        return ScriptPath()
    return ScriptPath(path_array=script_path.to_array())

# Graph Query Utilities

def get_states_in_page(page_node: PageNode) -> List[StateNode]:
    """
    Retrieve all states belonging to a page.
    
    Args:
        page_node: The page node
        
    Returns:
        List of state nodes in the page
    """
    return page_node.state_nodes.copy()


def get_transition_event(
    source_state: AbstractStateNode,
    target_state: AbstractStateNode
) -> Optional[AbstractEvent]:
    """
    Get the event that triggers a specific transition.
    
    Args:
        source_state: The source state
        target_state: The target state
        
    Returns:
        The event triggering the transition, or None if no direct transition exists
    """
    from transition_graph import InternalStateNode
    
    # Check direct transitions
    for event, next_state in source_state.transitions.items():
        if next_state == target_state:
            return event
        
        # Check through internal state
        if isinstance(next_state, InternalStateNode):
            for internal_event, internal_target in next_state.transitions.items():
                if internal_target == target_state:
                    return event
    
    return None


def resolve_internal_transitions(
    state: AbstractStateNode,
    event: AbstractEvent
) -> List[AbstractStateNode]:
    """
    Handle internal state nodes and return all possible target states.
    
    Args:
        state: The source state
        event: The event to trigger
        
    Returns:
        List of all possible target states (handling internal state branching)
    """
    from transition_graph import InternalStateNode
    
    if event not in state.transitions:
        return []
    
    target = state.transitions[event]
    
    # If target is internal state, get all its targets
    if isinstance(target, InternalStateNode):
        targets = []
        for internal_event, internal_target in target.transitions.items():
            targets.append(internal_target)
        return targets
    else:
        return [target]


def get_reachable_pages_from_state(state: StateNode) -> List[PageNode]:
    """
    Find all pages reachable from a given state.
    
    Args:
        state: The source state
        
    Returns:
        List of reachable page nodes
    """
    from transition_graph import InternalStateNode, StateNode
    
    reachable_pages = set()
    
    for event, target in state.transitions.items():
        if isinstance(target, InternalStateNode):
            # Check internal state's targets
            for internal_event, internal_target in target.transitions.items():
                if isinstance(internal_target, StateNode):
                    reachable_pages.add(internal_target.parent_page_node)
        elif isinstance(target, StateNode):
            reachable_pages.add(target.parent_page_node)
    
    return list(reachable_pages)


# Local subgraph for MR-State (state-level BFS, reverse BFS, candidate subgraph)

def get_successor_edges(state: AbstractStateNode) -> List[Tuple[AbstractEvent, AbstractStateNode]]:
    """
    Get all outgoing edges from the current state (expand `InternalStateNode`) and return a list
    of `(event, target_state)` pairs.
    """
    result: List[Tuple[AbstractEvent, AbstractStateNode]] = []
    for event, target in state.transitions.items():
        if isinstance(target, InternalStateNode):
            for _, tgt in target.transitions.items():
                result.append((event, tgt))
        else:
            result.append((event, target))
    return result


def get_all_states_in_graph(graph_mgr: GraphManager) -> List[AbstractStateNode]:
    """Return all state nodes in the graph (including `InternalStateNode`)."""
    states: List[AbstractStateNode] = []
    for page in graph_mgr.currentGraph.page_nodes:
        states.extend(page.state_nodes)
    states.extend(graph_mgr.currentGraph.internal_state_nodes)
    return states


def get_predecessor_edges(
    state: AbstractStateNode,
    graph_mgr: GraphManager,
) -> List[Tuple[AbstractStateNode, AbstractEvent]]:
    """Return all `(source_state, event)` pairs that can reach the given `state`."""
    result: List[Tuple[AbstractStateNode, AbstractEvent]] = []
    for s in get_all_states_in_graph(graph_mgr):
        if not hasattr(s, "transitions"):
            continue
        for event, target in s.transitions.items():
            if target == state:
                result.append((s, event))
            elif isinstance(target, InternalStateNode):
                for _, tgt in target.transitions.items():
                    if tgt == state:
                        result.append((s, event))
                        break
    return result


def _bfs_forward_impl(
    start_state: AbstractStateNode,
    max_depth: int,
    all_states_by_id: Dict[int, AbstractStateNode],
) -> Set[AbstractStateNode]:
    """Run BFS from `start_state` and return the reachable state set.

    `all_states_by_id` is used for the `id -> node` mapping.
    """
    visited: Set[int] = set()
    visited.add(start_state.id)
    queue: deque = deque([(start_state, 0)])
    while queue:
        cur, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for _event, tgt in get_successor_edges(cur):
            if tgt.id not in visited:
                visited.add(tgt.id)
                queue.append((tgt, depth + 1))
    return set(all_states_by_id[i] for i in visited if i in all_states_by_id)


def bfs_forward(
    start_state: AbstractStateNode,
    graph_mgr: GraphManager,
    max_depth: int,
) -> Set[AbstractStateNode]:
    """Run BFS from `start_state` with depth limit `max_depth` and return the reachable set."""
    all_states = get_all_states_in_graph(graph_mgr)
    by_id = {s.id: s for s in all_states}
    return _bfs_forward_impl(start_state, max_depth, by_id)


def bfs_reverse(
    end_state: AbstractStateNode,
    graph_mgr: GraphManager,
    max_depth: int,
) -> Set[AbstractStateNode]:
    """Run reverse-edge BFS from `end_state` and return the set of states that can reach it."""
    all_states = get_all_states_in_graph(graph_mgr)
    by_id = {s.id: s for s in all_states}
    visited: Set[int] = set()
    visited.add(end_state.id)
    queue: deque = deque([(end_state, 0)])
    while queue:
        cur, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for src, _event in get_predecessor_edges(cur, graph_mgr):
            if src.id not in visited:
                visited.add(src.id)
                queue.append((src, depth + 1))
    return set(by_id[i] for i in visited if i in by_id)


# ---------- Path-level Local Subgraph Extraction (connected, focused) ----------

# A path is a list of edges: `[(src, event, tgt), ...]`.
PathEdges = List[Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]]

# Preset core-business intent description, used for cosine-similarity scoring against edge semantics.
TEXT_TARGET = "Complete purchase process, submit form data, add core business content, successful login/registration"

def _edge_key(src: AbstractStateNode, event: AbstractEvent, tgt: AbstractStateNode) -> Tuple[int, int, str]:
    """A unique key for an edge, used for de-duplication and set operations."""
    label = getattr(event, "semantic_label", None) or ""
    return (src.id, tgt.id, label)


def _find_all_paths(
    start_node: AbstractStateNode,
    end_node: AbstractStateNode,
    max_depth: int,
    current_edges: PathEdges,
    visited_edges: Set[Tuple[int, int, str]],
    result: List[PathEdges],
) -> None:
    """
    Enumerate all simple paths from `start_node` to `end_node` via a depth-limited DFS (do not
    reuse the same edge within a single path). Depth is bounded by `max_depth`.

    Append the results to `result`.
    """
    if len(current_edges) >= max_depth:
        return
    current = start_node if not current_edges else current_edges[-1][2]
    if current.id == end_node.id and current_edges:
        result.append(list(current_edges))
        return
    for event, tgt in get_successor_edges(current):
        # if not getattr(event, "semantic_label", None) or getattr(event, "semantic_label", "") == "":
        #     continue
        key = _edge_key(current, event, tgt)
        if key in visited_edges:
            continue
        visited_edges.add(key)
        current_edges.append((current, event, tgt))
        _find_all_paths(start_node, end_node, max_depth, current_edges, visited_edges, result)
        current_edges.pop()
        visited_edges.discard(key)


def find_all_paths(
    graph_mgr: GraphManager,
    start_node: AbstractStateNode,
    end_node: AbstractStateNode,
    max_depth: int,
) -> List[PathEdges]:
    """
    Depth-limited DFS to find all paths from `start_node` to `end_node` (no repeated edges
    within a path).
    Only keep edges that have `semantic_label`.
    """
    if start_node.id == end_node.id:
        return [[]]
    result: List[PathEdges] = []
    _find_all_paths(start_node, end_node, max_depth, [], set(), result)
    return result


def get_edges_from_path(path: PathEdges) -> Dict[Tuple[int, int, str], Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]]:
    """From one path, build the mapping `edge_key -> (src, event, tgt)` (de-duplicated)."""
    out: Dict[Tuple[int, int, str], Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]] = {}
    for src, event, tgt in path:
        k = _edge_key(src, event, tgt)
        if k not in out:
            out[k] = (src, event, tgt)
    return out


def get_unique_edges_from_paths(paths: List[PathEdges]) -> Dict[Tuple[int, int, str], Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]]:
    """Merge and de-duplicate edges across multiple paths:
    `edge_key -> (src, event, tgt)`.
    """
    out: Dict[Tuple[int, int, str], Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]] = {}
    for path in paths:
        for k, edge in get_edges_from_path(path).items():
            if k not in out:
                out[k] = edge
    return out

def _download_and_save_model() -> SentenceTransformer:
    import os

    model = None
    model_cache_dir = os.path.join(os.path.dirname(__file__), '.models_cache')
    model_name = 'all-MiniLM-L6-v2'

    local_path = os.path.join(model_cache_dir, model_name)

    if not os.path.exists(model_cache_dir):
        print("Downloading and saving model...")
        os.makedirs(model_cache_dir, exist_ok=True)
        model = SentenceTransformer(model_name)
        model.save(local_path)
        print(f"Model saved to: {local_path}")
    else:
        print("Loading model from cache...")
        model = SentenceTransformer(local_path)
    if model is None:
        raise ValueError("Failed to download and save model")
    
    return model

def _load_semantic_model(graph_mgr: GraphManager) -> bool:
    """Load SentenceTransformer embeddings for `TEXT_TARGET` to compute semantic weights.
    Store them in `graph_mgr` for thread safety.
    """
    if not _SENTENCE_TRANSFORMERS_AVAILABLE or SentenceTransformer is None:
        return False
    if graph_mgr._semantic_model is None:
        try:
            graph_mgr._semantic_model = _download_and_save_model()
        except Exception as e:
            print(f"Error downloading and saving model: {e}")
            return False
    if graph_mgr._semantic_target_embedding is None:
        graph_mgr._semantic_target_embedding = graph_mgr._semantic_model.encode(TEXT_TARGET, normalize_embeddings=True)
    return True


def _similarity_to_weight(sim: float) -> float:
    """Linearly map cosine similarity from `[-1, 1]` to a weight in `[1, 10]`."""
    sim = max(-1.0, min(1.0, float(sim)))
    return 1.0 + (sim + 1.0) / 2.0 * 9.0


def _ensure_semantic_embedding_cache(graph_mgr: GraphManager) -> None:
    """
    When the graph is first used (or on first cache build), convert every edge's `semantic_label`
    into an embedding, compute its cosine similarity to `TEXT_TARGET`, map the similarity to
    weights in `[1, 10]`, and store them in `graph_mgr`'s cache.
    """
    if not _load_semantic_model(graph_mgr):
        return
    cache = graph_mgr._semantic_label_to_weight
    all_states = get_all_states_in_graph(graph_mgr)
    labels: Set[str] = set()
    for state in all_states:
        for event, _tgt in get_successor_edges(state):
            lab = (getattr(event, "semantic_label", None) or "").strip()
            if lab:
                labels.add(lab)
    new_labels = [l for l in labels if l not in cache]
    if not new_labels:
        return
    embeddings = graph_mgr._semantic_model.encode(new_labels, normalize_embeddings=True)
    target = graph_mgr._semantic_target_embedding
    if hasattr(target, "reshape"):
        target = np.asarray(target).flatten()
    for label, emb in zip(new_labels, embeddings):
        e = np.asarray(emb).flatten()
        sim = float(np.dot(target, e))
        cache[label] = _similarity_to_weight(sim)


def _compute_edge_semantic_weight(event: AbstractEvent, graph_mgr: GraphManager) -> float:
    """
    Semantic action weight `W_semantic`: cosine similarity between an edge's semantic label and
    the preset core-business intent `TEXT_TARGET`, mapped to `[1, 10]`.

    Relies on `_ensure_semantic_embedding_cache` being called for the current graph; if
    `sentence_transformers` isn't available or the label isn't cached, return `1.0`.
    Uses `graph_mgr` internal caching (thread-safe).
    """
    label = (getattr(event, "semantic_label", None) or "").strip()
    if not label:
        return 1.0
    cache = graph_mgr._semantic_label_to_weight
    if label in cache:
        return cache[label]
    if _load_semantic_model(graph_mgr):
        emb = graph_mgr._semantic_model.encode([label], normalize_embeddings=True)
        e = np.asarray(emb[0]).flatten()
        target = np.asarray(graph_mgr._semantic_target_embedding).flatten()
        sim = float(np.dot(target, e))
        w = _similarity_to_weight(sim)
        cache[label] = w
        return w
    return 1.0


def _compute_edge_data_weight(src: AbstractStateNode, tgt: AbstractStateNode) -> float:
    """
    Data-increment weight `W_data`: return a high score if key data fields differ between the
    source and target states; otherwise return `0`.
    """
    src_entities = getattr(src, "data_entities", None) or []
    tgt_entities = getattr(tgt, "data_entities", None) or []
    src_map = {getattr(de, "key", ""): getattr(de, "value", "") for de in src_entities if getattr(de, "key", None)}
    tgt_map = {getattr(de, "key", ""): getattr(de, "value", "") for de in tgt_entities if getattr(de, "key", None)}
    for k in set(src_map) | set(tgt_map):
        if src_map.get(k) != tgt_map.get(k):
            return 10.0
    return 0.0


def calculate_path_score(graph_mgr: GraphManager, path: PathEdges) -> float:
    """
    Overall path score `S_path = (1/|P|) * sum_{e in P} (W_semantic(e) + W_data(e))`.
    Return `0` for an empty path. Uses `graph_mgr` semantic caching (thread-safe).
    """
    if not path:
        return 0.0
    total = 0.0
    for src, event, tgt in path:
        total += _compute_edge_semantic_weight(event, graph_mgr) + _compute_edge_data_weight(src, tgt)
    return total / len(path)


def extract_and_filter_subgraph(
    graph_mgr: GraphManager,
    start_node: AbstractStateNode,
    end_node: AbstractStateNode,
    max_depth: int = 5,
    max_edges_limit: int = 50,
) -> List[Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]]:
    """
    Extract a local subgraph at the path granularity while controlling the number of edges:
    depth-limited search -> path scoring -> greedy re-composition.

    Ensures the subgraph is connected and the number of edges does not exceed
    `max_edges_limit`.

    Path scoring uses embedding similarity between edge semantics and `TEXT_TARGET` (requires
    semantic cache to be filled before subgraph extraction).
    Returns:
        Edge list `[(src, event, tgt), ...]` without `edge_id`.
    """
    _ensure_semantic_embedding_cache(graph_mgr)
    all_paths = find_all_paths(graph_mgr, start_node, end_node, max_depth)
    if not all_paths:
        return []

    unique_edges = get_unique_edges_from_paths(all_paths)
    if len(unique_edges) <= max_edges_limit:
        return list(unique_edges.values())

    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        return list(unique_edges.values())[:max_edges_limit]

    path_scores: List[Tuple[PathEdges, float]] = []
    for path in all_paths:
        path_scores.append((path, calculate_path_score(graph_mgr, path)))
    path_scores.sort(key=lambda x: x[1], reverse=True)

    final_edges_dict: Dict[Tuple[int, int, str], Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]] = {}
    for path, _score in path_scores:
        path_edges = get_edges_from_path(path)
        new_keys = set(path_edges.keys()) - set(final_edges_dict.keys())
        if len(final_edges_dict) + len(new_keys) > max_edges_limit:
            break
        for k in new_keys:
            final_edges_dict[k] = path_edges[k]

    return list(final_edges_dict.values())


def build_local_candidate_subgraph(
    graph_mgr: GraphManager,
    exit_state: AbstractStateNode,
    entry_state: AbstractStateNode,
    max_depth: int = 6,
    max_edges_limit: int = 50,
) -> Tuple[Set[AbstractStateNode], List[Tuple[str, AbstractStateNode, AbstractEvent, AbstractStateNode]]]:
    """
    Build a local candidate subgraph from `exit_state` to `entry_state` at the path granularity
    (connected and focused):
    - Stage 1: use depth-limited DFS to find all paths from `exit_state` to `entry_state`.
    - Stage 2: if the number of de-duplicated edges exceeds `max_edges_limit`, sort paths by
      decreasing path score `S_path`.
    - Stage 3: greedily add edges from higher-priority paths until the edge budget is reached.

    Keep the return format compatible with the downstream
    `build_subgraph_semantic_summary` / `build_edge_by_id`.

    Returns:
        (nodes_set, [(edge_id, src, event, tgt), ...])
    """
    edges = extract_and_filter_subgraph(
        graph_mgr, exit_state, entry_state,
        max_depth=max_depth,
        max_edges_limit=max_edges_limit,
    )
    nodes_set: Set[AbstractStateNode] = set()
    edges_with_id: List[Tuple[str, AbstractStateNode, AbstractEvent, AbstractStateNode]] = []
    for i, (src, event, tgt) in enumerate(edges, 1):
        nodes_set.add(src)
        nodes_set.add(tgt)
        edges_with_id.append((f"E{i}", src, event, tgt))
    return nodes_set, edges_with_id


def _state_semantic_and_snapshot(state: AbstractStateNode) -> str:
    """State semantic + a snapshot of key data fields for a single state (including values)."""
    if isinstance(state, StateNode):
        page = getattr(state, "parent_page_node", None)
        semantic = getattr(page, "semantic_label", None) or getattr(state, "name", "") or ""
        parts = [semantic] if semantic else []
        for de in getattr(state, "data_entities", []) or []:
            key = getattr(de, "key", "")
            val = getattr(de, "value", "")
            if key or val:
                parts.append(f"{key}={val}" if key else str(val))
        return " | ".join(parts) if parts else getattr(state, "name", str(state.id))
    return getattr(state, "name", str(state.id))


def _event_semantic(event: AbstractEvent) -> str:
    """Event semantic: a description of the transition operation."""
    event_semantic = ""
    if event.type == "click":
        event_semantic = f"Clicked (xpath: {event.xpath})"
    elif event.type == "text_input":
        event_semantic = f"Entered text '{event.text}' (xpath: {event.xpath})"
    elif event.type == "text_clear":
        event_semantic = f"Cleared text (xpath: {event.xpath})"
    elif event.type == "back":
        event_semantic = "Performed back operation"
    elif event.type == "internal":
        event_semantic = "Internal transition"
    if getattr(event, "semantic_label", None):
        event_semantic += f"(The semantic label of this operation is: {event.semantic_label})"
    return event_semantic


def build_subgraph_semantic_summary(
    edges_with_id: List[Tuple[str, AbstractStateNode, AbstractEvent, AbstractStateNode]],
) -> List[Tuple[str, str]]:
    """
    Generate a semantic summary for each edge in the local subgraph for the LLM to read.

    Returns: `[(edge_id, description), ...]`, where `description` has the form:
    "from [state semantic + data snapshot] via [event semantic] can reach [state semantic + data snapshot]".
    """
    result: List[Tuple[str, str]] = []
    for eid, src, event, tgt in edges_with_id:
        from_s = _state_semantic_and_snapshot(src)
        to_s = _state_semantic_and_snapshot(tgt)
        ev_s = _event_semantic(event)
        desc = f"From [{from_s}] via [{ev_s}] to [{to_s}]"
        result.append((eid, desc))
    return result


def build_edge_by_id(
    edges_with_id: List[Tuple[str, AbstractStateNode, AbstractEvent, AbstractStateNode]],
) -> Dict[str, Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]]:
    """Build the mapping `edge_id -> (src, event, tgt)` from a list of id-tagged edges."""
    return {eid: (src, event, tgt) for eid, src, event, tgt in edges_with_id}


def align_intent_sequence_to_path(
    steps: List[Any],
    edge_by_id: Dict[str, Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]],
    exit_state: AbstractStateNode,
    entry_state: AbstractStateNode,
) -> Optional[Tuple[List[AbstractStateNode], List[AbstractEvent]]]:
    """
    Align an intent sequence (each step includes an `edge_id`) to a state path in the graph.

    Validation:
    - the first edge's source is `exit_state`
    - the last edge's target is `entry_state`
    - consecutive edges are connectable (previous target matches next source)

    If valid, return `(state_list, event_list)`; otherwise return `None`.

    `state_list` includes `exit_state` and `entry_state`.
    `event_list` includes all events from `exit_state` to `entry_state`.

    `steps` elements must have an `edge_id` attribute or be a `dict` with an `'edge_id'` key.
    """
    if not steps:
        return None
    edges: List[Tuple[AbstractStateNode, AbstractEvent, AbstractStateNode]] = []
    for s in steps:
        eid = getattr(s, "edge_id", None) or (s.get("edge_id") if isinstance(s, dict) else None)
        if eid is None or eid not in edge_by_id:
            return None
        edges.append(edge_by_id[eid])
    if not edges:
        return None
    if edges[0][0].id != exit_state.id:
        return None
    if edges[-1][2].id != entry_state.id:
        return None
    for i in range(len(edges) - 1):
        if edges[i][2].id != edges[i + 1][0].id:
            return None
    state_list = [exit_state] + [e[2] for e in edges]
    event_list = [e[1] for e in edges]
    return state_list, event_list

# MR-Cancel specific utilities
INVERSE_LABEL_TARGET = "remove, cancel, delete, undo"
_INVERSE_LABEL_TOP_K = 20
_INVERSE_KEYWORDS = ("remove", "cancel", "delete", "undo")

def _filter_candidate_inverse_labels(labels: List[str]) -> List[str]:
    """Filter candidate inverse labels with embedding similarity and keyword fallback."""
    filtered_labels: List[str] = []
    labels = [lb.strip() for lb in labels if isinstance(lb, str) and lb.strip()]
    if not labels:
        return filtered_labels

    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        for lb in labels:
            if any(k in lb.lower() for k in _INVERSE_KEYWORDS):
                filtered_labels.append(lb)
        return filtered_labels

    try:
        model = _download_and_save_model()
        target_embedding = np.asarray(model.encode(INVERSE_LABEL_TARGET, normalize_embeddings=True)).flatten()
        label_embeddings = model.encode(labels, normalize_embeddings=True)
        scored_labels: List[Tuple[str, float]] = []
        for lb, emb in zip(labels, label_embeddings):
            sim = float(np.dot(target_embedding, np.asarray(emb).flatten()))
            scored_labels.append((lb, sim))
        scored_labels.sort(key=lambda x: x[1], reverse=True)
        keep_count = min(_INVERSE_LABEL_TOP_K, len(scored_labels))
        filtered_labels = [lb for lb, _ in scored_labels[:keep_count]]
    except Exception as e:
        print(f"Embedding-based inverse label filtering failed: {e}")
        filtered_labels = []

    # Keyword fallback: preserve high-precision inverse verbs even if similarity misses.
    for lb in labels:
        if any(k in lb.lower() for k in _INVERSE_KEYWORDS) and lb not in filtered_labels:
            filtered_labels.append(lb)

    return filtered_labels

# Path Filtering and Validation

def filter_duplicate_paths(
    paths: List[List[AbstractStateNode]]
) -> List[List[AbstractStateNode]]:
    """
    Remove semantically duplicate paths.
    
    Args:
        paths: List of state sequences
        
    Returns:
        Filtered list with duplicates removed
    """
    unique_paths = []
    seen_signatures = set()
    
    for path in paths:
        # Create signature based on state IDs
        signature = tuple(state.id for state in path)
        
        if signature not in seen_signatures:
            seen_signatures.add(signature)
            unique_paths.append(path)
    
    return unique_paths


def is_path_different_from_original(
    new_states: List[AbstractStateNode],
    original_states: List[AbstractStateNode]
) -> bool:
    """
    Check if a path differs from the original.
    
    Args:
        new_states: New state sequence
        original_states: Original state sequence
        
    Returns:
        True if paths are different
    """
    if len(new_states) != len(original_states):
        return True
    
    for new_state, orig_state in zip(new_states, original_states):
        if new_state.id != orig_state.id:
            return True
    
    return False


def calculate_path_diversity_score(
    path1: List[AbstractStateNode],
    path2: List[AbstractStateNode]
) -> float:
    """
    Measure diversity between two paths.
    
    Args:
        path1: First path
        path2: Second path
        
    Returns:
        Diversity score (0.0 = identical, 1.0 = completely different)
    """
    if not path1 or not path2:
        return 1.0
    
    # Length difference component
    max_len = max(len(path1), len(path2))
    min_len = min(len(path1), len(path2))
    length_diff = (max_len - min_len) / max_len if max_len > 0 else 0.0
    
    # State difference component
    states1 = set(s.id for s in path1)
    states2 = set(s.id for s in path2)
    
    union = states1 | states2
    intersection = states1 & states2
    
    state_diff = 1.0 - (len(intersection) / len(union)) if union else 0.0
    
    # Combined score
    return 0.5 * length_diff + 0.5 * state_diff


def limit_variants_by_diversity(
    paths: List[List[AbstractStateNode]],
    max_count: int
) -> List[List[AbstractStateNode]]:
    """
    Select most diverse paths up to maximum count.
    
    Args:
        paths: List of candidate paths
        max_count: Maximum number of paths to return
        
    Returns:
        Filtered list of diverse paths
    """
    if len(paths) <= max_count:
        return paths
    
    # Start with the first path
    selected = [paths[0]]
    remaining = paths[1:]
    
    while len(selected) < max_count and remaining:
        # Find path with maximum average diversity from selected paths
        best_path = None
        best_score = -1.0
        
        for candidate in remaining:
            avg_diversity = sum(
                calculate_path_diversity_score(candidate, selected_path)
                for selected_path in selected
            ) / len(selected)
            
            if avg_diversity > best_score:
                best_score = avg_diversity
                best_path = candidate
        
        if best_path:
            selected.append(best_path)
            remaining.remove(best_path)
    
    return selected


def validate_path_in_graph(script_path: ScriptPath) -> bool:
    """
    Verify path validity against graph.
    
    Args:
        script_path: The path to validate
        
    Returns:
        True if path is valid
    """
    states = extract_state_sequence(script_path)
    
    if not states:
        return True
    
    # Check each transition
    for i in range(len(states) - 1):
        source = states[i]
        target = states[i + 1]
        
        # Check if transition exists
        event = get_transition_event(source, target)
        if event is None:
            return False
    
    return True

# Path Discovery and Search Algorithms

def find_all_paths_between_states(
    graph_mgr: GraphManager,
    start_state: StateNode,
    end_state: StateNode,
    config: Optional[PathSearchConfig] = None
) -> List[List[AbstractStateNode]]:
    """
    Find all paths between two states with optional constraints.
    
    Uses BFS to discover paths, respecting depth limits and page constraints.
    
    Args:
        graph_mgr: The graph manager
        start_state: Starting state
        end_state: Target state
        config: Search configuration (uses defaults if None)
        
    Returns:
        List of paths, where each path is a list of states
    """
    from transition_graph import InternalStateNode, StateNode
    
    if config is None:
        config = PathSearchConfig()

    if not config.allow_cycles:
        config.max_repeat_per_page = 1

    if start_state == end_state:
        return [[start_state]]

    paths = []

    # Queue contains: (current_state, path_so_far, page_counter)
    queue = deque([
        (
            start_state,
            [start_state],
            Counter([start_state.id])
        )
    ])

    while queue and len(paths) < config.max_results:
        current_state, path, counter = queue.popleft()

        # Depth limit
        if len(path) > config.max_depth:
            continue

        for event, target in current_state.transitions.items():
            if isinstance(target, InternalStateNode):
                for internal_event, internal_target in target.transitions.items():
                    # repetition check
                    if counter[internal_target.id] >= config.max_repeat_per_page:
                        continue

                    if not _satisfies_page_constraints(
                        internal_target, config.page_constraints
                    ):
                        continue

                    new_path = path + [target, internal_target]

                    if internal_target == end_state:
                        paths.append(new_path)
                        if len(paths) >= config.max_results:
                            break
                        continue

                    new_counter = counter.copy()
                    new_counter[target.id] += 1
                    new_counter[internal_target.id] += 1

                    queue.append(
                        (internal_target, new_path, new_counter)
                    )
            else:
                if counter[target.id] >= config.max_repeat_per_page:
                    continue

                if not _satisfies_page_constraints(
                    target, config.page_constraints
                ):
                    continue

                new_path = path + [target]

                if target == end_state:
                    paths.append(new_path)
                    if len(paths) >= config.max_results:
                        break
                    continue

                new_counter = counter.copy()
                new_counter[target.id] += 1

                queue.append(
                    (target, new_path, new_counter)
                )

    # Prefer shorter paths
    if config.prefer_shorter_paths:
        paths.sort(key=len)

    return paths

def _satisfies_page_constraints(
    state: AbstractStateNode,
    page_constraints: Optional[List[PageNode]]
) -> bool:
    """
    Check if a state satisfies page constraints.
    
    Args:
        state: State to check
        page_constraints: List of allowed pages (None = no constraint)
        
    Returns:
        True if state satisfies constraints
    """
    from transition_graph import StateNode
    
    if page_constraints is None:
        return True
    
    if not isinstance(state, StateNode):
        return True  # Internal states don't have page constraints
    
    return state.parent_page_node in page_constraints


def find_paths_through_pages(
    graph_mgr: GraphManager,
    start_state: StateNode,
    end_state: StateNode,
    required_pages: List[PageNode],
    config: Optional[PathSearchConfig] = None
) -> List[List[AbstractStateNode]]:
    """
    Find paths that traverse specific pages in order.
    
    Args:
        graph_mgr: The graph manager
        start_state: Starting state
        end_state: Target state
        required_pages: Pages that must be traversed in order
        config: Search configuration
        
    Returns:
        List of paths that go through all required pages
    """
    from transition_graph import StateNode
    
    if not required_pages:
        return find_all_paths_between_states(graph_mgr, start_state, end_state, config)
    
    # Find all paths and filter those that traverse required pages
    all_paths = find_all_paths_between_states(graph_mgr, start_state, end_state, config)
    valid_paths = []
    
    for path in all_paths:
        # Extract page sequence from path
        path_pages = []
        for state in path:
            if isinstance(state, StateNode):
                page = state.parent_page_node
                if not path_pages or path_pages[-1] != page:
                    path_pages.append(page)
        
        # Check if required pages appear in order
        if _contains_pages_in_order(path_pages, required_pages):
            valid_paths.append(path)
    
    return valid_paths


def _contains_pages_in_order(
    path_pages: List[PageNode],
    required_pages: List[PageNode]
) -> bool:
    """
    Check if required pages appear in path_pages in the specified order.
    
    Args:
        path_pages: Actual page sequence
        required_pages: Required page sequence
        
    Returns:
        True if all required pages appear in order
    """
    req_idx = 0
    
    for page in path_pages:
        if req_idx < len(required_pages) and page == required_pages[req_idx]:
            req_idx += 1
    
    return req_idx == len(required_pages)


def find_page_to_page_paths(
    graph_mgr: GraphManager,
    source_page: PageNode,
    target_page: PageNode,
    max_intermediate_pages: int = 3,
    max_repeat_per_page: int = 2
) -> List[List[PageNode]]:
    """
    Find page-level paths from source page to target page.
    
    Args:
        graph_mgr: The graph manager
        source_page: Starting page
        target_page: Target page
        max_intermediate_pages: Maximum number of intermediate pages
        
    Returns:
        List of page sequences
    """
    if source_page == target_page:
        return [[source_page]]
    
    page_paths = []
    queue = deque([(source_page, [source_page], Counter([source_page.id]))])

    max_len = max_intermediate_pages + 2

    while queue:
        current_page, path, counter = queue.popleft()

        if len(path) >= max_len:
            continue

        for next_page in current_page.get_all_adjacent_pages():
            if counter[next_page.id] >= max_repeat_per_page:
                continue

            new_counter = counter.copy()
            new_counter[next_page.id] += 1
            new_path = path + [next_page]

            if next_page == target_page:
                page_paths.append(new_path)
            else:
                queue.append((next_page, new_path, new_counter))

    return page_paths


def get_candidate_intermediate_pages(
    graph_mgr: GraphManager,
    source_page: PageNode,
    target_page: PageNode,
    max_intermediate_pages: int = 3,
    max_repeat_per_page: int = 2,
) -> List[PageNode]:
    """
    Collect intermediate pages (excluding the first/last pages) that appear in any BFS path
    from `source_page` to `target_page`. De-duplicate them and return in first-seen order.

    Used for MR-State: the graph provides only a set of candidate intermediate pages,
    and the LLM selects ordered indices from them (we do not enumerate full page sequences).

    Args:
        graph_mgr: Graph manager.
        source_page: Starting page.
        target_page: Target page.
        max_intermediate_pages: Upper bound on the number of intermediate pages.
        max_repeat_per_page: Maximum repeat count per page.

    Returns:
        List of candidate intermediate pages (possibly empty).
    """
    if source_page == target_page:
        return []

    seen_ids = set()
    ordered: List[PageNode] = []
    queue = deque([(source_page, [source_page], Counter([source_page.id]))])
    max_len = max_intermediate_pages + 2

    while queue:
        current_page, path, counter = queue.popleft()

        if len(path) >= max_len:
            continue

        for next_page in current_page.get_all_adjacent_pages():
            if counter[next_page.id] >= max_repeat_per_page:
                continue

            new_counter = counter.copy()
            new_counter[next_page.id] += 1
            new_path = path + [next_page]

            if next_page == target_page:
                for p in new_path[1:-1]:
                    if p.id not in seen_ids:
                        seen_ids.add(p.id)
                        ordered.append(p)
            else:
                queue.append((next_page, new_path, new_counter))

    return ordered
