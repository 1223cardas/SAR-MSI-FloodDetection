from pathlib import Path
import os
import subprocess
import platform

GPT = "gpt.exe" if platform.system() == "Windows" else "gpt"

def getExecutable() -> list[str]:
    """Locate the SNAP GPT executable by checking the SNAP_DIRECTORY environment variable."""
    print("Locating SNAP GPT executable...", end=" ")
    snap_dir = os.getenv("SNAP_DIRECTORY")

    # If SNAP_DIRECTORY is set, check if gpt.exe exists there
    if snap_dir:
        candidate = Path(snap_dir)
        gpt_exec = candidate / "bin" / GPT

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
    return [str(gptExec), "-x", "-J-Xms1G", "-J-Xmx4G", "-q", "4"]


def execute_command(
    cmd: list[str],
    success_message: str,
    error_message: str
) -> bool:
    print(f"Executing command: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        print(f"Could not launch GPT: {e}")
        return False

    out = proc.stdout
    assert out is not None

    for chunk in iter(lambda: out.read(1), ""):
        print(chunk, end="", flush=True)

    proc.wait()

    if proc.returncode != 0:
        print(f"\n{error_message}")
        print(f"GPT exited with code {proc.returncode}")
        return False

    print(success_message)
    return True
