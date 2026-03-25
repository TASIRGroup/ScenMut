# ScenMut: Scenario-based GUI Test Script Augmentation with Business-Logic-Enhanced Metamorphic Relations

### Environment Setup

To prepare the environment for this project, follow the steps below:

1. **Python Version**: Use Python 3.9+. Check your version with `python --version`.
2. **Install Python Dependencies**: Install all required libraries from `requirements.txt`:
  `pip install -r requirements.txt`
3. **Android Testing Toolchain**:
  - Install **ADB** and ensure `adb --version` works.
    - Install **Appium** and ensure `appium --version` works.
    - Prepare at least one Android emulator/device that can be accessed by ADB.
4. **LLM API Key**: ScenMut uses Qwen-compatible APIs via LangChain. Set your API key as an environment variable:
  `export DASHSCOPE_API_KEY=<your_api_key>`. If you want to use other LLM providers, you can add a corresponding connector by creating a new file in the `llm/providers` directory following the pattern of `qwen_client.py`.
5. **Optional Coverage Support**: If you enable coverage collection in config, make sure your app and environment support JaCoCo-related coverage extraction. The coverage files will be automatically saved to the corresponding directory under your output path.

### Project Structure

The repository is organized around modeling GUI behavior, augmenting scripts with metamorphic relations, and evaluating generated tests:

- **`mutator/`**: Main augmentation pipeline, including trace replay, exploration, augmented path generation, assertion synthesis, and evaluation.
- **`transition_graph/`**: Core data structures and managers for GUI state graphs, transitions, script paths, and oracles.
- **`device_infrastructure/`**: Appium/ADB integration layer, device control actions, environment setup helpers, and coverage operations.
- **`llm/`**: LLM-facing components, including prompt templates, method wrappers, and Qwen-compatible model client providers.
- **`main.py`**: Main entry point. It parses arguments, generates per-app/per-script runtime configs, dispatches jobs to single or multiple devices, and triggers the full workflow.
- **`config.example.yaml`**: Reference configuration file, covering environment settings, Appium capability fields, path augmentation controls, exploration settings, and enabled MR categories.

### Configuration and Execution

To configure and run ScenMut, follow these steps (assume your project root is `/scenmut`):

#### 1. **Prepare the Input Script Layout**

Organize input scripts under your configured `scriptDir`. Each app should be placed in a folder named: `<launch_activity>@<app_package>`. 

Example:

```
/scenmut/input/com.example.MainActivity@com.example.app/test_login.py
/scenmut/input/com.example.MainActivity@com.example.app/test_checkout.py
```

Each app folder should also include the target APK file used for install/uninstall during execution.

#### 2. **Create Your Runtime Config**

Copy and edit `config.example.yaml` (for example, save it as `config.yaml`), then update at least:

- `env.emulators`, `env.emulatorPath` (`env.emulators` can be a list for multi-device runs)
- `appium.serverUrl` and other Appium capability fields
- `scriptDir` (input root)
- `outputDir` (output root)

 You can tune modeling and graph-related options such as `maxExplorationEpochs`, `coverageThreshold`, `sameStateStrategy`, and `belongingStrategy`. Also, you can modify `mutation.maxPathLength`/`mutation.maxMutations` configs, and enable or disable MRs in `MRs`.

#### 3. **Run the Project**

Run ScenMut with your config (assuming the config file is at `./config.yaml`):

```
python main.py -f ./config.yaml
```

This will run the full workflow, including modeling, path augmentation, and evaluation.

Other common usage examples:

- Modeling only: `python main.py -f ./config.yaml -m`
- Path augmentation only: `python main.py -f ./config.yaml -a`
- Evaluation only: `python main.py -f ./config.yaml -ev`
- Skip evaluation: `python main.py -f ./config.yaml -s`
- Run only selected app package(s): `python main.py -f ./config.yaml -p com.example.app`
- Run on a specific device (must be listed in `env.emulators`): `python main.py -f ./config.yaml -d emulator-5554`
- View detailed help: `python main.py -h`

During execution, ScenMut produces per-app output folders with generated configs, logs, transition graph data, augmented scripts, and path augmentation reports.
