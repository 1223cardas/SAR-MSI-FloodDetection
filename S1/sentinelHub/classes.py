from dataclasses import dataclass, field
import json

@dataclass
class searchParams:
	bbox: list
	datetime: str
	collections: list
	limit: int

	def to_dict(self):
		return {
			"bbox": self.bbox,
			"datetime": self.datetime,
			"collections": self.collections,
			"limit": self.limit
		}


@dataclass
class LogEntry:
	place_query: str = ""
	place_name: str = ""
	bbox: list = field(default_factory=list)
	crisis_date: str = ""
	date_range: str = ""
	beforeId: str = ""
	afterId: str = ""

	@classmethod
	def from_csv_row(cls, row):
		return cls(
			place_query=row.get("place_query", ""),
			place_name=row.get("place_name", ""),
			bbox=json.loads(row.get("bbox") or "[]"),
			crisis_date=row.get("crisis_date", ""),
			date_range=row.get("date_range", ""),
			beforeId=row.get("beforeId", ""),
			afterId=row.get("afterId", "")
		)
	
	def to_dict(self):
		return {
			"place_query": self.place_query,
			"place_name": self.place_name,
			"bbox": json.dumps(self.bbox),
			"crisis_date": self.crisis_date,
			"date_range": self.date_range,
			"beforeId": self.beforeId,
			"afterId": self.afterId
		}


@dataclass
class Place:
	name: str
	lat: float
	lon: float


@dataclass
class Product:
	id: str = ""
	datetime: str = ""


@dataclass
class TimeFrame:
	start: str
	end: str