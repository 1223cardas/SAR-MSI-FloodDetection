from datetime import datetime, timedelta

from .aclasses import TimeFrame, LogEntry
from . import aquisition_config
from mainconfig import input


def prompt_crisis_date() -> str:
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



def getTimeFrame(crisisDate: datetime, daysMargin) -> TimeFrame | None:
	try:
		margin = timedelta(days=daysMargin)
		start_date = (crisisDate - margin).strftime("%Y-%m-%dT%H:%M:%SZ")
		end_date = (crisisDate + margin).strftime("%Y-%m-%dT%H:%M:%SZ")

		return TimeFrame(start_date, end_date)
	except Exception as e:
		print(f"Error computing time frame: {e}")
		return None



def setDaysMargin() -> int:
	while True:
		margin_days = input(
				f"Enter days margin around crisis date (minimum default value=[{aquisition_config.DEFAULT_DAYS_MARGIN}days]):",
				expected_type=int
				)

		margin = int(margin_days) if margin_days else aquisition_config.DEFAULT_DAYS_MARGIN
		if margin <= 0:
			print("Margin must positive integer. Please try again.")
			continue
		if margin < aquisition_config.DEFAULT_DAYS_MARGIN:
			print(f"Margin too small. Using default value of {aquisition_config.DEFAULT_DAYS_MARGIN} days.")
			margin = aquisition_config.DEFAULT_DAYS_MARGIN
		if margin > 20:
			print("Margin too large. Choose a smaller window of days.")
			continue
		return margin

def getTimeSeries(entry: LogEntry):
	while True:
		crisis_date = prompt_crisis_date()
		if not crisis_date:
			print("Error parsing crisis date. Please try again.")
			continue

		entry.crisis_date = crisis_date

		break