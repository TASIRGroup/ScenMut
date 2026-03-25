def generate_yaml_file_for_this_script(config, app_device_map, specific_app_name=None):
    import yaml
    from pathlib import Path

    # Input Folder Structure
    # |-- input_folder
    #     |-- app_name1 (format: activity_name@package_name)
    #         |-- test_case1.py
    #         |-- test_case2.py
    #     |-- app_name2
    #         |-- test_case1.py

    # Output Folder Structure
    # |-- output_folder
    #     |-- app_name1
    #         |-- config.yaml
    #         |-- mutated_scripts
    #         |-- transition_graph
    #         |-- screenshots
    #         |-- logs
    #     |-- app_name2

    (Path(config["outputDir"])).mkdir(exist_ok=True)

    input_folder_path = Path(config['scriptDir'])
    for dir_path in input_folder_path.iterdir():
        if dir_path.is_dir():
            if len(dir_path.name.split('@')) != 2:
                print(f'Invalid directory name [{dir_path.name}], skipping this directory')
                continue
            app_name = dir_path.name.split('@')[1]  # Extract app name from the directory name
            activity_name = dir_path.name.split('@')[0]  # Extract activity name from the directory name

            if app_name not in app_device_map:
                print(f'App not registered, skipping this app.')
                continue

            if specific_app_name is not None and len(specific_app_name) > 0 and app_name not in specific_app_name:
                continue

            output_folder_path = Path(config['outputDir']) / app_name
            output_folder_path.mkdir(parents=True, exist_ok=True)

            # Copy config.yaml to the output folder
            config_data = config.copy()

            # Create the output folder structure
            (output_folder_path / 'transition_graph').mkdir(exist_ok=True)
            (output_folder_path / 'screenshots').mkdir(exist_ok=True)
            (output_folder_path / 'logs').mkdir(exist_ok=True)
            if config["coverageFile"]:
                (output_folder_path / 'coverage_data').mkdir(exist_ok=True)

            # modify the config data
            config_data["appium"]["appPackage"] = app_name
            config_data["appium"]["appActivity"] = activity_name
            config_data["screenshotDir"] = str((output_folder_path / 'screenshots').absolute())
            config_data["graphDir"] = str((output_folder_path / 'transition_graph').absolute())
            config_data["scriptDir"] = str(dir_path.absolute())
            config_data["logDir"] = str((output_folder_path / 'logs').absolute())
            if config["coverageFile"]:
                config_data["coverageFileDir"] = str((output_folder_path / 'coverage_data').absolute())

            # allocate device
            config_data["env"]["emulator"] = app_device_map[app_name]["emulator"]
            config_data["env"]["device_id"] = app_device_map[app_name]["device_id"]
            if "emulators" in config_data["env"]:
                config_data["env"].pop("emulators")

            with open(output_folder_path / 'config.yaml', 'w') as file:
                yaml.dump(config_data, file)
                file.close()

def generate_app_device_map(input_folder_path, device_list, specific_device_id=None):
    app_device_map = {}
    for idx, dir_path in enumerate(input_folder_path.iterdir()):
        if dir_path.is_dir():
            if len(dir_path.name.split('@')) != 2:
                print(f'Invalid directory name [{dir_path.name}], skipping this directory')
                continue
            app_name = dir_path.name.split('@')[1]  # Extract app name from the directory name
            if app_name not in app_device_map:
                if specific_device_id:
                    target_device_list_item = [x for x in device_list if x['device_id'] == specific_device_id]
                    if target_device_list_item:
                        app_device_map[app_name] = {"emulator": target_device_list_item[0], "device_id": specific_device_id}
                    else:
                        raise Exception(f"Device {specific_device_id} not found in device list")
                else:
                    app_device_map[app_name] = device_list[idx % len(device_list)]

            else:
                print(f'App {app_name} already exists in app_device_map, skipping this app.')
    return app_device_map

def worker_on_single_device(device_id, output_paths, progress_counter, progress_counter_lock, shared_ports, port_alloc_lock, explore_only, skip_evaluation, mutation_only, evaluation_only, rerun_script_and_report_generation):
    import yaml
    from mutator import mutate
    from device_infrastructure import EnvManager
    from device_infrastructure.device_manager import DeviceManager

    DeviceManager.set_shared_port_pool(shared_ports, port_alloc_lock)

    for output_path in output_paths:
        if output_path.is_dir():
            yaml_file_path = output_path / 'config.yaml'
            with open(yaml_file_path, 'r') as file:
                config = yaml.safe_load(file)
                file.close()
            if not skip_evaluation:
                EnvManager.install_apk(config['scriptDir'], device_id)
            mutate(yaml_file_path, explore_only, skip_evaluation, mutation_only, evaluation_only, rerun_script_and_report_generation)
            if not skip_evaluation:
                EnvManager.uninstall_apk(config['appium']['appPackage'], device_id)
        with progress_counter_lock:
            progress_counter.value += 1

