from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Callable, Optional

from S2 import discovery as s2_discovery
from S2 import pipeline as s2_pipeline
from S2 import preview as s2_preview

from S1.Processing import processing as s1_processing
from S1.Processing import snap, paths


@dataclass
class ProcessorResult:
    name: str
    output_path: Path | None = None


class Processor(ABC):
    """
    Classe base para processadores de satélite.

    Gere o progress_callback, stop_event e pause_event de forma uniforme,
    expondo métodos utilitários para as subclasses.
    """

    def __init__(
        self,
        progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None,
        stop_event: Optional[threading.Event] = None,
        pause_event: Optional[threading.Event] = None,
    ) -> None:
        self._progress_cb = progress_callback or (lambda *_: None)
        self._stop_event  = stop_event
        self._pause_event = pause_event

    # --- Utilitários de controlo ---

    def _progress(self, value: float, msg: Optional[str] = None) -> None:
        self._progress_cb(value, msg)

    def _is_cancelled(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    def _wait_if_paused(self) -> bool:
        """
        Bloqueia enquanto estiver em pausa.
        Devolve True se foi cancelado durante a espera, False caso contrário.
        """
        while self._pause_event is not None and self._pause_event.is_set():
            if self._is_cancelled():
                return True
            self._pause_event.wait(timeout=0.2)
        return self._is_cancelled()

    def _check(self) -> bool:
        """Verifica cancelamento e pausa. Devolve True se deve abortar."""
        if self._is_cancelled():
            return True
        return self._wait_if_paused()

    def _abort(self, msg: str = "Cancelado") -> ProcessorResult:
        self._progress(0.0, msg)
        return ProcessorResult(name=self._name, output_path=None)

    @property
    @abstractmethod
    def _name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def run(self, run_processing: bool, view: bool) -> ProcessorResult:
        raise NotImplementedError


class S1Processor(Processor):

    @property
    def _name(self) -> str:
        return "s1"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        print("=" * 96)
        self.paths    = paths.check_directories()
        self.gpt_exec = snap.getExecutable()
        print("=" * 96)

    def run(self, run_processing: bool, view: bool, entry = None) -> ProcessorResult:
        output_path = None

        try:
            self._progress(0.0, "Iniciando S1")

            if run_processing:
                if self._check():
                    return self._abort("Cancelado antes de iniciar S1")

                self._progress(0.1, "A executar SNAP (S1)")
                output_path = s1_processing.processProducts(self.gpt_exec, entry, self._progress_cb)
                self._progress(0.9, "SNAP concluído")

            if view:
                if self._check():
                    return self._abort("Cancelado antes de visualizar S1")
                output_path = s1_processing.calculateAndDisplayResults()

            # Fallback: procura o TIF mais recente no disco
            if run_processing and not output_path:
                out_dir = Path("S1/output")
                tifs = list(out_dir.glob("*_flood.tif")) if out_dir.exists() else []
                if tifs:
                    output_path = max(tifs, key=lambda p: p.stat().st_mtime)

            self._progress(1.0, "S1 concluído")
            return ProcessorResult(name=self._name, output_path=output_path)

        except Exception:
            self._progress(0.0, "Erro S1")
            raise

class S2Processor(Processor):

    @property
    def _name(self) -> str:
        return "s2"

    def __init__(
        self,
        imagens_dir: str = "Imagens",
        out_dir: str = "ndwi_work",
        preview: bool = False,
        threshold: float | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.imagens_dir = imagens_dir
        self.out_dir     = out_dir
        self.preview     = preview
        self.threshold   = threshold

    def run(self, run_processing: bool, view: bool) -> ProcessorResult:
        output_path = None

        try:
            self._progress(0.0, "Iniciando S2")

            if run_processing:
                if self._check():
                    return self._abort("Cancelado antes de iniciar S2")

                self._progress(0.05, "A descobrir produtos S2")
                before, after = s2_discovery.discover_all_band_pairs(self.imagens_dir)

                if self._check():
                    return self._abort("Cancelado após descoberta S2")

                self._progress(0.2, "A executar pipeline S2")
                s2_pipeline.run_pipeline(
                    before,
                    after,
                    self.out_dir,
                    preview=self.preview,
                    threshold=self.threshold,
                    progress_callback=self._progress_cb,
                    stop_event=self._stop_event,
                    pause_event=self._pause_event,
                )

                if self._check():
                    return self._abort("Cancelado após pipeline S2")

                self._progress(0.9, "Pipeline S2 concluído")

                candidate = Path(self.out_dir) / "flood.tif"
                if candidate.exists():
                    output_path = candidate

            if view and not output_path:
                candidate = Path(self.out_dir) / "flood.tif"
                if not candidate.exists():
                    raise FileNotFoundError(f"S2 flood.tif não encontrado em '{self.out_dir}'")
                output_path = candidate

            if self.preview and not run_processing:
                try:
                    s2_preview.preview_outputs_only(self.out_dir, threshold=self.threshold)
                    preview_candidate = Path(self.out_dir) / "preview.png"
                    if preview_candidate.exists():
                        output_path = preview_candidate
                except Exception as e:
                    print("S2 preview falhou:", e)
                    raise

            self._progress(1.0, "S2 concluído")
            return ProcessorResult(name=self._name, output_path=output_path)

        except Exception:
            self._progress(0.0, "Erro S2")
            raise