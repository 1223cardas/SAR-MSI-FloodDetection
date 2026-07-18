from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

@dataclass
class Product:
	name: str
	path: Path = Path()
	date: datetime = datetime.min
	
	def parseDate(self) -> str:
		"""Converts the product's acquisition datetime to the format used in SNAP band names: DDMmmYYYY (ex: 01Jan2020)."""
		return self.date.strftime("%d%b%Y")


	def extractDateFromProduct(self):
		# Assuming the product name format is something like "S1A_IW_GRDH_1SDV_20210101T123456_20210101T123456_012345_67890_ABCDE.SAFE"
		# The date is usually in the format YYYYMMDDTHHMMSS
		match = re.search(r"_(\d{8}T\d{6})_", self.name)
		if not match:
			raise ValueError(f"Could not parse acquisition time from: {self.name}")

		result = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
		self.date = result



class PromptCancelledError(RuntimeError):
    pass