from Aquisition.modules.classes import LogEntry
from Aquisition.modules.regiongeocoding import getRegion
from Aquisition.modules.regiontimestamp import getTimeSeries
from Aquisition.modules.request import requestProducts
from Aquisition.modules.download import queueProductsForDownload
from Aquisition.modules.search_log import saveLogEntry, load_search_log
from mainconfig import input
from pathlib import Path


def ellipsize(s: str, left: int = 15, right: int = 12, placeholder: str = '(...)') -> str:
	if s is None:
		return s
	s = str(s)
	# If the string is short enough, return as-is
	if len(s) <= left + right + len(placeholder):
		return s
	return s[:left] + placeholder + s[-right:]


def aquireProducts(productType: str = "sentinel-1-grd") -> list[Path]:
	entry = LogEntry(collection=[productType])

	# Set place_query, place_name, bbox
	getRegion(entry)

	# Set crisis_date, date_range
	getTimeSeries(entry)

	# Set beforeId, afterId
	[before, after] = requestProducts(entry, productType)

	# Save log entry
	saveLogEntry(entry)

	products = [before, after]
	return queueProductsForDownload(products)



def aquireProductsFromLog() -> list[Path]:
	entries: list[LogEntry] = load_search_log()
	if not entries:
		print("No log entries found.")
		return []
	
	if not any(entry.collection == ["sentinel-1-grd"] for entry in entries):
		print("No log entries found for the specified product type.")
		return []


	for idx, entry in enumerate(entries, start=1):
		print(f"\n[{idx}]:\tPlace: {entry.place_name}")
		print(f" |\tCrisis Date: {entry.crisis_date}")
		print(f" |\tBBox: {entry.bbox}")
	print(f" |\tBefore Product ID: {ellipsize(entry.beforeId)}")
	print(f" |\tAfter Product ID: {ellipsize(entry.afterId)}\n")

	choice = input("Enter the number of the log entry to process (or 'q' to quit): ").strip()
	if choice.lower() == 'q':
		print("Exiting.")
		return []
	
	try:
		selected_entry = entries[int(choice) - 1]
	except (IndexError, ValueError):
		print("Invalid choice. Exiting.")
		return []
	
	products = selected_entry.productFromIds()
	return queueProductsForDownload(products)



def main():
	downloaded_paths = aquireProducts()
	print("Downloaded products:")
	for path in downloaded_paths:
		print(path)

if __name__ == "__main__":
	main()