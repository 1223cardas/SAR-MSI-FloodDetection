from collections import defaultdict
from copy import deepcopy

from .modules.search_log import saveLogEntry, load_search_log
from .modules.download import queueProductsForDownload
from .modules.regiontimestamp import getTimeSeries
from .modules.regiongeocoding import getRegion
from .modules.acquisition_config import input
from .modules.request import requestProducts
from .modules.aclasses import LogEntry
from .modules.utils import *

from common import Product, PromptCancelledError, S1_COLLECTION, S2_COLLECTION

from mainconfig import OUTPUT_DIR


def getEntry(collection_name: str) -> dict:
	print("Discovering products...")
	csvEntry = acquireEntryFromLog(collection_name)

	if csvEntry is None:
		raise FileNotFoundError(
			f"No products found in {OUTPUT_DIR}.\n"
			"Please run the acquisition process first to create log entries."
		)

	return csvEntry.to_dict()


def discoverProducts(entry: dict) -> list:
	bef = Product(entry["beforeId"])
	aft = Product(entry["afterId"])

	products = [bef, aft]
	if not all(p.name for p in products):
		raise ValueError(
			"Both 'before' and 'after' product IDs must be present in the log entry. "
			"Please check the log and ensure both products are listed."
		)

	downloads = list(OUTPUT_DIR.iterdir())

	for p in products:
		p.extractDateFromProduct()
		for file in downloads:
			if file.name.startswith(p.name):
				p.path = file

	if not all(getattr(p, "path", None) is not None for p in products):
		raise FileNotFoundError(
			"Could not find both product files in the output directory. "
			"Please ensure the products are present and try again."
		)

	return products


def _getList(entries: list[LogEntry], mode: str) -> list:
	res = []
	if mode == "single":
		res = entries
		displayEntries(entries)
	elif mode == "auto":
		region_map: dict[str, dict[str, LogEntry]] = defaultdict(dict)

		for entry in entries:
			region_key = f"{entry.place_name}|{entry.crisis_date}"
			region_map[region_key][entry.collection] = entry

		complete_regions = {
			key: cols
			for key, cols in region_map.items()
			if S1_COLLECTION in cols and S2_COLLECTION in cols
		}
		res = list(complete_regions.items())
		displayEntriesS1S2(res)
	
	return res


def _printEntries(entries: list[LogEntry], entryTypes: list[str], mode: str = "single") -> LogEntry | tuple[LogEntry, LogEntry]:
	while True:
		entries_list = _getList(entries, mode)

		choice = input("Enter the number of the log entry to process ('q' to quit, 0 to create a new entry): ")
		if choice.lower() == 'q':
			print("Exiting.")
			raise PromptCancelledError("User requested program exit via console menu.")
		
		if choice == '0':
			print("Creating a new log entry.")
			if mode == "auto":
				acquireProductsS1_S2()
			else:
				acquireProducts(entryTypes[0])
			
			# Reload and continue the loop seamlessly with updated entries
			entries = [e for e in load_search_log() if e.collection in entryTypes]
			continue

		try:
			idx_int = int(choice)
			if idx_int not in range(1, len(entries_list) + 1):
				print("Invalid choice. Try again.")
				continue

			selected = entries_list[idx_int - 1]

			if mode == "auto":
				_, cols = selected
				return cols[S1_COLLECTION], cols[S2_COLLECTION]
			
			return selected

		except ValueError:
			print("Invalid input. Please enter a number corresponding to a log entry or 'q' to quit.")


def _setupEntry(entry: LogEntry, collection: str) -> LogEntry:
	resultEntry = deepcopy(entry)
	resultEntry.collection = collection
	print(f"Checking for products using {collection}")

	products = requestProducts(resultEntry, collection)
	saveLogEntry(resultEntry)
	if len(products) != 2:
		print(f"No products found for collection {collection}. Skipping download queue.")
		return LogEntry()

	return resultEntry


def acquireProducts(productType: str) -> LogEntry:
	entry = LogEntry(collection=productType)
	getRegion(entry)
	getTimeSeries(entry)

	entry = _setupEntry(entry, productType)

	queueProductsForDownload(entry.productFromIds())
	return entry


def acquireProductsS1_S2() -> tuple[LogEntry, LogEntry]:
	entry = LogEntry()
	getRegion(entry)
	getTimeSeries(entry)

	s1_entry = _setupEntry(entry, S1_COLLECTION)
	s2_entry = _setupEntry(entry, S2_COLLECTION)

	queueProductsForDownload(s1_entry.productFromIds() + s2_entry.productFromIds())
	return s1_entry, s2_entry


def _getEntryFromLog(entryTypes: list[str], auto_pair: bool = False) -> LogEntry | tuple[LogEntry, LogEntry]:
	mode = "auto" if auto_pair else "single"

	# Consolidate log checking and product acquisition loop
	while True:
		entries = load_search_log()
		type_entries = [e for e in entries if e.collection in entryTypes]

		if type_entries:
			if mode == "auto":
				# Verify that at least one complete S1/S2 pair actually exists before proceeding
				region_map = defaultdict(dict)
				for entry in type_entries:
					region_key = f"{entry.place_name}|{entry.crisis_date}"
					region_map[region_key][entry.collection] = entry
				
				has_pairs = any(S1_COLLECTION in cols and S2_COLLECTION in cols for cols in region_map.values())
				if not has_pairs:
					print("No complete S1/S2 pairs found. Running acquisition...")
					acquireProductsS1_S2()
					continue
			break

		print("No log entries found for the specified product type(s). Running acquisition...")
		if len(entryTypes) > 1:
			acquireProductsS1_S2()
		else:
			acquireProducts(entryTypes[0])

	selected_entry = _printEntries(type_entries, entryTypes, mode=mode)
	
	if isinstance(selected_entry, tuple):
		bef, aft = selected_entry
		queueProductsForDownload(bef.productFromIds() + aft.productFromIds())
	elif selected_entry:
		queueProductsForDownload(selected_entry.productFromIds())
	
	return selected_entry


def acquireEntryFromLog(entryType: str) -> LogEntry | None:
	entry = _getEntryFromLog([entryType])
	if not isinstance(entry, LogEntry):
		return None
	return entry


def acquireEntryFromLogWithBoth() -> tuple[LogEntry, LogEntry] | None:
	entries = _getEntryFromLog([S1_COLLECTION, S2_COLLECTION], auto_pair= True)
	if isinstance(entries, LogEntry):
		return None
	return entries