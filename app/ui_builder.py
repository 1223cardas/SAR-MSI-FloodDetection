import customtkinter as ctk
from .config import MODE_CONFIG, RunState

WIDTH  = 1280
HEIGHT = 720


class UIBuilder:
    def __init__(self, app, on_mode_changed):
        self.app = app
        self._on_mode_changed = on_mode_changed

        # Widgets expostos para o exterior
        self.status   = None
        self.progress = None
        self.log_box  = None
        self.pause_btn  = None
        self.cancel_btn = None
        self.run_btn    = None

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def build(self):
        self._configure_window()
        self._build_sidebar()
        self._build_main_area()
        self._build_header()
        self._build_body()
        self._render_fields("all")

    # ------------------------------------------------------------------
    # Helpers de UI (chamados pelo RunController / App)
    # ------------------------------------------------------------------

    def set_status(self, text: str):
        self.app.after(0, lambda t=text: self.status.configure(text=t))

    def set_pause_label(self, text: str):
        self.app.after(0, lambda t=text: self.pause_btn.configure(text=t))

    def set_running_controls(self):
        """Activa controlos de pausa/cancel e desactiva o botão de run."""
        self.run_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="Pausar")
        self.cancel_btn.configure(state="normal")

    def reset_controls(self):
        """Restaura a UI para o estado idle após o fim de uma execução."""
        self.run_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="Pausar")
        self.cancel_btn.configure(state="disabled")

    def set_prompt_waiting(self, text="A aguardar seleção de produto..."):
        def _apply():
            app = self.app
            if app.run_state != RunState.CANCELED:
                app.run_state         = RunState.AWAITING_INPUT
                app._last_status_text = self.status.cget("text")
                self.pause_btn.configure(state="disabled", text="Pausar")
                self.status.configure(text=text)

        self.app.after(0, _apply)

    def clear_prompt_waiting(self):
        app = self.app
        if app.run_state != RunState.AWAITING_INPUT:
            return
        app.run_state = RunState.PAUSED if app._pause_event.is_set() else RunState.RUNNING
        self.pause_btn.configure(
            state="normal",
            text="Retomar" if app.run_state == RunState.PAUSED else "Pausar",
        )
        if app.run_state == RunState.RUNNING:
            self.status.configure(text=app._last_status_text or "A executar...")

    def append_log(self, text: str):
        """Thread-safe: adiciona texto à caixa de log."""
        self.app.after(0, lambda t=text: self._do_append_log(t))

    def _do_append_log(self, text: str):
        if self.log_box:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Campos dinâmicos
    # ------------------------------------------------------------------

    def _render_fields(self, mode_key: str):
        app = self.app
        app._capture_field_values()

        for widget in self._fields_frame.winfo_children():
            widget.destroy()
        app._field_entries = {}

        fields = MODE_CONFIG[mode_key]["fields"]
        if not fields:
            ctk.CTkLabel(
                self._fields_frame,
                text="Sem parâmetros configuráveis para este modo.",
                text_color="gray",
            ).pack(anchor="w", padx=14, pady=10)
            return

        for label, attr in fields:
            frame = ctk.CTkFrame(self._fields_frame)
            frame.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(frame, text=label).pack(anchor="w", padx=10, pady=(6, 2))
            entry = ctk.CTkEntry(frame)
            entry.insert(0, app._get_field_value(attr))
            entry.pack(fill="x", padx=10, pady=(0, 8))
            app._field_entries[attr] = entry

    def render(self, mode_key: str):
        """Chamado por App._switch_mode para re-renderizar os campos."""
        self._render_fields(mode_key)
        self._header_label.configure(text=MODE_CONFIG[mode_key]["title"])

    # ------------------------------------------------------------------
    # Construção interna
    # ------------------------------------------------------------------

    def _configure_window(self):
        app = self.app
        app.title("SAR-MSI Flood Detection")
        app.geometry(f"{WIDTH}x{HEIGHT}")
        app.minsize(WIDTH, HEIGHT)
        app.grid_columnconfigure(1, weight=1)
        app.grid_rowconfigure(0, weight=1)

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self.app, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="ns")

        ctk.CTkLabel(
            sidebar, text="SAR-MSI",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(20, 8))

        ctk.CTkLabel(
            sidebar, text="Flood Detection", text_color="gray",
        ).pack(fill="x", padx=15, pady=(0, 40))

        def _nav(text, mode):
            ctk.CTkButton(
                sidebar, text=text,
                command=lambda m=mode: self._on_mode_changed(m),
            ).pack(fill="x", padx=15, pady=8)

        _nav("Pipeline Completo", "all")
        _nav("Modo automático",   "auto")
        _nav("Sentinel-1",        "s1")
        _nav("Sentinel-2",        "s2")
        _nav("Fusão",             "fusion")

    def _build_main_area(self):
        main = ctk.CTkFrame(self.app)
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self.app.main = main

    def _build_header(self):
        header = ctk.CTkFrame(self.app.main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        self._header_label = ctk.CTkLabel(
            header, text="Pipeline Completo",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self._header_label.grid(row=0, column=0, sticky="w", padx=14, pady=14)

    def _build_body(self):
        body = ctk.CTkFrame(self.app.main)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

    def _build_left_panel(self, parent):
        left = ctk.CTkFrame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=5)

        ctk.CTkLabel(
            left, text="Parâmetros",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(14, 10))

        self._fields_frame = ctk.CTkFrame(left, fg_color="transparent", height=330)
        self._fields_frame.pack(fill="both", expand=True)

        self.run_btn = ctk.CTkButton(
            left, text="Executar", height=40,
            command=self.app.run_selected,
        )
        self.run_btn.pack(fill="x", padx=14, pady=(18, 6))

        ctrl = ctk.CTkFrame(left, fg_color="transparent")
        ctrl.pack(fill="x", padx=14, pady=(0, 14))

        self.pause_btn = ctk.CTkButton(
            ctrl, text="Pausar",
            command=self.app.runner.toggle_pause,
            state="disabled",
        )
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.cancel_btn = ctk.CTkButton(
            ctrl, text="Cancelar",
            command=self.app.runner.cancel,
            state="disabled",
        )
        self.cancel_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _build_right_panel(self, parent):
        right = ctk.CTkFrame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            right, text="Estado",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        self.progress = ctk.CTkProgressBar(right)
        self.progress.pack(fill="x", padx=14, pady=(0, 10))
        self.progress.set(0)

        self.status = ctk.CTkLabel(right, text="Pronto", anchor="w")
        self.status.pack(fill="x", padx=14, pady=(0, 12))

        self.log_box = ctk.CTkTextbox(right, wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self._build_input_field(right)

    def _build_input_field(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkLabel(
            frame, text="Entrada:", text_color="gray",
            font=ctk.CTkFont(size=10),
        ).pack(anchor="w", pady=(0, 4))

        entry = ctk.CTkEntry(
            frame,
            textvariable=self.app.input_entry_var,
            placeholder_text="Digite aqui e pressione Enter para responder...",
        )
        entry.pack(fill="x")
        entry.bind("<Return>", lambda e: self.app._submit_input())
        self.app.input_field = entry