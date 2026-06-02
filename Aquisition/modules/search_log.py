from pathlib import Path
import csv

from Aquisition.modules.aclasses import LogEntry
from Aquisition.modules import aquisition_config
from mainconfig import LOG_PATH


def saveLogEntry(entry: LogEntry):
	log_path = LOG_PATH
	log_path.parent.mkdir(parents=True, exist_ok=True)

	# If file doesn't exist yet, create it with header and write the entry.
	if not log_path.exists():
		writeToFile(entry, log_path, is_new=True)
		return

	# File exists: check for duplicates then append if new
	with log_path.open("r", newline="", encoding="utf-8") as csvRead:
		reader = csv.DictReader(csvRead)
		for row in reader:
			currRow: LogEntry = LogEntry.from_csv_row(row)
			if currRow == entry:
				print("Log entry already exists, skipping save.")
				return

	writeToFile(entry, log_path, is_new=False)



def writeToFile(entry: LogEntry, log_path: Path, is_new: bool):
	with log_path.open("a", newline="", encoding="utf-8") as csvWrite:
		writer = csv.DictWriter(csvWrite, fieldnames=aquisition_config.CSV_FIELDNAMES)
		if is_new: writer.writeheader()
		writer.writerow(entry.to_dict())
		print("Log saved to:", log_path)
		return


def load_search_log() -> list[LogEntry]:
	log_path = LOG_PATH
	
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
