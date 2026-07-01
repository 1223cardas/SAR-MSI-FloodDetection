import queue
import threading

import customtkinter as ctk

from .config import RunState, FIELD_DEFAULTS
from .ui_builder import UIBuilder
from .runner import RunController
from .streams import StreamManager

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        # --- Estado partilhado ---
        self.mode            = ctk.StringVar(value="all")
        self.input_entry_var = ctk.StringVar()
        self.input_queue     = queue.Queue()

        self._field_entries   = {}
        self._field_values    = dict(FIELD_DEFAULTS)
        self._last_status_text = "Pronto"

        self.run_state   = RunState.IDLE
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()

        # --- Colaboradores ---
        self.runner = RunController(self)
        self.ui     = UIBuilder(self, self._switch_mode)
        self.ui.build()

        self._streams = StreamManager(
            log_callback=self.ui.append_log,
            input_queue=self.input_queue,
            stop_event=self._stop_event,
            status_callback=self.ui.set_prompt_waiting,
        )
        self._streams.redirect()

    # ------------------------------------------------------------------
    # Navegação entre modos
    # ------------------------------------------------------------------

    def _switch_mode(self, mode: str):
        self.mode.set(mode)
        self.ui.render(mode)

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------

    def run_selected(self):
        self._capture_field_values()
        self.ui.set_running_controls()
        self.ui.set_status("A executar...")
        self.ui.progress.set(0.0)
        self._last_status_text = "A executar..."
        self.runner.start()

    # ------------------------------------------------------------------
    # Input interativo
    # ------------------------------------------------------------------

    def _submit_input(self):
        value = self.input_entry_var.get()
        self.input_queue.put(value)
        self.ui.append_log(f"{value}\n")
        self.input_entry_var.set("")
        self.ui.clear_prompt_waiting()

    # ------------------------------------------------------------------
    # Gestão de campos
    # ------------------------------------------------------------------

    def _capture_field_values(self):
        for attr, entry in self._field_entries.items():
            self._field_values[attr] = entry.get()

    def _get_field_value(self, attr: str) -> str:
        return self._field_values.get(attr, "")

    @staticmethod
    def _clean_path_text(value: str) -> str:
        return value.strip().strip('"').strip("'")