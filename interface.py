import customtkinter as ctk
from tkinter import filedialog
from processors import S1Processor, S2Processor
from Combined.combine import fuse_flood_outputs
from pathlib import Path
import threading
import sys
import io
import queue
from enum import Enum

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------------------------
# Stream Redirector for stdout/stderr
# ---------------------------------------------------------------------------
class _StreamRedirector(io.TextIOBase):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def write(self, text):
        if text:
            self._callback(text)
        return len(text) if text else 0

    def flush(self):
        pass

    def isatty(self):
        return True


# ---------------------------------------------------------------------------
# Interactive stdin reader with queue
# ---------------------------------------------------------------------------
class _InteractiveInputReader(io.TextIOBase):
    def __init__(self, input_queue, stop_event=None, status_callback=None):
        super().__init__()
        self.input_queue = input_queue
        self.stop_event = stop_event
        self.status_callback = status_callback

    def _notify_waiting(self):
        if self.status_callback:
            self.status_callback("A aguardar entrada do utilizador...")

    def readline(self, size=-1):
        """Blocking read line from input queue - waits indefinitely for user input."""
        self._notify_waiting()
        try:
            # Poll so cancel can interrupt a blocked prompt.
            while True:
                if self.stop_event is not None and self.stop_event.is_set():
                    raise PromptCancelledError()
                try:
                    line = self.input_queue.get(block=True, timeout=0.2)
                    break
                except queue.Empty:
                    continue
            # Ensure line ends with newline
            return line if line.endswith("\n") else line + "\n"
        except queue.Empty:
            # Should not happen with timeout=None, but just in case
            return "\n"

    def read(self, size=-1):
        return self.readline(size)

    def isatty(self):
        return True


# ---------------------------------------------------------------------------
# Parameter layouts per mode
# ---------------------------------------------------------------------------
MODE_CONFIG = {
    "all": {
        "title": "Pipeline Completo",
        "fields": [
            ("Pasta Sentinel-2", "s2_dir"),
            ("Output S2",        "s2_out"),
            ("Threshold",        "threshold"),
            ("S1 TIF",           "s1_tif"),
            ("S2 TIF",           "s2_tif"),
            ("Output final",     "out_tif"),
        ],
    },
    "s1": {
        "title": "Sentinel-1",
        "fields": [],
    },
    "s2": {
        "title": "Sentinel-2",
        "fields": [
            ("Pasta Sentinel-2", "s2_dir"),
            ("Output S2",        "s2_out"),
            ("Threshold",        "threshold"),
        ],
    },
    "fusion": {
        "title": "Fusão",
        "fields": [
            ("S1 TIF",       "s1_tif"),
            ("S2 TIF",       "s2_tif"),
            ("Output final", "out_tif"),
        ],
    },
}


