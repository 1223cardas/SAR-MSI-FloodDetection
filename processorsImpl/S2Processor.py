from pathlib import Path

from processorsImpl.processorBase import Processor
from S2 import workflow, preview, config

class S2Processor(Processor):

	@property
	def name(self):
		return "s2"
	
	def __init__(self, threshold: float | None = None, **kwargs):
		super().__init__(**kwargs)
		self.threshold = threshold


	def process(self, entry: dict | None) -> Path | None:
		self._progress(0.1, "Starting S2 processing...")
		result = workflow.processProducts(entry, self.threshold, self._progress_cb)
		self._progress(1, "S2 processing completed.")
		return result


	def preview(self) -> Path | None:
		self._progress(0.1, "Starting S2 preview...")
		preview.preview_outputs_only(threshold=self.threshold, flood_path=None)
		candidate = Path(config.OUT_DIR) / "preview.png"
		result = candidate if candidate.exists() else None
		self._progress(1, "S2 preview completed.")
		return result