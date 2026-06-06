from pathlib import Path
import builtins

ROOT_DIR = Path(__file__).resolve().parent # Acquisition/ folder
OUTPUT_DIR = ROOT_DIR / "downloads"
AQUISTION_DIR = ROOT_DIR / "Acquisition"
LOG_PATH = AQUISTION_DIR / "search_log.csv"


CLI_PROMPT = "SAR-MSI-FloodDetection> "

def input(prompt: str = "", expected_type: type = str):
	print(prompt, end="\n")
	while True:
		user_input = builtins.input(CLI_PROMPT).strip()
		# print(f"User input: '{user_input}' (type: {type(user_input).__name__})")

		if not user_input: continue

		try:
			result = expected_type(user_input)
			# print(f"Parsed input: {result} (type: {type(result).__name__})")
			return result
		except ValueError:
			print(f"Invalid input. Expected a value of type {expected_type.__name__}. Please try again.")
			