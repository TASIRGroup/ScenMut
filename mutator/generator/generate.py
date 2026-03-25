import yaml
from pathlib import Path
from typing import List

from transition_graph import GraphManager, ScriptPath, PathNode, InternalPathNode, InternalStateNode, PathManager

class Generator:

    def __init__(self, yaml_file_path):
        self.yaml_file_path = yaml_file_path
        self.graph_mgr = GraphManager(yaml_file_path)
        self.graph_mgr.load_graph_from_file()
        self.path_mgr = PathManager(yaml_file_path, self.graph_mgr)
        self.mr_instances = []

        yaml_file = open(yaml_file_path, "r")
        self.config = yaml.safe_load(yaml_file)
        yaml_file.close()
        
        self.max_results = self.config["mutation"]["maxMutations"]
        self.script_dir = Path(self.config["scriptDir"])

    def get_original_script_paths(self) -> List[ScriptPath]:
        from mutator.parser.parse import parse_script

        script_paths = []

        for script_file in self.script_dir.iterdir():
            if script_file.is_file() and script_file.suffix == ".py":
                script_content = script_file.read_text(encoding='utf-8')
                steps, _ = parse_script(script_content)
                path = self.build_script_path(script_file.name, steps)
                if len(path.to_array()) > 0:
                    script_paths.append([script_file.name, path])
                else:
                    print(f"Error: Invalid path for script {script_file.name}")

        self.path_mgr.extend_paths(map(lambda path: path[1], script_paths), 'original')
        self.path_mgr.save_paths_to_file()

        return script_paths


    def build_script_path(self, script_name: str, steps) -> ScriptPath:
        from mutator.explorer.trace import Tracer

        states_list = self.graph_mgr.get_states_by_script_name(script_name)

        script_path = ScriptPath()
        script_path.set_path_type("original")
        script_path.set_path_name(script_name)
        current_state_index = 0

        for step in steps:
            if current_state_index >= len(states_list) - 1:
                print(f"Warning: More steps than states. The last step will be ignored.")
                return ScriptPath()
            current_state = states_list[current_state_index]
            transitions = current_state.transitions
            # transition: {event -> target_state_node}
            events = transitions.keys()
            matched_event = Tracer.match_step_and_event(step, current_state.component_tree, events)
            oracles = current_state.get_oracles([script_name, current_state_index])

            if matched_event is None:
                print(f"Error: No matching event found for step: {step}. Path building aborted without a valid path.")
                return ScriptPath()
            
            script_path.add_path_node(PathNode(current_state, matched_event, oracles))

            # get the target state node
            target_state_node = transitions[matched_event]
            if isinstance(target_state_node, InternalStateNode):
                real_target_state_node = states_list[current_state_index + 1]
                found_corresponding_state = False
                                # check whether the corresponding_state in the target_state_node's transitions
                for nominate_state_node in target_state_node.transitions.values():
                    if real_target_state_node.id == nominate_state_node.id:
                        found_corresponding_state = True
                        break
                if not found_corresponding_state:
                    print(f"Error: The corresponding state {real_target_state_node} is not in the target state node's transitions.")
                    return ScriptPath()
                # find the event that leads to the corresponding state
                target_event = None
                for event, target_state in target_state_node.transitions.items():
                    if target_state == real_target_state_node:
                        target_event = event
                        break
                if target_event is None:
                    print(f"Error: No event found that leads to the corresponding state {real_target_state_node}.")
                    return ScriptPath()
                script_path.add_path_node(InternalPathNode(target_state_node, target_event))
                target_state_node = real_target_state_node

            current_state_index += 1
            if current_state_index == len(states_list) - 1:
                # reached the end, add the last state node
                oracles = target_state_node.get_oracles([script_name, current_state_index])
                script_path.add_path_node(PathNode(target_state_node, None, oracles))

        return script_path


    def load_mr_instances(self):
        # Load MR instances from config
        from .mrs.mr_factory import MRFactory

        for mr_type, mr_config in self.config["MRs"].items():
            if mr_config["enabled"]:
                mr_instance = MRFactory.create_mr(mr_type, self.graph_mgr, self.config)
                self.mr_instances.append(mr_instance)

    def filter_new_paths(self, new_paths: List[ScriptPath]) -> List[ScriptPath]:
        import numpy as np

        def _build_distance_matrix(paths: List[ScriptPath]) -> np.ndarray:
            """
            D[i][j] = f(paths[i], paths[j])
            """
            n = len(paths)
            D = np.zeros((n, n), dtype=float)

            for i in range(n):
                for j in range(i + 1, n):
                    distance = PathManager.diversity([paths[i], paths[j]])
                    D[i, j] = D[j, i] = distance

            return D

        def _greedy_diverse_selection(
            paths: List[ScriptPath],
            x: int
        ) -> List[ScriptPath]:
            """
            Greedy Max-Sum Dispersion
            """
            n = len(paths)
            D = _build_distance_matrix(paths)

            # choose a "most diverse" point as the starting point (better than random)
            start = np.argmax(D.sum(axis=1))

            selected = [start]
            remaining = set(range(n)) - {start}

            # gain[i] = sum_{u in selected} D[i][u]
            gain = D[start].copy()

            while len(selected) < x:
                # choose the point with the maximum gain
                nxt = max(remaining, key=lambda i: gain[i])
                selected.append(nxt)
                remaining.remove(nxt)

                # update gain
                for i in remaining:
                    gain[i] += D[i][nxt]

            return [paths[i] for i in selected]

        new_paths = PathManager.unique(new_paths)
        print(f"Number of unique paths: {len(new_paths)}")
        if self.max_results is not None and len(new_paths) > self.max_results:
            # try to choose the most diverse paths
            new_paths = _greedy_diverse_selection(new_paths, self.max_results)
        new_paths.sort(key=lambda path: len(path.to_array()))
        print(f"Number of paths after sorting and filtering: {len(new_paths)}")
        return new_paths

    def generate_new_paths(self, original_script_paths: List[ScriptPath]) -> List[ScriptPath]:
        if len(self.mr_instances) == 0:
            print("No MR instances loaded. Auto-load MR instances from config.")
            self.load_mr_instances()

        new_paths = []

        from mutator.generator.assertion_synthesis import run_assertion_synthesis
        from mutator.generator.context_extraction import MUTATION_TYPE_DATA, MUTATION_TYPE_STATE, MUTATION_TYPE_CANCEL

        for mr_instance in self.mr_instances:
            count = 0
            mr_type = getattr(mr_instance, "mr_type", mr_instance.__class__.__name__)
            for original_script_path in original_script_paths:
                mutated_paths = mr_instance.apply(original_script_path)
                for path in mutated_paths:
                    path.set_path_type("mutated")
                    if mr_type in ("MRData", "MRState", "MRCancel"):
                        try:
                            desc = getattr(mr_instance, "get_mutation_description", lambda o, p: {})(original_script_path, path) if hasattr(mr_instance, "get_mutation_description") else {}
                            run_assertion_synthesis(original_script_path, path, mr_type, desc, self.graph_mgr, self.config)
                        except Exception as e:
                            print(f"Assertion synthesis failed for {mr_type}: {e}")
                    new_paths.append(path)
                    count += 1
            print(f"MR {mr_instance.__class__.__name__} applied on {count} original script paths.")

        new_paths = self.filter_new_paths(new_paths)
        self.path_mgr.extend_paths(new_paths, 'mutated')
        self.path_mgr.save_paths_to_file()

        return new_paths

    def generate_script_to_file(self, script_path: ScriptPath, script_name: str, file_path: str, config: dict):
        from mutator.generator.script_generation import generate_script_of_mutated_path
        print(f"Generating script {script_name} to {file_path}")
        script_content = f"# This is a mutated script generated by ScenMut.\n# Script Name: {script_name}\n"
        script_content += generate_script_of_mutated_path(script_path, config)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        print(f"Script {script_name} generated and saved to {file_path}")

    def generate_scripts_to_file(self, mutated_paths: List[ScriptPath], script_name_prefix: str, directory_path: str):
        import os
        import shutil
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path)
        os.makedirs(directory_path)
        for i, path in enumerate(mutated_paths):
            script_name = f"{script_name_prefix}_{i}.py"
            self.generate_script_to_file(path, script_name, os.path.join(directory_path, script_name), self.config)