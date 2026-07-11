from .aclasses import LogEntry
from .acquisition_config import S1_COLLECTION, S2_COLLECTION


def displayEntries(entries: list[LogEntry]):
	for idx, entry in enumerate(entries, start=1):
		print(f"\n[{idx}]:\tPlace: {entry.place_name}")
		print(f" |\tCrisis Date: {entry.crisis_date}")
		print(f" |\tBBox: {entry.bbox}")
		print(f" |\tBefore Product ID: {ellipsize(entry.beforeId)}")
		print(f" |\tAfter Product ID: {ellipsize(entry.afterId)}\n")


def displayEntriesS1S2(region_list):
	for idx, (_, cols) in enumerate(region_list, start=1):
		s1 = cols[S1_COLLECTION]
		print(f"[{idx}]:\tPlace: {s1.place_name}")
		print(f" |\tCrisis Date: {s1.crisis_date}")
		print(f" |\tBBox: {s1.bbox}")
		print(f" |\tS1 Before: {ellipsize(cols[S1_COLLECTION].beforeId)}")
		print(f" |\tS1 After:  {ellipsize(cols[S1_COLLECTION].afterId)}")
		print(f" |\tS2 Before: {ellipsize(cols[S2_COLLECTION].beforeId)}")
		print(f" |\tS2 After:  {ellipsize(cols[S2_COLLECTION].afterId)}\n")


def ellipsize(s: str, left: int = 15, right: int = 12, placeholder: str = '(...)') -> str:
	if s is None:
		return s
	s = str(s)
	if len(s) <= left + right + len(placeholder):
		return s
	return s[:left] + placeholder + s[-right:]