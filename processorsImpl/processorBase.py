from typing import Callable, Optional, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import threading


@dataclass
class ProcessorResult:
	name: str
	output_path: Path | None = None


class Processor(ABC):
		
	def __init__(
		self,
		progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None,
		stop_event: Optional[threading.Event] = None,
	):
		self._progress_cb = progress_callback or (lambda *_: None)
		self._stop_event = stop_event

	def _progress(self, value, message=None):
		self._progress_cb(value, message)

	def _cancelled(self):
		return self._stop_event is not None and self._stop_event.is_set()

	def _check(self):
		return self._cancelled()

	def _abort(self, message):
		self._progress(0, message)
		return ProcessorResult(
			self.name,
			None,
		)

	# --------------------------------------------------------
	# Template Method
	# --------------------------------------------------------

	def run(
		self,
		run_processing: bool,
		view: bool,
		entry: dict | None = None
	) -> ProcessorResult:

		try:
			self._progress(0, f"Starting {self.name.upper()}")
			output = None

			if run_processing:
				if self._check():
					return self._abort("Cancelled")

				output = self.process(entry)
				
			if view:
				if self._check():
					return self._abort("Cancelled")

				preview = self.preview()

				if preview is not None:
					output = preview

			self._progress(1, "Finished")
			return ProcessorResult(
				self.name,
				output,
			)

		except Exception:
			self._progress(0, f"{self.name.upper()} failed")
			raise

	# --------------------------------------------------------
	# Hooks
	# --------------------------------------------------------

	@property
	@abstractmethod
	def name(self) -> str:
		...

	@abstractmethod
	def process(self, entry: dict | None) -> Path | None:
		...

	@abstractmethod
	def preview(self) -> Path | None:
		...
