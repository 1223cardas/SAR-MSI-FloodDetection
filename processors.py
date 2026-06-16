from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import time
import threading
from typing import Any, Callable, Optional

from S2 import discovery as s2_discovery
from S2 import pipeline as s2_pipeline
from S2 import preview as s2_preview

from S1.Processing import processing as s1_processing
from S1.Processing import snap, paths

from mainconfig import OUTPUT_DIR

@dataclass
class ProcessorResult:
    name: str
    output_path: Path | None = None


class Processor(ABC):
    @abstractmethod
    def run(
        self,
        run_processing: bool,
        view: bool,
        progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None,
        stop_event: Optional[threading.Event] = None,
        pause_event: Optional[threading.Event] = None,
    ) -> ProcessorResult:
        raise NotImplementedError


class S1Processor(Processor):
    def __init__(self) -> None:
        print("================================================================================================")
        self.paths = paths.check_directories()
        self.gpt_exec = snap.getExecutable()
        print("================================================================================================")

    def run(
        self,
        run_processing: bool,
        view: bool,
        progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None,
        stop_event: Optional[threading.Event] = None,
        pause_event: Optional[threading.Event] = None,
    ) -> ProcessorResult:
        output_path = None
        try:
            if progress_callback:
                progress_callback(0.0, "Iniciando S1")

            # If requested, run SNAP processing (this is usually blocking)
            if run_processing:
                # allow cancel/pause before heavy call
                if stop_event and stop_event.is_set():
                    if progress_callback:
                        progress_callback(0.0, "Cancelado antes de iniciar S1")
                    return ProcessorResult(name="s1", output_path=None)

                while pause_event and pause_event.is_set():
                    time.sleep(0.2)
                    if stop_event and stop_event.is_set():
                        if progress_callback:
                            progress_callback(0.0, "Cancelado durante pausa")
                        return ProcessorResult(name="s1", output_path=None)

                if progress_callback:
                    progress_callback(0.1, "A executar SNAP (S1)")

                output_path = s1_processing.processProducts(self.gpt_exec)

                if progress_callback:
                    progress_callback(0.6, "SNAP concluído")

            if view:
                # allow pause/stop before view
                while pause_event and pause_event.is_set():
                    time.sleep(0.2)
                    if stop_event and stop_event.is_set():
                        if progress_callback:
                            progress_callback(0.0, "Cancelado durante pausa")
                        return ProcessorResult(name="s1", output_path=None)

                output_path = s1_processing.calculateAndDisplayResults()

            # If processProducts didn't return a path, try to find existing tif
            if run_processing and not output_path:
                out_dir = Path("S1/output")
                if out_dir.exists():
                    tifs = list(out_dir.glob("*_flood.tif"))
                    if tifs:
                        output_path = max(tifs, key=lambda p: p.stat().st_mtime)

            if run_processing and not output_path:
                # Isto tem que ser mudado depois
                fallback_path = Path(r"C:\Users\yoyoo\Desktop\SAR-MSI-FloodDetection\S1\output\Kherson_2023-06-06T04-59-59Z_flood.tif")
                if fallback_path.exists():
                    output_path = fallback_path

            if progress_callback:
                progress_callback(1.0, "S1 concluído")

            return ProcessorResult(name="s1", output_path=output_path)
        except Exception:
            if progress_callback:
                progress_callback(0.0, "Erro S1")
            raise

class S2Processor(Processor):
    def __init__(self, imagens_dir: str = "Imagens", out_dir: str = "ndwi_work", preview: bool = False, threshold: float | None = None) -> None:
        self.imagens_dir = imagens_dir
        self.out_dir = out_dir
        self.preview = preview
        self.threshold = threshold

    def run(
        self,
        run_processing: bool,
        view: bool,
        progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None,
        stop_event: Optional[threading.Event] = None,
        pause_event: Optional[threading.Event] = None,
    ) -> ProcessorResult:
        output_path = None

        def _cancelled() -> bool:
            return stop_event is not None and stop_event.is_set()

        def _wait_if_paused() -> bool:
            while pause_event is not None and pause_event.is_set():
                if _cancelled():
                    return True
                threading.Event().wait(0.2)
            return _cancelled()

        try:
            if progress_callback:
                progress_callback(0.0, "Iniciando S2")

            if run_processing:
                if _cancelled():
                    return ProcessorResult(name="s2", output_path=None)
                if _wait_if_paused():
                    return ProcessorResult(name="s2", output_path=None)

                if progress_callback:
                    progress_callback(0.05, "Descobrindo produtos S2")
                before, after = s2_discovery.discover_all_band_pairs(self.imagens_dir)

                if _cancelled():
                    return ProcessorResult(name="s2", output_path=None)
                if progress_callback:
                    progress_callback(0.15, "Produtos S2 descobertos")

                if _wait_if_paused():
                    return ProcessorResult(name="s2", output_path=None)

                if progress_callback:
                    progress_callback(0.2, "A executar pipeline S2")

                s2_pipeline.run_pipeline(
                    before,
                    after,
                    self.out_dir,
                    preview=self.preview,
                    threshold=self.threshold,
                    progress_callback=progress_callback,
                    stop_event=stop_event,
                    pause_event=pause_event,
                )

                if _cancelled():
                    return ProcessorResult(name="s2", output_path=None)
                if progress_callback:
                    progress_callback(0.9, "Pipeline S2 concluído")

                candidate = Path(self.out_dir) / "flood.tif"
                if candidate.exists():
                    output_path = candidate

            if view and not output_path:
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

            if progress_callback:
                progress_callback(1.0, "S2 concluído")

            return ProcessorResult(name="s2", output_path=output_path)
        except Exception:
            if progress_callback:
                progress_callback(0.0, "Erro S2")
            raise