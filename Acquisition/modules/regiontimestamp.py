from datetime import datetime, timedelta

from .aclasses import TimeFrame, LogEntry
from .acquisition_config import *


def _prompt_crisis_date() -> str:
	while True:
		crisis_date = input(
			"Insert crisis date (YYYY-MM-DD or YYYY-MM-DD-hh):")
		
		# Try parsing with hour first: YYYY-MM-DD-HH
		try:
			d = datetime.strptime(crisis_date, "%Y-%m-%d-%H")
			# set minutes and seconds to 59 to include the whole hour
			return datetime(d.year, d.month, d.day, d.hour, 59, 59).strftime("%Y-%m-%dT%H:%M:%SZ")
		except ValueError:
			# Try parsing date-only: YYYY-MM-DD
			try:
				d = datetime.strptime(crisis_date, "%Y-%m-%d")
				return datetime(d.year, d.month, d.day, 12, 59, 59).strftime("%Y-%m-%dT%H:%M:%SZ")
			except ValueError:
				print("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD-hh.")


def getTimeFrame(crisisDate: datetime, daysMargin: int) -> TimeFrame | None:
	try:
		margin = timedelta(days=daysMargin)
		start_date = (crisisDate - margin).strftime("%Y-%m-%dT%H:%M:%SZ")
		end_date = (crisisDate + margin).strftime("%Y-%m-%dT%H:%M:%SZ")

		return TimeFrame(start_date, end_date)
	except Exception as e:
		print(f"Error computing time frame: {e}")
		return None


def getTimeSeries(entry: LogEntry):
	while True:
		crisis_date = _prompt_crisis_date()
		if not crisis_date:
			print("Error parsing crisis date. Please try again.")
			continue

		entry.crisis_date = crisis_date

		break