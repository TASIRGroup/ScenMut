import subprocess
import platform


class Activity:
    @staticmethod
    def __parse_activity__(activity):
        """Parse Activity info."""
        """Format: mCurrentFocus=Window{<?component_hash> <?u0> <package_name>/<activity_name>}"""
        """The first two parameters are optional; if present, extract them with a regex."""
        """Match from the end backwards."""
        import re
        pattern = r'mCurrentFocus=Window\{(?:([\w\d]+)\s+)?(?:([\w\d]+)\s+)?([\w\d\-.]+)/([\w\d\-.]+)\}'

        match = re.search(pattern, activity)

        if match:
            # Parse matched fields.
            first = match.group(1)
            second = match.group(2)
            package_name = match.group(3)
            activity_name = match.group(4)

            # Handle assignment logic.
            if second:
                component_hash = first
                u0 = second
            else:  # If `second` is empty, then `first` is actually `u0`.
                component_hash = None
                u0 = first

            return {
                "component_hash": component_hash,
                "u0": u0,
                "package_name": package_name,
                "activity_name": activity_name
            }
        else:
            return None


    @staticmethod
    def get_current_activity(device_id = None):
        # Cross-platform command to filter for mCurrentFocus
        if platform.system() == "Windows":
            cmd = f"adb {'-s ' + device_id if device_id else ''} shell dumpsys window | findstr mCurrentFocus"
        else:
            cmd = f"adb {'-s ' + device_id if device_id else ''} shell dumpsys window | grep -E 'mCurrentFocus'"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5  # Add timeout to prevent hanging
        )

        if result.returncode == 0 or result.returncode == 1:
            activity = Activity.__parse_activity__(result.stdout)
            print(f"Current Activity: {activity}")
            return activity
        else:
            print(f"ADB Shell Error: {result.stderr}")
            return None

    @staticmethod
    def start_activity(activity, device_id=None):
        cmd = f"adb {'-s ' + device_id if device_id else ''} shell am start -n {activity['package_name']}/{activity['activity_name']}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Activity {activity.activity_name} started successfully")
        else:
            print("Start activity Error")
            print(result.stderr)
            exit(1)


if __name__ == "__main__":
    # Test the Activity class
    print(Activity.__parse_activity__("mCurrentFocus=Window{u0 com.example.app/com.example.app.MainActivity}"))
    print(Activity.start_activity(Activity.__parse_activity__("mCurrentFocus=Window{u0 com.example.app/com.example.app.MainActivity}")))