def run_on_all_devices(config, output_path, app_device_map, specific_app_name=None, explore_only=False, skip_evaluation=False, mutation_only=False, evaluation_only=False, rerun_script_and_report_generation=False):
    import multiprocessing
    from tqdm import tqdm
    import time

    manager = multiprocessing.Manager()
    progress_counter = manager.Value('i', 0)
    progress_counter_lock = manager.Lock()
    shared_ports = manager.dict()
    port_alloc_lock = manager.Lock()

    device_app_output_paths_map = {}
    total_tasks = 0
    for folder_path in output_path.iterdir():
        if folder_path.is_dir() and folder_path.name in app_device_map:
            if specific_app_name and folder_path.name not in specific_app_name:
                continue

            if app_device_map[folder_path.name]["device_id"] not in device_app_output_paths_map:
                device_app_output_paths_map[app_device_map[folder_path.name]["device_id"]] = []
            device_app_output_paths_map[app_device_map[folder_path.name]["device_id"]].append(folder_path)
            total_tasks += 1

    processes = []
    for device_id, output_paths in device_app_output_paths_map.items():
        p = multiprocessing.Process(target=worker_on_single_device, args=(device_id, output_paths, progress_counter, progress_counter_lock, shared_ports, port_alloc_lock, explore_only, skip_evaluation, mutation_only, evaluation_only, rerun_script_and_report_generation))
        processes.append(p)

    # start all processes
    print("Starting all processes")
    for p in processes:
        p.start()

    # display progress
    with tqdm(total=total_tasks, desc="Total Progress") as pbar:
        last_value = 0
        while any(p.is_alive() for p in processes):
            with progress_counter_lock:
                current_value = progress_counter.value
            
            if current_value > last_value:
                pbar.update(current_value - last_value)
                last_value = current_value
            
            time.sleep(0.1)
        pbar.update(total_tasks - last_value)
    
    for p in processes:
        p.join()
    print("All processes completed")

def run_on_single_devices(config, output_path, device_id=None, specific_app_name=None, explore_only=False, skip_evaluation=False, mutation_only=False, evaluation_only=False, rerun_script_and_report_generation=False):
    import yaml
    from mutator import mutate
    from device_infrastructure import EnvManager

    for folder_path in output_path.iterdir():
        if folder_path.is_dir():
            if specific_app_name and folder_path.name not in specific_app_name:
                continue
            yaml_file_path = folder_path / 'config.yaml'
            with open(yaml_file_path, 'r') as file:
                config = yaml.safe_load(file)
                file.close()
            EnvManager.install_apk(config['scriptDir'], device_id)
            mutate(yaml_file_path, explore_only, skip_evaluation, mutation_only, evaluation_only, rerun_script_and_report_generation)
            EnvManager.uninstall_apk(config['appium']['appPackage'], device_id)

def main():
    import sys
    import argparse

    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        prog='main.py',
        description='[ScenMut] Implementation of "Scenario-based GUI Test Script Augmentation with Business-Logic-Enhanced Metamorphic Relations"',
        epilog='Visit our repo: https://github.com/iGUITest/ScenMut'
    )
    parser.add_argument('-f', '--config-file', dest='yaml_file_path', help='Specify Yaml config file path. See README.md or our default config file for more help.', default='./config.yaml')
    parser.add_argument('-d', '--device-id', dest='device_id', help='Specify the device id to run the test cases. This will be useful when you have multiple devices connected and want to debug on a specific device.')
    parser.add_argument('-p', '--package-name', dest='package_name', nargs='*', default=None, help='Specify the package name(s) of the app(s) to run. Can pass multiple: -p pkg1 pkg2 pkg3. Omit to run all apps in the input folder.')
    parser.add_argument('-m', '--modeling-only', dest='explore_only', action='store_true', help='Modeling only mode. Only include trace replay and exploration phases. This will skip the augmentation and evaluation phases.')
    parser.add_argument('-s', '--skip-evaluation', dest='skip_evaluation', action='store_true', help='Skip evaluation mode. This will skip the evaluation phase.')
    parser.add_argument('-a', '--augmentation-only', dest='mutation_only', action='store_true', help='Augmentation only mode. This will skip the modeling phase. However, you should still run the modeling phase to get the transition graph, otherwise the augmentation will not be able to find the correct transition graph.')
    parser.add_argument('-ev', '--evaluation-only', dest='evaluation_only', action='store_true', help='Evaluation only mode. This will skip the modeling and augmentation phases.')
    parser.add_argument('-rs', '--rerun-script-and-report-generation', dest='rerun_script_and_report_generation', action='store_true', help='Rerun script and report generation mode before evaluation. If the evaluation is skipped, this option will be ignored.')
    args = parser.parse_args()

    import yaml
    from pathlib import Path

    # Print Config
    config_info = f"""ScenMut
-------------------------
Config File: {args.yaml_file_path}"""
    print(config_info)

    main_yaml_file_path = args.yaml_file_path
    with open(main_yaml_file_path, 'r') as file:
        config = yaml.safe_load(file)
        file.close()

    output_path = Path(config['outputDir'])
    device_list = config['env']['emulators']
    devices_info_str = "Devices:\n"+ "\n".join([f"- {device['emulator']}: {device['device_id']}" for device in device_list])
    print(devices_info_str)
    if args.device_id:
        print(f"Running on specific device {args.device_id}")
    if args.package_name:
        print(f"Running for package(s): {', '.join(args.package_name)}")
    config_info_end = f"""-------------------------
"""
    print(config_info_end)

    app_device_map = generate_app_device_map(Path(config['scriptDir']), device_list, args.device_id)
    generate_yaml_file_for_this_script(config, app_device_map, args.package_name)

    # Check if the output path exists
    if output_path.exists():
        print(f"Output path {output_path} exists.")
    else:
        print(f"Output path {output_path} does not exist.")
        exit(1)

    if args.device_id:
        run_on_single_devices(config, output_path, app_device_map, args.device_id, args.package_name, args.explore_only, args.skip_evaluation, args.mutation_only, args.evaluation_only, args.rerun_script_and_report_generation)
    else:
        run_on_all_devices(config, output_path, app_device_map, args.package_name, args.explore_only, args.skip_evaluation, args.mutation_only, args.evaluation_only, args.rerun_script_and_report_generation)

if __name__ == '__main__':
    main()