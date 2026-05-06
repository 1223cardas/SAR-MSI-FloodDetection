from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from S1 import scriptS1, utilS1
from S2 import discovery as s2_discovery
from S2 import pipeline as s2_pipeline
from S2 import preview as s2_preview


@dataclass
class ProcessorResult:
    name: str
    output_path: Path | None = None


class Processor(ABC):
    @abstractmethod
    def run(self, run_processing: bool, view: bool) -> ProcessorResult:
        raise NotImplementedError


class S1Processor(Processor):
    def __init__(self) -> None:
        print("================================================================================================")
        self.paths = utilS1.check_directories()
        self.gpt = utilS1.getExecutable()
        self.gpt_exec = utilS1.getGPTCommand(self.gpt)
        print("================================================================================================")

    def run(self, run_processing: bool, view: bool) -> ProcessorResult:
        if run_processing:
            scriptS1.processProducts(self.gpt_exec, self.paths)

        output_path = None
        if view:
            output_path = scriptS1.calculateAndDisplayResults(self.gpt_exec, self.paths)

        return ProcessorResult(name="s1", output_path=output_path)


class S2Processor(Processor):
    def __init__(self, imagens_dir: str = "Imagens", out_dir: str = "ndwi_work", preview: bool = False, threshold: float | None = None) -> None:
        self.imagens_dir = imagens_dir
        self.out_dir = out_dir
        self.preview = preview
        self.threshold = threshold

    def run(self, run_processing: bool, view: bool) -> ProcessorResult:
        output_path = None
        if run_processing:
            b3b, b8b, b3a, b8a = s2_discovery.auto_find_band_paths(self.imagens_dir)
            s2_pipeline.run_pipeline(
                b3b,
                b8b,
                b3a,
                b8a,
                self.out_dir,
                preview=self.preview,
                threshold=self.threshold,
            )

        if view:
            candidate = Path(self.out_dir) / "flood.tif"
            if not candidate.exists():
                raise FileNotFoundError(f"S2 flood.tif not found in {self.out_dir}")
            output_path = candidate

        if self.preview and not run_processing:
            try:
                s2_preview.preview_outputs_only(self.out_dir, threshold=self.threshold)
                preview_candidate = Path(self.out_dir) / "preview.png"
                if preview_candidate.exists():
                    output_path = preview_candidate
            except FileNotFoundError:
                raise
            except Exception as e:
                print("S2 preview failed:", e)

        return ProcessorResult(name="s2", output_path=output_path)
