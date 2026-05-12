from pathlib import Path
import os
import subprocess


def getExecutable() -> list[str]:
    """Locate the SNAP GPT executable by checking the SNAP_DIRECTORY environment variable."""
    print("Locating SNAP GPT executable...", end=" ")
    snap_dir = os.getenv("SNAP_DIRECTORY")

    # If SNAP_DIRECTORY is set, check if gpt.exe exists there
    if snap_dir:
        candidate = Path(snap_dir)
        gpt_exec = candidate / "bin" / "gpt.exe"

        if gpt_exec.exists():
            print(f"Found at: {gpt_exec}")
            # Return the command list to execute GPT
            return getGPTCommand(gpt_exec)

        raise FileNotFoundError(
            f"SNAP_DIRECTORY is set to '{snap_dir}', but gpt.exe was not found.\n"
            "Verify SNAP_DIRECTORY in your .env points to the SNAP installation root."
        )

    raise FileNotFoundError(
        "SNAP_DIRECTORY environment variable is not set.\n"
        "Please set SNAP_DIRECTORY in your .env to your SNAP installation directory,\n"
        "or install SNAP at the default location: C:\\Program Files\\snap."
    )


def getGPTCommand(gptExec: Path) -> list[str]:
    """Build the command list to execute SNAP GPT with the specified executable and memory settings."""
    return [str(gptExec), "-x", "-J-Xms1G", "-J-Xmx4G"]


def execute_command(cmd: list[str], success_message: str, error_message: str) -> None:
    try:
        subprocess.run(cmd, check=True)
        print(success_message)
    except subprocess.CalledProcessError as e:
        print(f"{error_message}\n{e.stderr}")
