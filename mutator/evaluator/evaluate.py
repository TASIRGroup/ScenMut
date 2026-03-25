import yaml
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from transition_graph import GraphManager, PathManager
from device_infrastructure import DeviceManager

class Evaluator:

    def __init__(self, yaml_file_path):
        self.yaml_file_path = yaml_file_path
        yaml_file = open(yaml_file_path, "r")
        self.config = yaml.safe_load(yaml_file)
        yaml_file.close()

        self.graph_mgr = GraphManager(yaml_file_path)
        self.graph_mgr.load_graph_from_file()
        self.path_mgr = PathManager(yaml_file_path, self.graph_mgr)
        self.path_mgr.load_paths_from_file()
        self.device_mgr = None
        self.state_mgr = None

    def execute_all_script_files(self, script_dir: str = None):
        """
        Execute all script files in the given directory. Calculate metrics.
        Args:
            script_dir: The directory containing the script files.
        """
        if script_dir is None:
            script_dir = str(Path(self.config["outputDir"] + f"/{self.config['appium']['appPackage']}" + "/mutated_scripts").absolute())

        result_array = []
        start_time = datetime.now()

        for i, script_file in enumerate(os.listdir(script_dir)):
            if script_file.endswith(".py"):
                result = self.execute_single_script_file(os.path.join(script_dir, script_file))
                result_array.append(result)
        
        end_time = datetime.now()
        total_execution_time = (end_time - start_time).total_seconds()

        metrics = {
            "total_execution_time": total_execution_time,
            "number_of_scripts": len(result_array),
            "results": result_array,
            "success_rate": sum(1 for r in result_array if r) / len(result_array) if len(result_array) > 0 else 0,
            "average_time_per_script": total_execution_time / len(result_array) if len(result_array) > 0 else 0
        }

        print("Evaluation metrics:" + str(metrics))

    def execute_single_script_file(self, script_file: str, device_id: str = None):
        """
        Execute a single script file using sub process. Calculate metrics. Pull coverage file.
        Args:
            script_file: The path to the script file.
            device_id: The ID of the device to execute the script file on.
        """
        print(f"Executing script file: {script_file}")

        with open(script_file, "r", encoding="utf-8") as f:
            script_content = f.read()

        # inject device id into the script file
        # {"udid": device_id}
        device_id = self.config["env"]["device_id"] if device_id is None else device_id
        script_content = script_content.replace('"udid": "device_id",', f'"udid": "{device_id}",')
        # {"systemPort": "system_port"}
        system_port = DeviceManager._calc_system_port(device_id)
        script_content = script_content.replace('"systemPort": "system_port",', f'"systemPort": "{system_port}",')
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script_content)

        failed_to_execute = False
        try:
            subprocess.run(["python", script_file], check=True, stdout=sys.stdout, stderr=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Error executing script file {script_file}: {e}")
            failed_to_execute = True
        except Exception as e:
            print(f"Error occurred: {e}")
            failed_to_execute = True
        if failed_to_execute:
            return False
        print(f"Script file {script_file} executed successfully.")

        return True