from pathlib import Path
import shutil

from processorsImpl.processorBase import Processor
from S1.Processing import processing, paths, snap

class S1Processor(Processor):

	@property
	def name(self) -> str:
		return "s1"
	
	def __init__(self, **kwargs):
		super().__init__(**kwargs)

		terminal_width = shutil.get_terminal_size().columns

		print("=" * terminal_width)
		paths.check_directories()
		self.gpt_exec = snap.getExecutable()
		print("=" * terminal_width)

	
	def process(self, entry: dict | None) -> Path | None:
		self._progress(0.1, "Starting S1 processing...")
		result = processing.processProducts(self.gpt_exec, entry, self._progress_cb)
		self._progress(1, "S1 processing completed.")

		return result

	def preview(self) -> Path | None:
		self._progress(0.1, "Starting S1 preview...")
		result = processing.calculateAndDisplayResults()
		self._progress(1, "S1 preview completed.")

		return result
	
