import yaml
from time import sleep

from device_infrastructure import DeviceManager
from transition_graph import GraphManager, StateManager
from .utils.event_visit_strategy import RandomEventVisitStrategy, SequentialEventVisitStrategy, UnvisitedPriorEventVisitStrategy, GraphOptimizedEventVisitStrategy

class Explorer:
    def __init__(self, yaml_file_path, epoch=None, reset=None):
        self.yaml_file_path = yaml_file_path
        self.device_mgr = None
        self.state_mgr = None
        self.graph_mgr = GraphManager(self.yaml_file_path)
        self.current_state = None
        if epoch is None:
            self.epoch = 0
        else:
            self.epoch = epoch

        yaml_file = open(yaml_file_path, "r")
        config = yaml.safe_load(yaml_file)
        yaml_file.close()
        self.max_epochs = config["maxExplorationEpochs"] if "maxExplorationEpochs" in config else 100
        self.delay = config["delay"] if "delay" in config else 0.5
        self.coverage_threshold = config["coverageThreshold"] if "coverageThreshold" in config else 1

        self.exploration_preset = config["explorationPreset"]
        self.event_visit_strategy = GraphOptimizedEventVisitStrategy(self.graph_mgr, back_penalty=(self.exploration_preset == "back_penalty"))

        print("Explorer initialized with max epochs:", self.max_epochs)

    def explore(self, app_name=None, logger=None):
        if self.device_mgr is not None:
            self.device_mgr.quit()
        self.device_mgr = DeviceManager(self.yaml_file_path, reset=False, seperate_screenshot_folder="exploration", seperate_coverage_folder="exploration")
        self.state_mgr = StateManager(self.device_mgr)

        self.load_exploration()
        print("Explorer: Continuing exploration from the last saved state.")

        if self.graph_mgr.get_start_state() is None:
            print("Explorer: No start state found. Creating a new start state.")
            print("Explorer: Setting up the initial state, starting the exploration. [Epoch: {}, Coverage: {}]".format(self.epoch, self.calculate_exploration_coverage()))
            self.current_state = self.state_mgr.capture_new_state()
            self.graph_mgr.add_new_state(self.current_state, None, None, self.state_mgr.capture_current_activity())
            self.graph_mgr.save_graph_to_file()
        else:
            print("Explorer: Found a start state in the graph. Resuming the exploration.")
            self.current_state = self.graph_mgr.get_start_state()

        same_streak = 0
        last_coverage = 0

        while True:
            self.epoch += 1

            if self.calculate_exploration_coverage() <= last_coverage:
                same_streak += 1
            else:
                same_streak = 0
            last_coverage = self.calculate_exploration_coverage()

            if same_streak >= 10:
                print(f"Explorer: No new coverage for 10 epochs. Stopping the exploration. [Epoch: {self.epoch}, Coverage: {self.calculate_exploration_coverage()}, States: {self.calculate_states_count()}, Events: {self.calculate_events_count()}, Transitions: {self.calculate_transitions_count()}]")
                return "continue"

            # Check if the maximum epochs or coverage threshold is reached
            if self.epoch > self.max_epochs:
                print(f"Explorer: Maximum epochs reached. Stopping the exploration. [Epoch: {self.epoch}, Coverage: {self.calculate_exploration_coverage()}, States: {self.calculate_states_count()}, Events: {self.calculate_events_count()}, Transitions: {self.calculate_transitions_count()}]")
                if logger is not None:
                    logger.log(app_name, "script0", key="aved", value=self.calculate_exploration_coverage(), phase="modeling")
                    logger.log(app_name, "script0", key="ed_cond", value="max_ep", phase="modeling")
                break
            if self.calculate_exploration_coverage() >= self.coverage_threshold:
                print(f"Explorer: Coverage threshold reached. Stopping the exploration. [Epoch: {self.epoch}, Coverage: {self.calculate_exploration_coverage()}, States: {self.calculate_states_count()}, Events: {self.calculate_events_count()}, Transitions: {self.calculate_transitions_count()}]")
                if logger is not None:
                    logger.log(app_name, "script0", key="aved", value=self.calculate_exploration_coverage(), phase="modeling")
                    logger.log(app_name, "script0", key="ed_cond", value="acc_cov", phase="modeling")
                break

            print(f"Explorer: Starting exploration on [State {self.current_state.id}]. [Epoch: {self.epoch}, Coverage: {self.calculate_exploration_coverage()}, States: {self.calculate_states_count()}, Events: {self.calculate_events_count()}, Transitions: {self.calculate_transitions_count()}]")

            # Save state
            if self.exploration_preset == "snapshot":
                self.device_mgr.save_snapshot()

            # Get applicable events
            unvisited_events = self.current_state.get_unvisited_events()
            visited_events = self.current_state.get_visited_events()
            target_event = self.event_visit_strategy.choose_event(visited_events, unvisited_events, transitions=self.current_state.transitions)
            print(f"Explorer: Executing event [{target_event}] in [State {self.current_state.id}]")

            # Perform the event
            target_event.perform(self.device_mgr)
            self.current_state.add_visited_event(target_event)

            # Check app state
            state = self.device_mgr.get_state()

            if state == "background":
                print("Explorer: App is in background. Marking the state as end state.")
                next_state = self.graph_mgr.get_end_state()
                if self.exploration_preset == "snapshot":
                    self.device_mgr.restore_snapshot()
                else: # self.exploration_preset == "default" or self.exploration_preset == "back_penalty"
                    pass
            elif state == "halted":
                print("Explorer: App is halted. Marking the state as end state.")
                next_state = self.graph_mgr.get_end_state()
                if self.exploration_preset == "snapshot":
                    self.device_mgr.restore_snapshot()
                else: # self.exploration_preset == "default" or self.exploration_preset == "back_penalty"
                    pass
            else: # state == "running"
                print("Explorer: App is in foreground. Capturing new state.")
                next_state = self.state_mgr.capture_new_state()

            # Add the new state to the graph
            next_state = self.graph_mgr.add_new_state(next_state, self.current_state, target_event, self.state_mgr.capture_current_activity())
            self.graph_mgr.save_graph_to_file()

            if state == "halted":
                if self.exploration_preset == "default" or self.exploration_preset == "back_penalty":
                    print("Explorer: Restarting the app after halt.")
                    return "continue"
                else: # self.exploration_preset == "snapshot"
                    pass
            elif state == "background":
                if self.exploration_preset == "default" or self.exploration_preset == "back_penalty":
                    print("Explorer: Restarting the app after background.")
                    return "continue"
                else: # self.exploration_preset == "snapshot"
                    pass
            elif state == "running":
                self.current_state = next_state

            sleep(self.delay)

        self.device_mgr.quit()
        return "end"

    def load_exploration(self):
        if self.graph_mgr.load_graph_from_file():
            print("Explorer: Loaded exploration graph from file.")

    def calculate_exploration_coverage(self):
        return self.graph_mgr.calculate_exploration_coverage()

    def calculate_states_count(self):
        return self.graph_mgr.calculate_states_count()

    def calculate_events_count(self):
        return self.graph_mgr.calculate_events_count()

    def calculate_transitions_count(self):
        return self.graph_mgr.calculate_transitions_count()

if __name__ == "__main__":
    from device_infrastructure import DeviceManager
    from transition_graph import GraphManager

    yaml_file_path = "/Users/xingjunyang/Documents/GitHub/PathMuTeG/config.yaml"

    explorer = Explorer(yaml_file_path)
    while True:
        res = explorer.explore()
        if res == "end":
            break
