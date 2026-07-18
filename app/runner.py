import threading
from pathlib import Path

from .config import RunState
from Combined.combine import fuse_flood_outputs
from processorsImpl import S1Processor, S2Processor
from Acquisition.acquireProducts import acquireEntryFromLogWithBoth

from common import PromptCancelledError

class RunController:
	def __init__(self, app):
		self._app = app

	def start(self):
		app = self._app
		app._stop_event.clear()

		app.run_state = RunState.RUNNING
		app._last_status_text = "Executing..."
		app.last_output_path = None

		app.ui._do_clear_log()

		app.ui.set_running_controls()
		app.ui.progress.set(0.0)
		app.ui.set_status(app._last_status_text)

		threading.Thread(target=self._worker, daemon=True).start()

	def cancel(self):
		app = self._app
		print("Trying to cancel the execution...\n")
		app._stop_event.set()
		app.run_state = RunState.CANCELED
		app._last_status_text = app.ui.status.cget("text")

		app.ui.set_status("Cancelling...")
		app.ui.set_progress_color("canceled")

	def update_progress(self, fraction, msg=None):
		app = self._app
		frac = max(0.0, min(1.0, fraction or 0.0))
		app.after(0, lambda: app.ui.progress.set(frac))

		if not msg:
			return

		if msg == "Cancelled":
			app.after(0, lambda: app.ui.set_status("Cancelled"))
			app.after(0, lambda: app.ui.set_progress_color("canceled"))
			app.after(0, lambda: setattr(app, "run_state", RunState.CANCELED))
		else:
			app.after(0, lambda m=msg: app.ui.set_status(m))

	def _worker(self):
		app = self._app
		try:
			final_output_path = self._dispatch(app.mode.get())
			app.last_output_path = final_output_path

			if app._stop_event.is_set():
				app.after(0, lambda: setattr(app, "run_state", RunState.CANCELED))
				app.after(0, lambda: app.ui.set_status("Cancelled"))
				app.after(0, lambda: app.ui.set_progress_color("canceled"))
			else:
				app.after(0, lambda: setattr(app, "run_state", RunState.COMPLETED))
				app.after(0, lambda: app.ui.progress.set(1.0))
				app.after(0, lambda: app.ui.set_status("Completed"))
				app.after(0, lambda: app.ui.set_progress_color("completed"))

		except PromptCancelledError:
			app.after(0, lambda: setattr(app, "run_state", RunState.CANCELED))
			app.after(0, lambda: app.ui.set_status("Cancelled"))
			app.after(0, lambda: app.ui.set_progress_color("canceled"))
			app.after(0, lambda: print("Execution cancelled while awaiting user input.\n"))

		except Exception as e:
			if app._stop_event.is_set():
				app.after(0, lambda: setattr(app, "run_state", RunState.CANCELED))
				app.after(0, lambda: app.ui.set_status("Cancelled"))
				app.after(0, lambda: app.ui.set_progress_color("canceled"))
				return
			print(f"Error: {e}")
			app.after(0, lambda: setattr(app, "run_state", RunState.FAILED))
			app.after(0, lambda: app.ui.set_status("Failed"))
			app.after(0, lambda: app.ui.set_progress_color("failed"))
			app.after(0, lambda: app.ui.progress.set(0))
		finally:
			app.after(0, app.ui.reset_controls)

	def _dispatch(self, mode):
		app  = self._app
		cb   = self.update_progress
		stop = app._stop_event

		def field(key):
			return app._clean_path_text(app._get_field_value(key))

		if mode == "s1":
			print("Starting Sentinel-1 Pipeline...")
			result = S1Processor(progress_callback=cb, stop_event=stop).run(run_processing=True, view=False)
			return result.output_path if not stop.is_set() else None

		elif mode == "s2":
			print("Starting Sentinel-2 Pipeline...")
			threshold = float(field("threshold")) if field("threshold") else None
			result = S2Processor(threshold=threshold, progress_callback=cb, stop_event=stop).run(run_processing=True, view=False)
			return result.output_path if not stop.is_set() else None

		elif mode == "fusion":
			print("Executing Fusion...")
			out = fuse_flood_outputs(Path(field("s1_tif")), Path(field("s2_tif")), Path(field("out_tif")), progress_callback=cb, stop_event=stop)
			return out if not stop.is_set() else None

		elif mode == "auto":
			print("Running Automated Pipeline Workflow...")
			entries  = acquireEntryFromLogWithBoth()
			if entries is None:
				print("No entries available.")
				return None
			
			s1_entry, s2_entry = entries 
			hasS1 = len(s1_entry.productFromIds()) == 2
			hasS2 = len(s2_entry.productFromIds()) == 2

			if not hasS1 and not hasS2:
				print("No satellite products available for automated processing.")
				return None

			s1_path = None
			if hasS1:
				result = S1Processor(progress_callback=cb, stop_event=stop).run(run_processing=True, view=False, entry=s1_entry.to_dict())
				output_path = getattr(result, "output_path", None)
				s1_path = Path(output_path) if output_path is not None else None
				if not s1_path:
					s1_path = next(iter(sorted(Path("S1/output").glob("*_flood.tif"), key=lambda p: p.stat().st_mtime, reverse=True)), None)

			s2_path = None
			if hasS2:
				threshold = float(field("threshold")) if field("threshold") else None
				result = S2Processor(threshold=threshold, progress_callback=cb, stop_event=stop).run(run_processing=True, view=False, entry=s2_entry.to_dict())
				output_path = getattr(result, "output_path", None)
				s2_path = Path(output_path) if output_path is not None else None
				if not s2_path:
					s2_path = next(iter(sorted(Path(field("s2_out")).glob("*flood*.tif"), key=lambda p: p.stat().st_mtime, reverse=True)), None)

			if s1_path and s2_path:
				out = fuse_flood_outputs(s1_path, s2_path, Path(field("out_tif")), progress_callback=cb, stop_event=stop)
				return out if not stop.is_set() else None
			elif s1_path:
				return s1_path
			elif s2_path:
				return s2_path
			return None