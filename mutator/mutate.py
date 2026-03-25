from mutator.explorer.explore import Explorer
from mutator.explorer.trace import Tracer
from mutator.generator.generate import Generator
from mutator.generator.report_generation import generate_report
from mutator.evaluator.evaluate import Evaluator
from transition_graph import PathManager, GraphManager

def get_config(yaml_file_path):
    import yaml
    with open(yaml_file_path, 'r') as file:
        config = yaml.safe_load(file)
        file.close()
    return config

def get_log_dir(config):
    from pathlib import Path
    log_dir = Path(config['logDir'])
    return log_dir

def get_app_name(config):
    return config['appium']['appPackage']

def mutate(yaml_file_path, explore_only: bool = False, skip_evaluation: bool = False, mutation_only: bool = False, evaluation_only: bool = False, rerun_script_and_report_generation: bool = False):
    import sys
    from time import sleep
    from datetime import datetime
    from transition_graph import InternalStateNode

    config = get_config(yaml_file_path)
    log_dir = get_log_dir(config)
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    trace_end_time = None
    exp_end_time = None
    mutated_paths = []
    paths = []
    metrics = {}

    try:
        start_time = datetime.now()

        # ---------- Modeling: Parse & Trace + Explore -> modeling_logs.txt ----------
        if not mutation_only and not evaluation_only:
            modeling_log = open(log_dir / 'modeling_logs.txt', 'w', encoding='utf-8')
            try:
                sys.stdout = sys.stderr = modeling_log
                print('-' * 10 + "TRACE PHASE STARTED" + '-' * 10)
                try:
                    tracer = Tracer(yaml_file_path)
                    metrics = tracer.execute_and_trace_all_scripts()
                except Exception as e:
                    print(f"Error during tracing: {e}")
                finally:
                    trace_end_time = datetime.now()
                    trace_time = (trace_end_time - start_time).total_seconds()
                    print(f"Trace Time {trace_time}s")

                    generator = Generator(yaml_file_path)
                    name_and_paths = generator.get_original_script_paths()
                    if len(name_and_paths) == 0:
                        print("No original script paths found. Please check the trace results. Subsequebt steps will be skipped.")
                        return
                print('-' * 10 + "TRACE PHASE COMPLETED" + '-' * 10)

                print('-' * 10 + "EXPLORE PHASE STARTED" + '-' * 10)
                try:
                    explorer = Explorer(yaml_file_path)
                    while True:
                        res = explorer.explore()
                        if res == "end":
                            break
                    print(explorer.graph_mgr.get_script_name_list())
                    explorer.graph_mgr.refine_pagination_by_semantic_labels_full()
                    explorer.graph_mgr.save_graph_to_file()
                except Exception as e:
                    print(f"Error during exploration: {e}")
                finally:
                    exp_end_time = datetime.now()
                    explore_time = (exp_end_time - trace_end_time).total_seconds() if trace_end_time else 0
                    print(f"Explore Time: {explore_time}s")
                print('-' * 10 + "EXPLORE PHASE COMPLETED" + '-' * 10)
            finally:
                sys.stdout, sys.stderr = saved_stdout, saved_stderr
                modeling_log.close()

            if explore_only:
                with open(log_dir / 'modeling_logs.txt', 'a', encoding='utf-8') as f:
                    f.write("Explore only mode. Exiting...\n")
                return

        # ---------- Generate -> mutation_logs.txt ----------
        if not evaluation_only:
            exp_end_time = exp_end_time or datetime.now()
            mutation_log = open(log_dir / 'mutation_logs.txt', 'w', encoding='utf-8')
            try:
                sys.stdout = sys.stderr = mutation_log
                print('-' * 10 + "GENERATION PHASE STARTED" + '-' * 10)
                try:
                    generator = Generator(yaml_file_path)
                    generator.graph_mgr.refine_pagination_by_semantic_labels_full()
                    name_and_paths = generator.get_original_script_paths()
                    print("Original Script Paths:")
                    for name, path in name_and_paths:
                        path_string = list(map(lambda pn: f"{pn.state.id} (PNI: {pn.state.parent_page_node.id if not isinstance(pn.state, InternalStateNode) else 'i'}, ORC: {len(pn.oracles) if not isinstance(pn.state, InternalStateNode) and len(pn.oracles) > 0 else 'None'})", path.to_array()))
                        print(f"Script Name: {name}, Path: {path_string}")
                    paths = []
                    for name, path in name_and_paths:
                        paths.append(path)
                    mutated_paths = generator.generate_new_paths(paths)
                    for path in mutated_paths:
                        print(list(map(lambda pn: f"{pn.state.id}({pn.state.parent_page_node.id if not isinstance(pn.state, InternalStateNode) else 'i'})", path.to_array())))
                    generator.generate_scripts_to_file(mutated_paths, 'mutated', f"{config['outputDir']}/{get_app_name(config)}/mutated_scripts")

                    report_dir = f"{config['outputDir']}/{get_app_name(config)}/mutation_report"
                    generate_report(
                        mutated_paths,
                        report_dir,
                        application_name=get_app_name(config),
                        original_paths=paths,
                    )
                except Exception as e:
                    print(f"Error during generation: {e}")
                print('-' * 10 + "GENERATION PHASE COMPLETED" + '-' * 10)
            finally:
                sys.stdout, sys.stderr = saved_stdout, saved_stderr
                mutation_log.close()

        if skip_evaluation:
            with open(log_dir / 'mutation_logs.txt', 'a', encoding='utf-8') as f:
                f.write("Skip evaluation mode. Exiting...\n")
            return

        # ---------- Evaluate -> evaluation_logs.txt ----------
        evaluation_log = open(log_dir / 'evaluation_logs.txt', 'w', encoding='utf-8')
        try:
            sys.stdout = sys.stderr = evaluation_log
            print('-' * 10 + "EVALUATION PHASE STARTED" + '-' * 10)
            try:
                if rerun_script_and_report_generation:
                    try:
                        graph_mgr = GraphManager(yaml_file_path)
                        graph_mgr.load_graph_from_file()
                        path_mgr = PathManager(yaml_file_path, graph_mgr)
                        path_mgr.load_paths_from_file()
                        generator = Generator(yaml_file_path)
                        generator.generate_scripts_to_file(path_mgr.mutated_paths, 'mutated_scripts', f"{config['outputDir']}/{get_app_name(config)}/mutated_scripts")
                        report_dir = f"{config['outputDir']}/{get_app_name(config)}/mutation_report"
                        generate_report(
                            path_mgr.mutated_paths,
                            report_dir,
                            application_name=get_app_name(config),
                            original_paths=path_mgr.original_paths,
                        )
                    except Exception as e:
                        raise Exception(f"Error during rerunning script and report generation: {e}")

                evaluator = Evaluator(yaml_file_path)
                metrics = evaluator.execute_all_script_files()
                print(metrics)
            except Exception as e:
                print(f"Error during evaluation: {e}")
            finally:
                print('-' * 10 + "EVALUATION PHASE COMPLETED" + '-' * 10)
        finally:
            sys.stdout, sys.stderr = saved_stdout, saved_stderr
            evaluation_log.close()

    except Exception as e:
        saved_stdout.write(str(e) + "\n")
    finally:
        sys.stdout, sys.stderr = saved_stdout, saved_stderr
        sleep(5)

    return