from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from S1 import scriptS1, utilS1
from S2 import discovery as s2_discovery
from S2 import pipeline as s2_pipeline


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
        self.paths = utilS1.check_directories()
        self.gpt = utilS1.getExecutable()
        self.gpt_exec = [str(self.gpt), "-x", "-J-Xms256m", "-J-Xmx4G"]

    def run(self, run_processing: bool, view: bool) -> ProcessorResult:
        if run_processing:
            scriptS1.processProducts(self.gpt_exec, self.paths)

        output_path = None
        if view:
            output_path = self._ensure_visualization()

        return ProcessorResult(name="s1", output_path=output_path)

    def _ensure_visualization(self) -> Path:
        out_dir = Path(self.paths["out"])
        tifs = list(out_dir.glob("floodImage*.tif"))
        if tifs:
            return tifs[0]

        scriptS1.calculateAndDisplayResults(self.gpt_exec, self.paths)
        tifs = list(out_dir.glob("floodImage*.tif"))
        if not tifs:
            raise FileNotFoundError("Failed to produce S1 flood TIF in S1/out/")
        return tifs[0]


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

        return ProcessorResult(name="s2", output_path=output_path)
