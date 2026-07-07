from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import threading
from typing import Any, Callable, Optional

from Acquisition.modules.search_log import updateLogEntry
from S2 import discovery as s2_discovery
from S2 import pipeline as s2_pipeline
from S2 import preview as s2_preview

from S1.Processing import processing as s1_processing
from S1.Processing import snap, paths


@dataclass
class ProcessorResult:
    name: str
    output_path: Path | None = None


def _slugify_filename(value: str) -> str:
    text = re.sub(r"[^\w.-]+", "_", (value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "s2"


def _entry_timestamp(entry: dict | None = None) -> str:
    if entry:
        processed_at = str(entry.get("processed_at", "")).strip()
        if processed_at:
            return processed_at
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def build_s2_output_path(out_dir: str | Path, entry: dict | None = None, threshold: float | None = None) -> Path:
    base_dir = Path(out_dir)
    if not entry:
        return base_dir / "flood.tif"

    place_query = _slugify_filename(str(entry.get("place_query", "")))
    timestamp = _slugify_filename(_entry_timestamp(entry))
    stem = f"{place_query}_{timestamp}_flood"
    return base_dir / f"{stem}.tif"


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

    def run(self, run_processing: bool, view: bool, entry: dict | None = None) -> ProcessorResult:
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
        out_dir: str = "S2/output",
        preview: bool = False,
        threshold: float | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.out_dir     = out_dir
        self.preview     = preview
        self.threshold   = threshold

    def _cached_output(self, entry: dict | None = None) -> Path:
        return build_s2_output_path(self.out_dir, entry=entry, threshold=self.threshold)

    def _resolve_entry(self, entry: dict | None) -> dict | None:
        if entry is not None:
            return entry

        resolved = s2_discovery.getEntry()
        if resolved is None:
            return None
        return resolved if isinstance(resolved, dict) else resolved.to_dict()

    def _ensure_processing_timestamp(self, entry: dict) -> dict:
        if str(entry.get("processed_at", "")).strip():
            return entry

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        updated_entry = dict(entry)
        updated_entry["processed_at"] = timestamp

        try:
            updateLogEntry(entry, {"processed_at": timestamp})
        except Exception:
            pass

        return updated_entry

    def run(self, run_processing: bool, view: bool, entry = None) -> ProcessorResult:
        output_path = None
        resolved_entry = self._resolve_entry(entry)
        if resolved_entry is not None:
            resolved_entry = self._ensure_processing_timestamp(resolved_entry)

        cached_output = self._cached_output(resolved_entry)

        try:
            self._progress(0.0, "Iniciando S2")

            if run_processing:
                if self._check():
                    return self._abort("Cancelado antes de iniciar S2")

                if cached_output.exists():
                    self._progress(1.0, "S2 concluído")
                    print(f"[s2] a usar ficheiro existente: {cached_output}")
                    return ProcessorResult(name=self._name, output_path=cached_output)

                self._progress(0.1, "A descobrir produtos S2")
                before, after = s2_discovery.discover_all_band_pairs("downloads", resolved_entry)

                if self._check():
                    return self._abort("Cancelado após descoberta S2")

                self._progress(0.2, "A executar pipeline S2")
                s2_pipeline.run_pipeline(
                    before,
                    after,
                    self.out_dir,
                    output_name=cached_output.name,
                    preview=self.preview,
                    threshold=self.threshold,
                    progress_callback=self._progress_cb,
                    stop_event=self._stop_event,
                    pause_event=self._pause_event,
                )

                if self._check():
                    return self._abort("Cancelado após pipeline S2")

                self._progress(0.9, "Pipeline S2 concluído")

                if cached_output.exists():
                    output_path = cached_output

            if view and not output_path:
                if not cached_output.exists():
                    raise FileNotFoundError(f"S2 output não encontrado em '{self.out_dir}'")
                output_path = cached_output

            if self.preview and not run_processing:
                try:
                    s2_preview.preview_outputs_only(self.out_dir, threshold=self.threshold, flood_path=cached_output)
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