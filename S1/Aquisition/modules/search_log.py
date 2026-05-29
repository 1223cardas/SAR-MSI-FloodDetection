from .classes import LogEntry
from pathlib import Path
from . import config
import csv


def saveLogEntry(entry: LogEntry):
	log_path = config.LOG_PATH
	log_path.parent.mkdir(parents=True, exist_ok=True)
	
	is_new = not log_path.exists()
	
	with log_path.open("a", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=config.CSV_FIELDNAMES)
		
		if is_new: writer.writeheader()
		writer.writerow(entry.to_dict())



def load_search_log(log_path: Path) -> list[LogEntry]:
	if not log_path.exists():
		print("Log file not found:", log_path)
		return []
	
	entries: list[LogEntry] = []
	with log_path.open("r", newline="", encoding="utf-8") as handle:
		reader = csv.DictReader(handle)

		list_of_csv = list(reader)

		for row in list_of_csv:
			entry = LogEntry.from_csv_row(row)
			entries.append(entry)

	return entries
	

