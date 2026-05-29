from modules.classes import LogEntry
from modules.regiongeocoding import getRegion
from modules.regiontimestamp import getTimeSeries
from modules.request import requestProducts
from modules.download import queueProductsForDownload
from modules.search_log import saveLogEntry
from pathlib import Path
from modules.config import ROOT_DIR


def aquireProducts() -> list[Path]:
	entry = LogEntry()

	# Set place_query, place_name, bbox
	getRegion(entry)

	# Set crisis_date, date_range
	getTimeSeries(entry)

	# Set beforeId, afterId
	[before, after] = requestProducts(entry)

	# Save log entry
	saveLogEntry(entry)
	
	products = [before, after]
	return queueProductsForDownload(products)


def main():
	downloaded_paths = aquireProducts()
	print("Downloaded products:")
	for path in downloaded_paths:
		print(path)

if __name__ == "__main__":
	main()