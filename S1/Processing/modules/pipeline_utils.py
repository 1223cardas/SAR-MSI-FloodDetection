from pathlib import Path

from dataclasses import dataclass
from .discovery import getWorkflow
from .snap import execute_command

@dataclass
class Msg:
	success: str = ""
	error: str = ""


def getMsg(mode: str) -> Msg | None:
	match(mode):
		case "singleProductProcessing":
			success = "Successfully processed product.\n"
			error = "Error processing product.\n"
		case "stackProducts":
			success = "Successfully stacked products.\n"
			error = "Error stacking products"
		case "createMask":
			success = "Successfully computed flood product.\n"
			error = "Error computing flood product"
	
	if success == "" and error == "":
		return None
	
	return Msg(success, error)


def _execute(cmd: list[str], mode: str) -> bool:
	msg = getMsg(mode)
	if msg is None:
		print("Incorrect mode. Stopping execution.")
		return False
	
	return execute_command(cmd, msg.success, msg.error)


def setupExecution(mode: str, arguments: dict, gptExec: list[str]):
	cmd = gptExec.copy()

	workflow = str(getWorkflow(mode))
	cmd.extend([workflow])	

	for key, val in arguments.items():
		cmd.extend([f"-P{key}={val}"])

	return _execute(cmd, mode)


def checkSuffixForFile(file: Path, sfx: str) -> tuple[Path, bool]:
	dim_file = file.with_suffix(sfx)

	if dim_file.exists():
		return dim_file, True
	
	return dim_file, False