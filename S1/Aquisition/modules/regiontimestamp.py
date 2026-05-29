from datetime import datetime, timedelta
from .classes import TimeFrame, LogEntry
from . import config


def prompt_crisis_date() -> str:
	while True:
		crisis_date = input("Crisis date (YYYY-MM-DD or YYYY-MM-DD-hh): ").strip()

		if not crisis_date:
			print("Crisis date cannot be empty.")
			continue

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



def getTimeSeries(entry: LogEntry):
	while True:
		crisis_date = prompt_crisis_date()
		if not crisis_date:
			print("Error parsing crisis date. Please try again.")
			continue

		margin_days = input(
			f"Enter days margin around crisis date (Press Enter for default value [{config.DEFAULT_DAYS_MARGIN}days]): "
			).strip()
		
		margin = int(margin_days) if margin_days else config.DEFAULT_DAYS_MARGIN

		crisis_date_dt = datetime.strptime(crisis_date, "%Y-%m-%dT%H:%M:%SZ") 
		timeFrame = getTimeFrame(crisis_date_dt, margin)

		if timeFrame is None:
			print("Error computing time frame. Please try again.")
			continue

		entry.crisis_date = crisis_date
		entry.date_range = timeFrame.toString()

		break