from .modules.aclasses import LogEntry
from .modules.regiongeocoding import getRegion
from .modules.regiontimestamp import getTimeSeries
from .modules.request import requestProducts
from .modules.download import queueProductsForDownload
from .modules.search_log import saveLogEntry, load_search_log
from mainconfig import input


def ellipsize(s: str, left: int = 15, right: int = 12, placeholder: str = '(...)') -> str:
	if s is None:
		return s
	s = str(s)
	# If the string is short enough, return as-is
	if len(s) <= left + right + len(placeholder):
		return s
	return s[:left] + placeholder + s[-right:]



def printEntries(entries: list[LogEntry], entryType: str) -> str:
	while True:
		for idx, entry in enumerate(entries, start=1):
			print(f"\n[{idx}]:\tPlace: {entry.place_name}")
			print(f" |\tCrisis Date: {entry.crisis_date}")
			print(f" |\tBBox: {entry.bbox}")
			print(f" |\tBefore Product ID: {ellipsize(entry.beforeId)}")
			print(f" |\tAfter Product ID: {ellipsize(entry.afterId)}\n")

		choice = input("Enter the number of the log entry to process ('q' to quit, 0 to create a new entry): ")
		if choice.lower() == 'q':
			print("Exiting.")
			return ""
		
		if choice == '0':
			print("Creating a new log entry.")
			acquireProducts(entryType)
			return printEntries(load_search_log(), entryType)
		
		try:
			if int(choice) not in range(1, len(entries) + 1):
				print("Invalid choice. Try again.")
				continue

			return choice
		except ValueError:
			print("Invalid input. Please enter a number corresponding to a log entry or 'q' to quit.")



def acquireProducts(productType: str = "sentinel-1-grd") -> LogEntry:
	entry = LogEntry(collection=productType)

	# Set place_query, place_name, bbox
	getRegion(entry)

	# Set crisis_date, date_range
	getTimeSeries(entry)

	# Set beforeId, afterId
	[before, after] = requestProducts(entry, productType)

	# Save log entry
	saveLogEntry(entry)

	products = [before, after]
	queueProductsForDownload(products)

	return entry


def acquireEntryFromLog(entryType: str) -> LogEntry | None:
	entries: list[LogEntry] = load_search_log()

	if not entries:
		print("No log entries found. Running product acquisition to create a new log entry.")
		return acquireProducts(entryType)

	typeEntries: list[LogEntry] = [entry for entry in entries if entry.collection == entryType]
	if not any(entry.collection == entryType for entry in typeEntries):
		print("No log entries found for the specified product type.")
		return acquireProducts(entryType)

	idx = printEntries(typeEntries, entryType)
	if idx == "": exit(0)
    
	try:
		selected_entry = typeEntries[int(idx) - 1]
	except (IndexError, ValueError):
		print("Invalid choice. Exiting.")
		return None

	queueProductsForDownload(selected_entry.productFromIds())

	return selected_entry


def main():
	acquireProducts()


if __name__ == "__main__":
	main()