from .modules.aclasses import LogEntry, Product
from .modules.regiongeocoding import getRegion
from .modules.regiontimestamp import getTimeSeries
from .modules.request import requestProducts
from .modules.download import queueProductsForDownload
from .modules.search_log import saveLogEntry, load_search_log
from .modules.aquisition_config import S1_COLLECTION, S2_COLLECTION
from mainconfig import input


def ellipsize(s: str, left: int = 15, right: int = 12, placeholder: str = '(...)') -> str:
	if s is None:
		return s
	s = str(s)
	if len(s) <= left + right + len(placeholder):
		return s
	return s[:left] + placeholder + s[-right:]


def printEntries(entries: list[LogEntry], entryType: str, mode: str = "single") -> LogEntry | str:
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
			exit(1)
		
		if choice == '0':
			print("Creating a new log entry.")
			if mode == "auto":
				acquireProductsS1_S2()
				updated_entries = [e for e in load_search_log() if e.collection in (S1_COLLECTION, S2_COLLECTION)]
			else:
				acquireProducts(entryType)
				updated_entries = [e for e in load_search_log() if e.collection == entryType]
			# Recarrega o log e recomeça o loop
			return printEntries(updated_entries, entryType, mode)

		try:
			idx_int = int(choice)
			if idx_int not in range(1, len(entries) + 1):
				print("Invalid choice. Try again.")
				continue

			return entries[idx_int - 1]
		except ValueError:
			print("Invalid input. Please enter a number corresponding to a log entry or 'q' to quit.")


def acquireProducts(productType: str) -> LogEntry:
	entry = LogEntry(collection=productType)
	getRegion(entry)
	getTimeSeries(entry)
	products = requestProducts(entry, productType)
	if len(products) != 2:
		print("Product acquisition failed. No products will be queued for download.")
		saveLogEntry(entry)
		return entry

	saveLogEntry(entry)
	queueProductsForDownload(products)
	return entry


def acquireProductsS1_S2() -> tuple[LogEntry, LogEntry]:
	entries: list[LogEntry] = load_search_log()

	if entries:
		# Agrupa por região (place_name + crisis_date como chave)
		from collections import defaultdict
		region_map: dict[str, dict[str, LogEntry]] = defaultdict(dict)

		for entry in entries:
			region_key = f"{entry.place_name}|{entry.crisis_date}"
			region_map[region_key][entry.collection] = entry

		# Filtra apenas regiões com ambas as coleções
		complete_regions = {
			key: cols
			for key, cols in region_map.items()
			if S1_COLLECTION in cols and S2_COLLECTION in cols
		}

		if complete_regions:
			print("\nRegiões com dados de ambos os satélites encontradas:\n")
			region_list = list(complete_regions.items())

			for idx, (key, cols) in enumerate(region_list, start=1):
				s1 = cols[S1_COLLECTION]
				print(f"[{idx}]:\tPlace: {s1.place_name}")
				print(f" |\tCrisis Date: {s1.crisis_date}")
				print(f" |\tBBox: {s1.bbox}")
				print(f" |\tS1 Before: {ellipsize(cols[S1_COLLECTION].beforeId)}")
				print(f" |\tS1 After:  {ellipsize(cols[S1_COLLECTION].afterId)}")
				print(f" |\tS2 Before: {ellipsize(cols[S2_COLLECTION].beforeId)}")
				print(f" |\tS2 After:  {ellipsize(cols[S2_COLLECTION].afterId)}\n")

			while True:
				choice = input("Escolhe uma região (0 para criar nova entrada, 'q' para sair): ")

				if choice == 'q':
					exit(0)

				if choice == '0':
					break  # segue para nova aquisição

				try:
					idx_int = int(choice)
					if idx_int not in range(1, len(region_list) + 1):
						print("Escolha inválida. Tenta novamente.")
						continue

					_, cols = region_list[idx_int - 1]
					s1_entry = cols[S1_COLLECTION]
					s2_entry = cols[S2_COLLECTION]

					products = s1_entry.productFromIds() + s2_entry.productFromIds()
					queueProductsForDownload(products)

					return s1_entry, s2_entry
				except ValueError:
					print("Input inválido. Insere um número ou 'q'.")


	print("A iniciar nova aquisição para S1 e S2...")
	entry = LogEntry()
	getRegion(entry)
	getTimeSeries(entry)

	s1_entry = setupEntry(entry, S1_COLLECTION)
	s2_entry = setupEntry(entry, S2_COLLECTION)

	queueProductsForDownload(s1_entry.productFromIds() + s2_entry.productFromIds())

	return s1_entry, s2_entry


def setupEntry(entry: LogEntry, collection: str) -> LogEntry:
	resultEntry = entry
	resultEntry.collection = collection
	print(f"Checking for products using {collection}")

	products = requestProducts(resultEntry, collection)
	saveLogEntry(resultEntry)
	if len(products) != 2:
		print(f"No products found for collection {collection}. Skipping download queue.")
		return LogEntry()

	return resultEntry


def acquireEntryFromLog(entryType: str) -> LogEntry | None:
	entries: list[LogEntry] = load_search_log()

	if not entries:
		print("No log entries found. Running product acquisition to create a new log entry.")
		return acquireProducts(entryType)

	typeEntries: list[LogEntry] = [e for e in entries if e.collection == entryType]

	if not typeEntries:
		print("No log entries found for the specified product type.")
		return acquireProducts(entryType)

	entry = printEntries(typeEntries, entryType, mode="single")
	if isinstance(entry, str):
		return None

	try:
		selected_entry = entry
	except (IndexError, ValueError):
		print("Invalid choice. Exiting.")
		return None

	queueProductsForDownload(selected_entry.productFromIds())
	return selected_entry


def acquireEntryFromLogWithBoth(entryTypes: list[str]) -> LogEntry | None:
	entries: list[LogEntry] = load_search_log()

	if not entries:
		print("No log entries found. Running product acquisition to create a new log entry.")
		acquireProductsS1_S2()
		entries = load_search_log()  # Recarrega após aquisição

	# Filtra entradas que pertençam a qualquer uma das coleções pedidas
	typeEntries: list[LogEntry] = [e for e in entries if e.collection in entryTypes]

	if not typeEntries:
		print("No log entries found for the specified product types. Queueing product acquisition...")
		acquireProductsS1_S2()
		entries = load_search_log()
		typeEntries = [e for e in entries if e.collection in entryTypes]

	if not typeEntries:
		print("Still no entries found after acquisition. Exiting.")
		return None

	# Usa o primeiro tipo como label para o menu (só para display)
	label = entryTypes[0] if entryTypes else ""
	entry = printEntries(typeEntries, label, mode="auto")
	if isinstance(entry, str):
		return None

	try:
		selected_entry = entry
	except (IndexError, ValueError):
		print("Invalid choice. Exiting.")
		return None

	queueProductsForDownload(selected_entry.productFromIds())
	return selected_entry
