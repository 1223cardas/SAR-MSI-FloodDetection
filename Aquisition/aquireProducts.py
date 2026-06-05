from Aquisition.modules.aclasses import LogEntry
from Aquisition.modules.regiongeocoding import getRegion
from Aquisition.modules.regiontimestamp import getTimeSeries
from Aquisition.modules.request import requestProducts
from Aquisition.modules.download import queueProductsForDownload
from Aquisition.modules.search_log import saveLogEntry, load_search_log
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
			if entry.collection == entryType:
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
			aquireProducts(entryType)
			return printEntries(load_search_log(), entryType)
		
		try:
			if int(choice) not in range(1, len(entries) + 1):
				print("Invalid choice. Try again.")
				continue

			return choice
		except ValueError:
			print("Invalid input. Please enter a number corresponding to a log entry or 'q' to quit.")



def aquireProducts(productType: str = "sentinel-1-grd") -> LogEntry:
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


def aquireEntryFromLog(entryType: str) -> LogEntry | None:
    entries: list[LogEntry] = load_search_log()
    
    if not entries:
        print("No log entries found. Running product acquisition to create a new log entry.")
        return aquireProducts(entryType[0] if isinstance(entryType, list) else entryType)
    
    # Extrai a string real caso o entryType tenha vindo dentro de uma lista
    actual_type = entryType[0] if isinstance(entryType, list) else entryType
    
    # Correção da comparação: agora compara string com string
    if not any(entry.collection == actual_type for entry in entries):
        print("No log entries found for the specified product type.")
        return aquireProducts(actual_type)
    
    # Passa o tipo correto em formato string para a listagem
    idx = printEntries(entries, actual_type)
    if idx == "": exit(0)
    
    try:
        selected_entry = entries[int(idx) - 1]
    except (IndexError, ValueError):
        print("Invalid choice. Exiting.")
        return None

    queueProductsForDownload(selected_entry.productFromIds())

    return selected_entry


def main():
	aquireProducts()


if __name__ == "__main__":
	main()