from pathlib import Path
import csv

from .aclasses import LogEntry
from .acquisition_config import *
from mainconfig import LOG_PATH


def saveLogEntry(entry: LogEntry):
	LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

	# If file doesn't exist yet, create it with header and write the entry.
	if not LOG_PATH.exists():
		writeToFile(entry, is_new=True)
		return

	with LOG_PATH.open("r", newline="", encoding="utf-8") as csvRead:
		reader = csv.DictReader(csvRead)
		for row in reader:
			currRow: LogEntry = LogEntry.from_csv_row(row)
			if currRow == entry:
				print("Log entry already exists, skipping save.")
				return

	writeToFile(entry, is_new=False)


def updateLogEntry(entryDict: dict, item: dict):
	entry = LogEntry.to_entry(entryDict)

	rows = []
	with LOG_PATH.open("r", newline="", encoding="utf-8") as csvRead:
		reader = csv.DictReader(csvRead)

		for row in reader:
			currRow: LogEntry = LogEntry.from_csv_row(row)

			if currRow == entry:
				row.update(item)

			rows.append(row)

	with LOG_PATH.open("w", newline="", encoding="utf-8") as csvWrite:
		writer = csv.DictWriter(csvWrite, fieldnames=CSV_FIELDNAMES)

		writer.writeheader()
		writer.writerows(rows)


def writeToFile(entry: LogEntry, is_new: bool):
	with LOG_PATH.open("a", newline="", encoding="utf-8") as csvWrite:
		writer = csv.DictWriter(csvWrite, fieldnames=CSV_FIELDNAMES)
		if is_new: writer.writeheader()
		writer.writerow(entry.to_dict())
		print("Log saved to:", LOG_PATH)
		return


def load_search_log() -> list[LogEntry]:
	if not LOG_PATH.exists():
		print("Log file not found:", LOG_PATH)
		return []
	
	entries: list[LogEntry] = []
	with LOG_PATH.open("r", newline="", encoding="utf-8") as handle:
		reader = csv.DictReader(handle)

		list_of_csv = list(reader)

		for row in list_of_csv:
			entry = LogEntry.from_csv_row(row)
			entries.append(entry)

	return entries
