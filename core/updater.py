import subprocess


class Updater:
    @staticmethod
    def check_yt_dlp_update():
        try:
            import pkg_resources
        except Exception:
            return None

        try:
            installed = pkg_resources.get_distribution("yt-dlp").version
            result = subprocess.run(
                ["pip", "index", "versions", "yt-dlp"],
                capture_output=True,
                text=True,
            )
            if "versions:" not in result.stdout:
                return None
            latest = result.stdout.split("versions:")[1].split(",")[0].strip()
            return {
                "installed": installed,
                "latest": latest,
                "update_available": installed != latest,
            }
        except Exception:
            return None

    @staticmethod
    def update_yt_dlp():
        result = subprocess.run(
            ["pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
