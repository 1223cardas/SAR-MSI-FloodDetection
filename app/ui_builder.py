from pathlib import Path

import customtkinter as ctk
import numpy as np
import rasterio
from matplotlib import colors
import matplotlib.image as mpimg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .config import MODE_CONFIG, RunState, FIELD_DEFAULTS


def get_available_tifs(folder_path: str) -> list[str]:
	"""Scans for all .tif files in the given directory, sorted by most recent modification date."""
	path = Path(folder_path)
	if not path.exists():
		return []
	
	tifs = [str(p.absolute()) for p in path.glob("*flood.tif") if not p.name.endswith(".preview.png")]
	tifs.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
	return tifs


class UIBuilder:

	status: ctk.CTkLabel
	progress: ctk.CTkProgressBar
	log_box: ctk.CTkTextbox
	cancel_btn: ctk.CTkButton
	run_btn: ctk.CTkButton
	result_btn: ctk.CTkButton
	
	_fields_frame: ctk.CTkFrame
	_header_label: ctk.CTkLabel
	_rendered_mode: str

	def __init__(self, app, on_mode_changed):
		self.app = app
		self._on_mode_changed = on_mode_changed
		self._rendered_mode = ""

		self._progress_colors = {
			"running": "#3b82f6",
			"canceled": "#ef4444",
			"failed": "#ef4444",
			"completed": "#22c55e",
		}

	def build(self):
		self._configure_window()
		self._build_sidebar()
		self._build_main_area()
		self._build_header()
		self._build_body()
		self._render_fields(self._rendered_mode)

	# ------------------------------------------------------------------
	# UI Helpers (called by RunController / App)
	# ------------------------------------------------------------------

	def set_status(self, text: str):
		self.app.after(0, lambda t=text: self.status.configure(text=t))

	def clear_log(self):
		self._do_clear_log()

	def _do_clear_log(self):
		self.log_box.configure(state="normal")
		self.log_box.delete("1.0", "end")
		self.log_box.configure(state="disabled")

	def set_progress_color(self, state: str):
		color = self._progress_colors.get(state, self._progress_colors["running"])
		self.app.after(0, lambda c=color: self.progress.configure(progress_color=c))

	def set_result_button_state(self, enabled: bool):
		state = "normal" if enabled else "disabled"
		self.app.after(0, lambda: self.result_btn.configure(state=state))

	def show_result_preview(self):
		path = getattr(self.app, "last_output_path", None)
		if not path:
			self.set_status("No final result available to view.")
			return

		tif_path = Path(path)
		if not tif_path.exists():
			self.set_status("The final file no longer exists on disk.")
			return

		preview_png = self.cache_result_preview(tif_path)
		if preview_png is None or not preview_png.exists():
			self.set_status("Failed to prepare PNG preview of the result.")
			return

		preview = ctk.CTkToplevel(self.app)
		preview.title(f"Final Result - {tif_path.name}")
		preview.geometry("980x760")
		preview.minsize(800, 600)

		container = ctk.CTkFrame(preview)
		container.pack(fill="both", expand=True, padx=12, pady=12)

		header = ctk.CTkLabel(
			container,
			text=f"Final Result: {tif_path.name}",
			font=ctk.CTkFont(size=16, weight="bold"),
		)
		header.pack(anchor="w", padx=12, pady=(12, 6))

		info = ctk.CTkLabel(
			container,
			text=f"Source: {tif_path} | Preview: {preview_png.name}",
			text_color="gray",
			anchor="w",
		)
		info.pack(fill="x", padx=12, pady=(0, 10))

		rgb = mpimg.imread(preview_png)
		fig = Figure(figsize=(8, 6), dpi=100)
		ax = fig.add_subplot(111)
		ax.imshow(rgb)
		ax.set_title("Final Result Map (Cached PNG)")
		ax.set_axis_off()
		fig.tight_layout()

		canvas = FigureCanvasTkAgg(fig, master=container)
		canvas.draw()
		canvas.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=(0, 12))

		preview.transient(self.app)
		preview.focus_set()

	def cache_result_preview(self, tif_path: str | Path | None) -> Path | None:
		if not tif_path:
			return None

		source = Path(tif_path)
		if not source.exists() or source.suffix.lower() != ".tif":
			return None

		preview_png = source.with_suffix(".preview.png")
		if preview_png.exists() and preview_png.stat().st_mtime >= source.stat().st_mtime:
			return preview_png

		source_for_preview = source
		normalize_uint8 = False
		try:
			with rasterio.open(source) as src:
				is_color_uint8 = (src.count >= 3 and src.dtypes[0].startswith("uint8"))
		except Exception:
			is_color_uint8 = False

		if is_color_uint8:
			text = source.stem
			if text.endswith('.color'):
				candidate = source.with_name(text[:-6] + source.suffix)
				if candidate.exists():
					source_for_preview = candidate
			else:
				for pattern in ('.color', '_color', '-color'):
					if pattern in text:
						candidate = source.with_name(text.replace(pattern, '') + source.suffix)
						if candidate.exists():
							source_for_preview = candidate
							break

			if source_for_preview == source:
				normalize_uint8 = True

		with rasterio.open(source_for_preview) as src:
			data = src.read(1).astype("float32")

		if normalize_uint8:
			data = data / 255.0

		finite = np.isfinite(data)
		if not finite.any():
			return None

		valid = data[finite]
		vmin = float(valid.min())
		vmax = float(valid.max())
		if vmax <= vmin:
			vmax = vmin + 1.0

		masked = np.ma.masked_invalid(data)
		fig = Figure(figsize=(10, 7), dpi=140)
		ax = fig.add_subplot(111)
		norm = colors.Normalize(vmin=vmin, vmax=vmax)
		image = ax.imshow(masked, cmap="viridis", norm=norm)
		ax.set_axis_off()
		ax.set_title(f"{source_for_preview.name} | scale {vmin:.3f} to {vmax:.3f}")
		fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Value")
		fig.tight_layout()
		fig.savefig(preview_png, bbox_inches="tight", pad_inches=0.05)
		fig.clear()
		return preview_png

	def set_running_controls(self):
		self.run_btn.configure(state="disabled")
		self.cancel_btn.configure(state="normal")
		self.set_result_button_state(False)
		self.set_progress_color("running")

	def reset_controls(self):
		self.run_btn.configure(state="normal")
		self.cancel_btn.configure(state="disabled")
		self.set_result_button_state(bool(getattr(self.app, "last_output_path", None)))

	def set_prompt_waiting(self, text="Awaiting product selection..."):
		def _apply():
			app = self.app
			if app.run_state != RunState.CANCELED:
				app.run_state         = RunState.AWAITING_INPUT
				app._last_status_text = self.status.cget("text")
				self.status.configure(text=text)

		self.app.after(0, _apply)

	def clear_prompt_waiting(self):
		app = self.app
		if app.run_state != RunState.AWAITING_INPUT:
			return
		app.run_state = RunState.RUNNING
		self.status.configure(text=app._last_status_text or "Executing...")

	def append_log(self, text: str):
		self.app.after(0, lambda t=text: self._do_append_log(t))

	def _do_append_log(self, text: str):
		if self.log_box:
			self.log_box.configure(state="normal")
			self.log_box.insert("end", text)
			self.log_box.see("end")
			self.log_box.configure(state="disabled")

	# ------------------------------------------------------------------
	# Dynamic Field Management
	# ------------------------------------------------------------------

	def _render_fields(self, mode_key: str):
		app = self.app

		if self._rendered_mode == mode_key and self._fields_frame.winfo_children():
			return
		self._rendered_mode = mode_key

		for widget in self._fields_frame.winfo_children():
			widget.destroy()
		
		app._field_entries = {}

		fields = MODE_CONFIG[mode_key]["fields"]
		if not fields:
			frame = ctk.CTkFrame(self._fields_frame)
			frame.pack(fill="x")
			ctk.CTkLabel(frame, text="No parameters required for this mode.").pack(anchor="w", padx=10, pady=(6, 2))
			return

		for label, attr in fields:
			frame = ctk.CTkFrame(self._fields_frame)
			frame.pack(fill="x")
			ctk.CTkLabel(frame, text=label).pack(anchor="w", padx=10, pady=(6, 2))

			current_value = app._get_field_value(attr)

			if mode_key == "fusion" and attr in ["s1_tif", "s2_tif"]:
				default_folder_key = "s1_out" if attr == "s1_tif" else "s2_out"
				folder_to_search = FIELD_DEFAULTS.get(default_folder_key, "")

				available_options = get_available_tifs(folder_path=folder_to_search)

				if not available_options:
					available_options = [current_value] if current_value else ["No .tif files found"]

				if current_value and current_value not in available_options and current_value != "No .tif files found":
					available_options.append(current_value)

				entry = ctk.CTkOptionMenu(frame, values=available_options, dynamic_resizing=False)
				if current_value in available_options:
					entry.set(current_value)
				else:
					entry.set(available_options[0])
			else:
				entry = ctk.CTkEntry(frame, placeholder_text="Enter value...")
				entry.insert(0, current_value)

			entry.pack(fill="x", padx=10, pady=(0, 8))
			app._field_entries[attr] = entry

	def render(self, mode_key: str):
		self._render_fields(mode_key)
		self._header_label.configure(text=MODE_CONFIG[mode_key]["title"])

	# ------------------------------------------------------------------
	# Core Layout Assembly 
	# ------------------------------------------------------------------

	def _configure_window(self):
		app = self.app
		app.title("SAR-MSI Flood Detection")

		screen_width = app.winfo_screenwidth()
		screen_height = app.winfo_screenheight()

		dynamic_width = int(screen_width * 0.75)
		dynamic_height = int(screen_height * 0.70)

		win_width = max(1024, min(dynamic_width, 1600))
		win_height = max(600, min(dynamic_height, 900))

		x_position = (screen_width - win_width) // 2
		y_position = (screen_height - win_height) // 2
		
		app.geometry(f"{win_width}x{win_height}+{x_position}+{y_position}")
		app.resizable(False, False)

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

		_nav("Automated Pipeline", "auto")
		_nav("Sentinel-1",         "s1")
		_nav("Sentinel-2",         "s2")
		_nav("Fusion",        "fusion")

		self._rendered_mode = "auto"

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

		header_text = MODE_CONFIG.get(self._rendered_mode, {}).get("title", "")
		self._header_label = ctk.CTkLabel(
			header, 
			text=header_text,
			font=ctk.CTkFont(size=20, weight="bold"),
		)
		self._header_label.grid(row=0, column=0, sticky="w", padx=14, pady=14)

	def _build_body(self):
		body = ctk.CTkFrame(self.app.main)
		body.grid(row=1, column=0, sticky="nsew")
		body.grid_columnconfigure(0, weight=1, uniform="panel")
		body.grid_columnconfigure(1, weight=1, uniform="panel")
		body.grid_rowconfigure(0, weight=1)

		self._build_left_panel(body)
		self._build_right_panel(body)

	def _build_left_panel(self, parent):
		left = ctk.CTkFrame(parent)
		left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)

		ctk.CTkLabel(
			left, text="Parameters",
			font=ctk.CTkFont(size=16, weight="bold")
		).pack(anchor="w", padx=14, pady=(14, 10))

		self._fields_frame = ctk.CTkFrame(left, fg_color="transparent")
		self._fields_frame.pack(fill="both", expand=True, side="top")

		self.cancel_btn = ctk.CTkButton(
			left, text="Cancel", height=40,
			command=self.app.runner.cancel,
			state="disabled"
		)
		self.cancel_btn.pack(fill="x", padx=14, pady=(6, 12), side="bottom")

		self.run_btn = ctk.CTkButton(
			left, text="Run Execution", height=40,
			command=self.app.run_selected
		)
		self.run_btn.pack(fill="x", padx=14, side="bottom")


	def _build_right_panel(self, parent):
		right = ctk.CTkFrame(parent)
		right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
		right.grid_columnconfigure(0, weight=1)
		right.grid_rowconfigure(2, weight=1)

		ctk.CTkLabel(
			right, text="Status Monitoring",
			font=ctk.CTkFont(size=16, weight="bold"),
		).pack(anchor="w", padx=14, pady=(14, 8))

		self.progress = ctk.CTkProgressBar(right)
		self.progress.pack(fill="x", padx=14, pady=(0, 10))
		self.progress.set(0)

		self.status = ctk.CTkLabel(right, text="Ready", anchor="w")
		self.status.pack(fill="x", padx=14, pady=(0, 12))

		self.log_box = ctk.CTkTextbox(right, wrap="none", state="disabled")
		self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

		self.result_btn = ctk.CTkButton(
			right,
			text="View Final Result Map",
			command=self.show_result_preview,
			state="disabled",
		)
		self.result_btn.pack(fill="x", padx=14, pady=(0, 12))

		self._build_input_field(right)

	def _build_input_field(self, parent):
		frame = ctk.CTkFrame(parent)
		frame.pack(fill="x", padx=14, pady=(0, 14))

		ctk.CTkLabel(
			frame, 
			text="User Console Input:", 
			text_color="gray", 
			font=ctk.CTkFont(size=10)
		).pack(anchor="w", pady=(0, 4))

		entry = ctk.CTkEntry(
			frame,
			textvariable=self.app.input_entry_var,
			placeholder_text="Type your answer here and press Enter...",
		)
		entry.pack(fill="x")
		entry.bind("<Return>", lambda e: self.app._submit_input())
		self.app.input_field = entry