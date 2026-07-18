from datetime import datetime
from pathlib import Path
from typing import Callable

from .shared_config import S1_COLLECTION, S2_COLLECTION

def checkEntryInOutput(entry: dict, build_output_func: Callable[[str], Path] | None = None) -> tuple[str, str, Path | None]:
	entry_collection = entry.get("collection", "")
	stored_date: str = entry.get("processed_at", "")

	dt_str = format(datetime.now(), '%Y-%m-%d_%H-%M-%S')
	new_naming = f"{entry.get('place_query')}_{dt_str}_flood"

	if stored_date == "":
		return new_naming, dt_str, None

	entry_naming = f"{entry.get('place_query')}_{stored_date}_flood"
	
	expected_results = []
	if build_output_func is not None:
		if entry_collection == S1_COLLECTION:
			expected_tif = build_output_func(entry_naming + ".tif")
			expected_data = build_output_func(entry_naming + ".data")
			expected_dim = build_output_func(entry_naming + ".dim")
			expected_results = [expected_tif, expected_data, expected_dim]

		elif entry_collection == S2_COLLECTION:
			expected_tif = build_output_func(entry_naming + ".tif")
			expected_results = [expected_tif]
	else:
		return new_naming, dt_str, None

	filecount = 0
	for f in expected_results:
		if f.exists():
			filecount += 1

	if filecount == 0:
		return new_naming, dt_str, None

	if filecount == len(expected_results):
		return entry_naming, stored_date, expected_results[0]
	else:
		return entry_naming, stored_date, None
