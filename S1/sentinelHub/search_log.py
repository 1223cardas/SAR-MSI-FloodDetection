import csv
from S1.sentinelHub.classes import LogEntry
from pathlib import Path
from typing import Optional
from S1.sentinelHub.config import LOG_PATH

fieldnames = [
	"place_query",
	"place_name",
	"bbox",
	"crisis_date",
	"date_range",
	"beforeId",
	"afterId"
]

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



def choose_log_entry() -> Optional[LogEntry]:
	entries = load_search_log(LOG_PATH)
	if not entries:
		print("No log entries found.")
		return None

	print("Available searches:")
	for idx, entry in enumerate(entries, start=1):
		label = entry.place_name
		before_id = entry.beforeId
		after_id = entry.afterId
		print(
			f"\t[{idx}] {label}\n"
			f"\t | crisis {entry.crisis_date}\n"
			f"\t | before: {before_id}\n"
			f"\t | after: {after_id}\n"
		)

	while True:
		raw = input("Select a search entry number (or Enter to cancel): ").strip()
		if not raw:
			return None
		if not raw.isdigit():
			print("Invalid selection. Use a number from the list.")
			continue
		idx = int(raw)
		if idx < 1 or idx > len(entries):
			print("Selection out of range.")
			continue
		return entries[idx - 1]
	

	
def append_search_log(entry: LogEntry):
	LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

	is_new = not LOG_PATH.exists()
	
	with LOG_PATH.open("a", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		
		if is_new: writer.writeheader()
		writer.writerow(entry.to_dict())

	print("Log saved to:", LOG_PATH)