class RunState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class PromptCancelledError(RuntimeError):
    pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SAR-MSI Flood Detection")
        self.geometry("1100x750")
        self.minsize(1000, 700)

        self.mode = ctk.StringVar(value="all")
        self.s2_dir    = ctk.StringVar(value="Imagens")
        self.s2_out    = ctk.StringVar(value="ndwi_work")
        self.threshold = ctk.StringVar(value="")
        self.s1_tif    = ctk.StringVar(value="S1/output/kherson_flood.tif")
        self.s2_tif    = ctk.StringVar(value="ndwi_work/flood.tif")
        self.out_tif   = ctk.StringVar(value="flood_fused_continuous.tif")

        self.log_box = None
        self.input_field = None
        self.input_queue = queue.Queue()
        self.input_entry_var = ctk.StringVar()
        self._field_entries = {}
        self._field_values = {
            "s2_dir": self.s2_dir.get(),
            "s2_out": self.s2_out.get(),
            "threshold": self.threshold.get(),
            "s1_tif": self.s1_tif.get(),
            "s2_tif": self.s2_tif.get(),
            "out_tif": self.out_tif.get(),
        }
        self._last_status_text = "Pronto"
        self._pause_requested = False
        self._cancel_requested = False

        # Run control state & events
        self.run_state = RunState.IDLE
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

        self._build_ui()
        self._redirect_streams()

    # ------------------------------------------------------------------
    # Redirect stdout / stderr / stdin
    # ------------------------------------------------------------------
    def _redirect_streams(self):
        """Redirect streams to log box and input queue."""
        sys.stdout = _StreamRedirector(self._append_log)
        sys.stderr = _StreamRedirector(self._append_log)
        sys.stdin = _InteractiveInputReader(
            self.input_queue,
            stop_event=self._stop_event,
            status_callback=self._set_prompt_waiting,
        )

    def _append_log(self, text):
        """Thread-safe append to the log textbox."""
        self.after(0, lambda t=text: self._do_append_log(t))

    def _do_append_log(self, text):
        """Append text to log box on main thread."""
        if self.log_box:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

    def _set_status_text(self, text):
        self.after(0, lambda t=text: self.status.configure(text=t))

    def _set_prompt_waiting(self, text="A aguardar seleção de produto..."):
        def _apply():
            if self.run_state != RunState.CANCELED:
                self.run_state = RunState.AWAITING_INPUT
                self._last_status_text = self.status.cget("text")
                self.pause_btn.configure(state="disabled", text="Pausar")
                self.status.configure(text=text)

        self.after(0, _apply)

    def _clear_prompt_waiting(self):
        if self.run_state != RunState.AWAITING_INPUT:
            return

        self.run_state = RunState.PAUSED if self._pause_event.is_set() else RunState.RUNNING
        self.pause_btn.configure(state="normal", text="Retomar" if self.run_state == RunState.PAUSED else "Pausar")
        if self.run_state == RunState.RUNNING:
            self.status.configure(text=self._last_status_text or "A executar...")

    def _submit_input(self):
        """Handle input submission from the input field."""
        value = self.input_entry_var.get()
        # Always put the value in the queue (even if empty)
        self.input_queue.put(value)
        self._append_log(f"{value}\n")
        self.input_entry_var.set("")
        self._clear_prompt_waiting()

    def _capture_field_values(self):
        for attr, entry in self._field_entries.items():
            value = entry.get()
            self._field_values[attr] = value
            source = getattr(self, attr, None)
            if hasattr(source, "set"):
                source.set(value)

    def _get_field_value(self, attr):
        return self._field_values.get(attr, "")

    @staticmethod
    def _clean_path_text(value):
        return value.strip().strip('"').strip("'")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---- Sidebar ----
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(sidebar, text="SAR-MSI",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(20, 8))
        ctk.CTkLabel(sidebar, text="Flood Detection",
                     text_color="gray").pack(pady=(0, 20))

        def _make_nav(label, key):
            return ctk.CTkButton(
                sidebar, text=label,
                command=lambda k=key: self._switch_mode(k)
            )

        _make_nav("Pipeline Completo", "all"   ).pack(fill="x", padx=16, pady=6)
        _make_nav("Sentinel-1",        "s1"    ).pack(fill="x", padx=16, pady=6)
        _make_nav("Sentinel-2",        "s2"    ).pack(fill="x", padx=16, pady=6)
        _make_nav("Fusão",             "fusion").pack(fill="x", padx=16, pady=6)

        # ---- Main area ----
        self.main = ctk.CTkFrame(self)
        self.main.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        # Header with dynamic title
        header = ctk.CTkFrame(self.main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        self.header_label = ctk.CTkLabel(
            header, text="Pipeline Completo",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.header_label.grid(row=0, column=0, sticky="w", padx=14, pady=14)

        # Body — two columns
        body = ctk.CTkFrame(self.main)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Left: parameters panel
        self.left = ctk.CTkFrame(body)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=5)

        self.params_title = ctk.CTkLabel(
            self.left, text="Parâmetros",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.params_title.pack(anchor="w", padx=14, pady=(14, 10))

        self.fields_frame = ctk.CTkFrame(self.left, fg_color="transparent", height=330)
        self.fields_frame.pack(fill="both", expand=True, padx=0)

        self.run_btn = ctk.CTkButton(
            self.left, text="Executar", height=40, command=self.run_selected
        )
        self.run_btn.pack(fill="x", padx=14, pady=(18, 6))

        # Pause / Cancel buttons
        ctrl_frame = ctk.CTkFrame(self.left, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=14, pady=(0, 14))
        self.pause_btn = ctk.CTkButton(ctrl_frame, text="Pausar", command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.cancel_btn = ctk.CTkButton(ctrl_frame, text="Cancelar", command=self._cancel_run, state="disabled")
        self.cancel_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # Right: status + log + input
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(right, text="Estado",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=14, pady=(14, 8)
        )
        self.progress = ctk.CTkProgressBar(right)
        self.progress.pack(fill="x", padx=14, pady=(0, 10))
        self.progress.set(0)

        self.status = ctk.CTkLabel(right, text="Pronto", anchor="w")
        self.status.pack(fill="x", padx=14, pady=(0, 12))

        # Log textbox (read-only)
        self.log_box = ctk.CTkTextbox(right, wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        # Input field for interactive prompts
        input_frame = ctk.CTkFrame(right)
        input_frame.pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkLabel(input_frame, text="Entrada:", text_color="gray", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=0, pady=(0, 4))

        self.input_field = ctk.CTkEntry(
            input_frame,
            textvariable=self.input_entry_var,
            placeholder_text="Digite aqui e pressione Enter para responder..."
        )
        self.input_field.pack(fill="x")
        self.input_field.bind("<Return>", lambda e: self._submit_input())

        # Render initial fields
        self._render_fields("all")

    # ------------------------------------------------------------------
    # Dynamic field rendering
    # ------------------------------------------------------------------
    def _render_fields(self, mode_key):
        self._capture_field_values()

        # Destroy existing field widgets
        for widget in self.fields_frame.winfo_children():
            widget.destroy()

        self._field_entries = {}

        cfg = MODE_CONFIG[mode_key]
        if not cfg["fields"]:
            ctk.CTkLabel(
                self.fields_frame,
                text="Sem parâmetros configuráveis para este modo.",
                text_color="gray"
            ).pack(anchor="w", padx=14, pady=10)
            return

        for label, attr in cfg["fields"]:
            frame = ctk.CTkFrame(self.fields_frame)
            frame.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(frame, text=label).pack(
                anchor="w", padx=10, pady=(6, 2)
            )
            entry = ctk.CTkEntry(frame)
            entry.insert(0, self._field_values.get(attr, ""))
            entry.pack(fill="x", padx=10, pady=(0, 8))
            self._field_entries[attr] = entry

    def _switch_mode(self, key):
        self.mode.set(key)
        cfg = MODE_CONFIG[key]
        self.header_label.configure(text=cfg["title"])
        self._render_fields(key)

    # ------------------------------------------------------------------
    # Run control handlers
    # ------------------------------------------------------------------
    def _toggle_pause(self):
        if self.run_state == RunState.RUNNING:
            self._pause_event.set()
            self._pause_requested = True
            self._last_status_text = self.status.cget("text")
            self.run_state = RunState.PAUSED
            self.pause_btn.configure(text="Retomar")
            self.status.configure(text="Pausa solicitada. A aguardar ponto seguro...")
            self._append_log("A tentar pausar a execução...\n")
        elif self.run_state == RunState.PAUSED:
            self._pause_event.clear()
            self._pause_requested = False
            self.run_state = RunState.RUNNING
            self.pause_btn.configure(text="Pausar")
            self.status.configure(text=self._last_status_text)
            self._append_log("Execução retomada pelo utilizador.\n")

    def _cancel_run(self):
        self._stop_event.set()
        self._cancel_requested = True
        self._last_status_text = self.status.cget("text")
        self.status.configure(text="A cancelar...")
        self._append_log("A tentar cancelar a execução...\n")

    def _update_progress(self, fraction, msg=None):
        # Expect fraction in 0.0..1.0
        f = max(0.0, min(1.0, fraction if fraction is not None else 0.0))
        self.after(0, lambda: self.progress.set(f))
        if msg:
            if msg == "Pausado":
                self._last_status_text = self._last_status_text or "A executar..."
                print("Execução pausada. Clique em Retomar para continuar.")
                self.after(0, lambda: self.status.configure(text="Pausado"))
                self.after(0, lambda: self.pause_btn.configure(text="Retomar"))
                self.after(0, lambda: setattr(self, "run_state", RunState.PAUSED))
            elif msg == "Cancelado":
                self.after(0, lambda: self.status.configure(text="Cancelado"))
                self.after(0, lambda: setattr(self, "run_state", RunState.CANCELED))
            else:
                self._last_status_text = msg
                self.after(0, lambda: self.status.configure(text=msg))

    # ------------------------------------------------------------------
    # Run logic
    # ------------------------------------------------------------------
    def run_selected(self):
        # prepare events/state and UI
        self._capture_field_values()
        self._stop_event.clear()
        self._pause_event.clear()
        self._pause_requested = False
        self._cancel_requested = False
        self.run_state = RunState.RUNNING
        self._last_status_text = "A executar..."
        self.status.configure(text="A executar...")
        self.progress.set(0.0)
        self.run_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="Pausar")
        self.cancel_btn.configure(state="normal")
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self):
        try:
            mode = self.mode.get()

            if mode == "s1":
                print("A iniciar Sentinel-1...")
                result = S1Processor().run(
                    run_processing=True,
                    view=False,
                    progress_callback=self._update_progress,
                    stop_event=self._stop_event,
                    pause_event=self._pause_event,
                )
                if self._stop_event.is_set():
                    print("S1 cancelado.")
                else:
                    print(f"S1 concluído: {result.output_path}")

            elif mode == "s2":
                print("A iniciar Sentinel-2...")
                threshold = (
                    float(self._clean_path_text(self._get_field_value("threshold")))
                    if self._get_field_value("threshold").strip() else None
                )
                processor = S2Processor(
                    imagens_dir=self._clean_path_text(self._get_field_value("s2_dir")),
                    out_dir=self._clean_path_text(self._get_field_value("s2_out")),
                    preview=False,
                    threshold=threshold,
                )
                result = processor.run(
                    run_processing=True,
                    view=False,
                    progress_callback=self._update_progress,
                    stop_event=self._stop_event,
                    pause_event=self._pause_event,
                )
                if self._stop_event.is_set():
                    print("S2 cancelado.")
                else:
                    print(f"S2 concluído: {result.output_path}")

            elif mode == "fusion":
                print("A executar fusão...")
                out = fuse_flood_outputs(
                    Path(self._clean_path_text(self._get_field_value("s1_tif"))),
                    Path(self._clean_path_text(self._get_field_value("s2_tif"))),
                    Path(self._clean_path_text(self._get_field_value("out_tif"))),
                    progress_callback=self._update_progress,
                    stop_event=self._stop_event,
                    pause_event=self._pause_event,
                )
                if self._stop_event.is_set():
                    print("Fusão cancelada.")
                else:
                    print(f"Fusão concluída: {out}")

            else:
                print("A executar pipeline completo...")

            if self._stop_event.is_set():
                self.run_state = RunState.CANCELED
                self.after(0, lambda: self.status.configure(text="Cancelado"))
            else:
                self.run_state = RunState.COMPLETED
                self.after(0, lambda: self.progress.set(1.0))
                self.after(0, lambda: self.status.configure(text="Concluído ✓"))

        except PromptCancelledError:
            self.run_state = RunState.CANCELED
            self.after(0, lambda: self.status.configure(text="Cancelado"))
            self.after(0, lambda: self._append_log("Execução cancelada durante a espera de entrada.\n"))

        except Exception as e:
            if self._stop_event.is_set():
                self.run_state = RunState.CANCELED
                self.after(0, lambda: self.status.configure(text="Cancelado"))
                self.after(0, lambda: self._append_log("Execução cancelada.\n"))
                return
            print(f"Erro: {e}")
            self.run_state = RunState.FAILED
            self.after(0, lambda: self.status.configure(text="Falhou ✗"))
            self.after(0, lambda: self.progress.set(0))
        finally:
            # restore UI
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            self.after(0, lambda: self.pause_btn.configure(state="disabled", text="Pausar"))
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
            self._pause_requested = False
            self._cancel_requested = False


if __name__ == "__main__":
    app = App()
    app.mainloop()
