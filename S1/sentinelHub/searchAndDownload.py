from S1.sentinelHub.catalog import getTimeFrame, getProducts, select_products_around_date, filter_features_fully_containing_bbox
from S1.sentinelHub.config import DEFAULT_AOI_KM, DEFAULT_DAYS_MARGIN, DEFAULT_SEARCH_LIMIT
from S1.sentinelHub.session import initializeSession, initializeSessionPasswordGrant
from S1.sentinelHub.cli import chooseRegion, prompt_crisis_date, prompt_numeric
from S1.sentinelHub.download import resolve_products_uuids, download_products
from S1.sentinelHub.search_log import append_search_log, choose_log_entry
from S1.sentinelHub.classes import searchParams, LogEntry
from types import SimpleNamespace
from S1.sentinelHub.aoi import compute_bbox
from typing import Optional

def runProductDiscovery():
	print("Sentinel 1 Product Search and Processing")
	entry = LogEntry()

	entry.place_query, place = chooseRegion()
	entry.place_name = place.name

	size_km = prompt_numeric("AOI size in km (square side)", DEFAULT_AOI_KM)
	bbox = compute_bbox(place.lat, place.lon, size_km)
	entry.bbox = bbox

	crisis_date = prompt_crisis_date()
	days_margin = prompt_numeric("Days margin around crisis date", DEFAULT_DAYS_MARGIN)

	date_range = getTimeFrame(crisis_date, days_margin)
	entry.crisis_date = crisis_date
	entry.date_range = date_range

	session = initializeSession()
	query = searchParams(
		bbox=bbox,
		datetime=date_range,
		collections=["sentinel-1-grd"],
		limit=DEFAULT_SEARCH_LIMIT,
	)

	features = getProducts(query.to_dict(), session)
	filtered_features = filter_features_fully_containing_bbox(features, bbox)

	if not filtered_features:
		print("No products found for the given query.")
		return
	
	before_item, after_item = select_products_around_date(filtered_features, crisis_date)

	if not before_item.id or not after_item.id:
		print("Could not find suitable products around the crisis date.")
		return

	entry.beforeId = before_item.id
	entry.afterId = after_item.id

	print(
		f"Selected products:\n"
		f"\tBefore: {before_item.id} ({before_item.datetime})\n"
		f"\tAfter: {after_item.id} ({after_item.datetime})\n"
	)

	append_search_log(entry)

	confirm = input("Do you want to download the products and proceed with the flood mask creation? [y/n]: ").strip().lower()
	if confirm in ("y", "yes"):
		run_from_log(entry)


def run_from_log(entry: Optional[LogEntry] = None):
	if entry is None:
		entry = choose_log_entry()
		if entry is None:
			return

		if not entry.beforeId or not entry.afterId:
			print("Log entry is missing one or both product IDs.")
			return

		if not entry.bbox:
			print("Log entry has no bounding box.")
			return

	session = initializeSessionPasswordGrant()

	before = SimpleNamespace(id=entry.beforeId)
	after = SimpleNamespace(id=entry.afterId)
	found_map, missing = resolve_products_uuids([before.id, after.id], session)

	if missing:
		print(f"Could not resolve the following product names to UUIDs: {missing}")
		print("Aborting download. Check product availability or search log.")
		return

	before.uuid = found_map[before.id]
	after.uuid = found_map[after.id]
	download_products([before, after], session)

def print_terminal():
	while True:
		print("\nMenu:")
		print("1. Run product discovery")
		print("2. Run from search log")
		print("3. Exit")

		choice = input("Choose an option: ").strip()
		if choice == "1":
			runProductDiscovery()
		elif choice == "2":
			run_from_log()
		elif choice == "3":
			print("Exiting.")
			break
		else:
			print("Invalid choice. Please try again.")

def main():
	print_terminal()


if __name__ == "__main__":
	main()
