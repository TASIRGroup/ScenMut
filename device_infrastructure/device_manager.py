import os
import platform
import socket
from time import sleep

import threading
import yaml
import subprocess

from appium.options.android import UiAutomator2Options
from appium import webdriver

from device_infrastructure.actions import Screenshot, Package, Activity, Snapshot, Input

class DeviceManager:
    _PORT_SCAN_START = 9200
    _PORT_SCAN_END = 65535
    _allocated_ports: set = set()
    _port_alloc_lock = threading.Lock()
    # In multi-process mode, the shared port pool passed in by `main` (Manager.dict + Manager.Lock);
    # shared by all processes.
    _shared_ports_proxy = None
    _shared_port_lock = None


    def __init__(self, yaml_file_path, reset=None, no_screenshot=None, seperate_screenshot_folder=None, seperate_coverage_folder=None):
        yaml_file = open(yaml_file_path, "r")
        self.config = yaml.safe_load(yaml_file)
        yaml_file.close()

        # load from config file
        self.max_err_count = 5
        self.delay = self.config["delay"] if "delay" in self.config else 1
        self.desired_caps = {
            "platformName": self.config["appium"]["platformName"],
            "automationName": self.config["appium"]["automationName"],
            "deviceName": self.config["appium"]["deviceName"],
            "appPackage": self.config["appium"]["appPackage"],
            "appActivity": self.config["appium"]["appActivity"],
            "language": self.config["appium"]["language"],
            "locale": self.config["appium"]["locale"],
            "newCommandTimeout": 0,
        }
        self.device_id = self.config["env"]["device_id"]
        if self.device_id:
            self.desired_caps.update({"udid": self.device_id})
            system_port = self._calc_system_port(str(self.device_id))
            if platform.system() == "Windows":
                self.desired_caps.update({"systemPort": str(system_port)})
        self.reset = reset if reset is not None else self.config["reset"]
        # self.clean_old_sessions()
        self.options = UiAutomator2Options().load_capabilities(self.desired_caps)
        self.driver = webdriver.Remote(self.config["appium"]["serverUrl"], options=self.options)
        # Add noreset
        self.desired_caps.update({"noReset": True})
        self.options = UiAutomator2Options().load_capabilities(self.desired_caps)
        self.screenshot_dir = self.config["screenshotDir"]
        self.package_name = self.config["appium"]["appPackage"]
        self.activity_name = self.config["appium"]["appActivity"]
        if seperate_screenshot_folder is not None and not no_screenshot:
            self.screenshot_dir = os.path.join(self.screenshot_dir, seperate_screenshot_folder)
        self.screenshot = Screenshot(self.screenshot_dir, self.reset, no_screenshot)
        self.enabled_coverage_file = self.config["coverageFile"]
        self.seperate_coverage_folder = seperate_coverage_folder
        if self.enabled_coverage_file:
            self.coverage_file_dir = self.config["coverageFileDir"]
            self.jacoco_path = self.config["jacocoAgentPath"]
        self.is_quit = False

        print("DeviceManager Initialized.")

    @staticmethod
    def _is_port_available(port: int) -> bool:
        """Check whether a port is available (not currently in use)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return True
            except OSError:
                return False

    @classmethod
    def set_shared_port_pool(cls, shared_ports_proxy, shared_port_lock):
        """Set a shared multi-process port pool; called inside the worker by `run_on_all_devices`."""
        cls._shared_ports_proxy = shared_ports_proxy
        cls._shared_port_lock = shared_port_lock

    @staticmethod
    def _calc_system_port(udid: str) -> int:
        """
        Scan starting from `PORT_SCAN_START` and return the first available port that has
        not been allocated in this process (or globally when using a shared pool).
        In multi-process mode, it uses the shared port pool.
        """
        if DeviceManager._shared_ports_proxy is not None and DeviceManager._shared_port_lock is not None:
            with DeviceManager._shared_port_lock:
                for port in range(DeviceManager._PORT_SCAN_START, DeviceManager._PORT_SCAN_END + 1):
                    if port in DeviceManager._shared_ports_proxy:
                        continue
                    if DeviceManager._is_port_available(port):
                        DeviceManager._shared_ports_proxy[port] = True
                        return port
        else:
            with DeviceManager._port_alloc_lock:
                for port in range(DeviceManager._PORT_SCAN_START, DeviceManager._PORT_SCAN_END + 1):
                    if port in DeviceManager._allocated_ports:
                        continue
                    if DeviceManager._is_port_available(port):
                        DeviceManager._allocated_ports.add(port)
                        return port
        raise RuntimeError(
            f"No available port in range [{DeviceManager._PORT_SCAN_START}, {DeviceManager._PORT_SCAN_END}] for udid={udid}"
        )
    
    def reload_driver(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                old_driver = self.driver
                self.driver = webdriver.Remote(self.config["appium"]["serverUrl"], options=self.options)
                sleep(self.delay)
                old_driver.quit()
                sleep(self.delay)
                break

            except Exception as e:
                if e.msg == "A session is either terminated or not started":
                    print("[WARNING] Session already terminated, ignoring...")
                    break
                print(f"[WARNING] Failed to reload driver: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to reload driver after {self.max_err_count} attempts.")
        return self.driver

    def get_driver(self):
        return self.driver

    def start_package(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                Package.start_package(self.package_name, device_id=self.device_id)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to start package: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to start package after {self.max_err_count} attempts.")


    def get_current_activity(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                activity = Activity.get_current_activity(self.device_id)
                break
            except Exception as e:
                print(f"[WARNING] Failed to get current activity: {e}, retrying...")
                sleep(self.delay)
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to get current activity after {self.max_err_count} attempts.")
        return activity

    def start_activity(self, activity):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                Activity.start_activity(activity, self.device_id)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to start activity: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to start activity after {self.max_err_count} attempts.")

    def save_snapshot(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                Snapshot.create_snapshot(self.device_id)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to save snapshot: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

    def restore_snapshot(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                Snapshot.restore_snapshot(self.device_id)
                sleep(self.delay)
                self.reload_driver()
                break
            except Exception as e:
                print(f"[WARNING] Failed to restore snapshot: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

    def get_bounds_by_xpath(self, xpath):
        """
        Get bounds by xpath. This method will return none if failed.
        :param xpath:
        :return: bounds in (x1, y1, x2, y2) tuple
        """
        bounds = Input.get_bounds_by_xpath(self.driver, xpath)
        return bounds

    def click_by_coordinate(self, x, y):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                status = Input.click_by_coordinate(self.driver, x, y)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to click by coordinate: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

        return status

    def click_by_xpath(self, xpath):
        from device_infrastructure import DeviceInfraError
        try:
            status = Input.click_by_xpath(self.driver, xpath)
            sleep(self.delay)
        except Exception as e:
            raise DeviceInfraError(f"Failed to click by xpath.")

        return status

    def back(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                status = Input.back(self.driver)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to click back: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

        return status

    def hide_keyboard(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                status = Input.hide_keyboard(self.driver)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to hide keyboard: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

        return status

    def text_input(self, xpath, text):
        from device_infrastructure import DeviceInfraError
        try:
            status = Input.text_input(self.driver, xpath, text)
            Input.hide_keyboard(self.driver)
            sleep(self.delay)
        except Exception as e:
            raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

        return status

    def text_clear(self, xpath):
        from device_infrastructure import DeviceInfraError

        try:
            status = Input.text_clear(self.driver, xpath)
            sleep(self.delay)
        except Exception as e:
            raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

        return status

    def take_screenshot(self):
        from device_infrastructure import DeviceInfraError

        try:
            status = self.screenshot.take_screenshot(self.driver)
            sleep(self.delay)
        except Exception as e:
            status = None
            print(f"Failed to take screenshot: {str(e)}")

        return status

    def get_component_tree(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                component_tree = self.driver.page_source
                break
            except Exception as e:
                print(f"[WARNING] Failed to get component tree: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")
                sleep(self.delay)

        return component_tree

    @staticmethod
    def is_system_activity(activity) -> bool:
        if activity is None:
            return False

        if activity.get("package_name") == "com.google.android.permissioncontroller" and activity.get("activity_name").endswith("permission.ui.GrantPermissionsActivity"):
            return True
            # More system activities can be added here
        else:
            return False


    def get_state(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                state = self.driver.query_app_state(self.package_name)
                activity = self.get_current_activity()
                break
            except Exception as e:
                print(f"[WARNING] Failed to query app state: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")
                sleep(self.delay)

        if DeviceManager.is_system_activity(activity):
            return "running"

        if state == 3:
            return "background"
        elif state == 4:
            return "running"
        else:
            return "halted"


    def to_background(self, time):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                self.driver.background_app(time)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to send app to background: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")


    def terminate(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                self.driver.terminate_app(self.package_name)
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to terminate app: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")

    def activate(self):
        from device_infrastructure import DeviceInfraError

        err_count = 0
        while True:
            try:
                self.driver.activate_app(self.package_name)
                break
            except Exception as e:
                print(f"[WARNING] Failed to activate app: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save snapshot after {self.max_err_count} attempts.")
                sleep(self.delay)


    def quit(self):
        from device_infrastructure import DeviceInfraError

        if self.is_quit:
            return

        self.save_coverage_file(where=self.seperate_coverage_folder)

        err_count = 0
        while True:
            try:
                self.driver.quit()
                self.is_quit = True
                sleep(4) # wait for the driver to quit
                break
            except Exception as e:
                print(f"[WARNING] Failed to quit driver: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"[FATAL] Failed to quit driver after {self.max_err_count} attempts.")
                sleep(self.delay)

    @staticmethod
    def pull_coverage_file(package_name: str, coverage_file_dir: str, device_id: str = None, retry_delay: float = 2, max_retries: int = 5):
        import time
        import shutil
        from pathlib import Path
        from device_infrastructure import DeviceInfraError
        err_count = 0

        while True:
            try:
                # clean old coverage files and ensure dir
                if os.path.exists(coverage_file_dir):
                    shutil.rmtree(coverage_file_dir)
                os.makedirs(coverage_file_dir, exist_ok=True)

                # pull coverage file
                timestamp = int(time.time())
                temp_path = f"/sdcard/coverage_{timestamp}.ec"
                copy_command = f"adb {'-s ' + device_id if device_id else ''} shell run-as {package_name} cp files/coverage.ec {temp_path}"
                subprocess.run(copy_command, shell=True, check=False)
                coverage_file_path = str(((Path(coverage_file_dir)) / f"coverage_{timestamp}.ec").absolute())
                pull_command = f"adb {'-s ' + device_id if device_id else ''} pull {temp_path} {coverage_file_path}"
                subprocess.run(pull_command, shell=True, check=True)
                rm_command = f"adb {'-s ' + device_id if device_id else ''} shell rm {temp_path}"
                subprocess.run(rm_command, shell=True, check=True)
                print(f"[INFO] Coverage file saved to {coverage_file_dir}/coverage_{timestamp}.ec")
                sleep(retry_delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to pull coverage file: {e}, retrying...")
                err_count += 1
                if err_count > max_retries:
                    raise DeviceInfraError(f"Failed to pull coverage file after {max_retries} attempts.")
                sleep(retry_delay)

    def save_coverage_file(self, where=None):
        import time
        from pathlib import Path
        from device_infrastructure import DeviceInfraError

        if not self.enabled_coverage_file:
            print("[INFO] Coverage file saving is disabled.")
            return

        if where is not None:
            coverage_file_dir_path = Path(self.coverage_file_dir) / where
            coverage_file_dir_path.mkdir(parents=True, exist_ok=True)
        else:
            coverage_file_dir_path = Path(self.coverage_file_dir)

        err_count = 0
        while True:
            try:
                # Pull the coverage file from the device
                # Using:
                # adb shell "run-as <package_name> cp files/coverage.ec /sdcard/coverage.ec"
                # adb pull /sdcard/coverage.ec <coverage_ec_output_path>
                # adb shell "rm /sdcard/coverage.ec"
                timestamp = int(time.time())
                temp_path = f"/sdcard/coverage_{timestamp}.ec"
                copy_command = f"adb {'-s ' + self.device_id if self.device_id else ''} shell run-as {self.package_name} cp files/coverage.ec {temp_path}"
                subprocess.run(copy_command, shell=True, check=True)
                pull_command = f"adb {'-s ' + self.device_id if self.device_id else ''} pull {temp_path} {str(coverage_file_dir_path.absolute())}/coverage_{timestamp}.ec"
                subprocess.run(pull_command, shell=True, check=True)
                rm_command = f"adb {'-s ' + self.device_id if self.device_id else ''} shell rm {temp_path}"
                subprocess.run(rm_command, shell=True, check=True)
                print(f"[INFO] Coverage file saved to {self.coverage_file_dir}/coverage_{timestamp}.ec")
                sleep(self.delay)
                break
            except Exception as e:
                print(f"[WARNING] Failed to save coverage file: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to save coverage file after {self.max_err_count} attempts.")
                sleep(self.delay * 10)


    def remove_forward_by_port(self, port: int):
        command = f"adb {'-s ' + self.device_id if self.device_id else ''} forward --remove tcp:{port}"
        result = subprocess.run(command, shell=True, check=False)
        if result.returncode == 0:
            print(f"[INFO] Forward removed by port: {port}")
        else:
            print(f"[WARNING] Failed to remove forward by port: {command}")
        sleep(self.delay)

    def kill_task_using_specific_port(self, port: int):
        if platform.system() == "Windows":
            command = f"netstat -ano | findstr {port}"
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"[WARNING] Failed to find task using specific port: {command}")
                return
            lines = result.stdout.splitlines()
            print(lines)
            for line in lines:
                parts = line.split()
                pid = parts[1]
                kill_command = f"taskkill /F /PID {pid}"
                subprocess.run(kill_command, shell=True, check=True)
        elif platform.system() == "Linux":
            command = f"lsof -i :{port}"
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"[WARNING] Failed to find task using specific port: {command}")
                return
            lines = result.stdout.splitlines()
            for line in lines:
                parts = line.split()
                pid = parts[1]
                kill_command = f"kill -9 {pid}"
                subprocess.run(kill_command, shell=True, check=True)

    def clean_old_sessions(self):
        # adb -s fc92c246 shell am force-stop io.appium.uiautomator2.server
        # adb -s fc92c246 shell am force-stop io.appium.uiautomator2.server.test
        command1 = f"adb {'-s ' + self.device_id if self.device_id else ''} shell am force-stop io.appium.uiautomator2.server"
        command2 = f"adb {'-s ' + self.device_id if self.device_id else ''} shell am force-stop io.appium.uiautomator2.server.test"
        result1 = subprocess.run(command1, shell=True, check=False)
        result2 = subprocess.run(command2, shell=True, check=False)
        if result1.returncode == 0:
            print(f"[INFO] Old session 1 removed")
        else:
            print(f"[WARNING] Failed to remove old session 1: {command1}")
        if result2.returncode == 0:
            print(f"[INFO] Old session 2 removed")
        else:
            print(f"[WARNING] Failed to remove old session 2: {command2}")
        sleep(self.delay)

    def remove_forward(self):
        from device_infrastructure import DeviceInfraError
        err_count = 0
        while True:
            try:
                command = f"adb {'-s ' + self.device_id if self.device_id else ''} forward --remove-all"
                subprocess.run(command, shell=True, check=True)
                break
            except Exception as e:
                print(f"[WARNING] Failed to remove forward: {e}, retrying...")
                err_count += 1
                if err_count > self.max_err_count:
                    raise DeviceInfraError(f"Failed to remove forward after {self.max_err_count} attempts.")
                sleep(self.delay)