import threading
from pathlib import Path

from .config import RunState, PromptCancelledError
from Combined.combine import fuse_flood_outputs
from processors import S1Processor, S2Processor

from Acquisition.acquireProducts import acquireProductsS1_S2

class RunController:
    def __init__(self, app):
        self._app = app

    # ------------------------------------------------------------------
    # Controlo público (chamado pela UI, no thread principal)
    # ------------------------------------------------------------------

    def start(self):
        app = self._app
        app._stop_event.clear()
        app._pause_event.clear()
        app.run_state        = RunState.RUNNING
        app._last_status_text = "A executar..."
        app.last_output_path = None
        app.ui.clear_log()
        app.ui.set_progress_color("running")
        threading.Thread(target=self._worker, daemon=True).start()

    def toggle_pause(self):
        app = self._app
        if app.run_state == RunState.RUNNING:
            app._pause_event.set()
            app.run_state         = RunState.PAUSED
            app._last_status_text = app.ui.status.cget("text")
            app.ui.set_status("Pausa solicitada. A aguardar ponto seguro...")
            app.ui.set_pause_label("Retomar")
            app.ui.set_progress_color("paused")
            print("A tentar pausar a execução...\n")

        elif app.run_state == RunState.PAUSED:
            app._pause_event.clear()
            app.run_state = RunState.RUNNING
            app.ui.set_status(app._last_status_text)
            app.ui.set_pause_label("Pausar")
            app.ui.set_progress_color("running")
            print("Execução retomada pelo utilizador.\n")

    def cancel(self):
        app = self._app
        app._stop_event.set()
        app._last_status_text = app.ui.status.cget("text")
        app.ui.set_status("A cancelar...")
        app.ui.set_progress_color("canceled")
        print("A tentar cancelar a execução...\n")

    # ------------------------------------------------------------------
    # Progress callback (chamado pelos processadores, em qualquer thread)
    # ------------------------------------------------------------------

    def update_progress(self, fraction, msg=None):
        app  = self._app
        frac = max(0.0, min(1.0, fraction or 0.0))
        app.after(0, lambda: app.ui.progress.set(frac))

        if not msg:
            return

        if msg == "Pausado":
            app._last_status_text = app._last_status_text or "A executar..."
            print("Execução pausada. Clique em Retomar para continuar.")
            app.after(0, lambda: app.ui.set_status("Pausado"))
            app.after(0, lambda: app.ui.set_pause_label("Retomar"))
            app.after(0, lambda: app.ui.set_progress_color("paused"))
            app.after(0, lambda: setattr(app, "run_state", RunState.PAUSED))
        elif msg == "Cancelado":
            app.after(0, lambda: app.ui.set_status("Cancelado"))
            app.after(0, lambda: app.ui.set_progress_color("canceled"))
            app.after(0, lambda: setattr(app, "run_state", RunState.CANCELED))
        else:
            app._last_status_text = msg
            app.after(0, lambda: app.ui.set_status(msg))

    # ------------------------------------------------------------------
    # Worker (corre no thread de background)
    # ------------------------------------------------------------------

    def _worker(self):
        app = self._app
        try:
            final_output_path = self._dispatch(app.mode.get())
            app.last_output_path = final_output_path

            if final_output_path and not app._stop_event.is_set():
                try:
                    app.ui.cache_result_preview(final_output_path)
                except Exception as e:
                    print(f"Aviso: falha ao criar preview PNG em cache: {e}")

            if app._stop_event.is_set():
                app.run_state = RunState.CANCELED
                app.after(0, lambda: app.ui.set_status("Cancelado"))
                app.after(0, lambda: app.ui.set_progress_color("canceled"))
                app.after(0, lambda: app.ui.set_result_button_state(False))
            else:
                app.run_state = RunState.COMPLETED
                app.after(0, lambda: app.ui.progress.set(1.0))
                app.after(0, lambda: app.ui.set_status("Concluído"))
                app.after(0, lambda: app.ui.set_progress_color("completed"))
                app.after(0, lambda: app.ui.set_result_button_state(bool(final_output_path)))

        except PromptCancelledError:
            app.run_state = RunState.CANCELED
            app.after(0, lambda: app.ui.set_status("Cancelado"))
            app.after(0, lambda: app.ui.set_progress_color("canceled"))
            app.after(0, lambda: app.ui.set_result_button_state(False))
            app.after(0, lambda: print("Execução cancelada durante a espera de entrada.\n"))

        except Exception as e:
            if app._stop_event.is_set():
                app.run_state = RunState.CANCELED
                app.after(0, lambda: app.ui.set_status("Cancelado"))
                app.after(0, lambda: app.ui.set_progress_color("canceled"))
                app.after(0, lambda: app.ui.set_result_button_state(False))
                app.after(0, lambda: print("Execução cancelada.\n"))
                return
            print(f"Erro: {e}")
            app.run_state = RunState.FAILED
            app.after(0, lambda: app.ui.set_status("Falhou"))
            app.after(0, lambda: app.ui.set_progress_color("failed"))
            app.after(0, lambda: app.ui.set_result_button_state(False))
            app.after(0, lambda: app.ui.progress.set(0))

        finally:
            app.after(0, app.ui.reset_controls)

    def _dispatch(self, mode):
        app  = self._app
        cb   = self.update_progress
        stop = app._stop_event
        pause = app._pause_event

        def field(key):
            return app._clean_path_text(app._get_field_value(key))

        if mode == "s1":
            print("A iniciar Sentinel-1...")
            result = S1Processor(
                progress_callback=cb, stop_event=stop, pause_event=pause,
            ).run(run_processing=True, view=False)
            print("S1 cancelado." if stop.is_set() else f"S1 concluído: {result.output_path}")
            return result.output_path if not stop.is_set() else None

        elif mode == "s2":
            print("A iniciar Sentinel-2...")
            threshold = float(field("threshold")) if field("threshold") else None
            result = S2Processor(
                out_dir=field("s2_out"),
                preview=False,
                threshold=threshold,
                progress_callback=cb, stop_event=stop, pause_event=pause,
            ).run(run_processing=True, view=False)
            print("S2 cancelado." if stop.is_set() else f"S2 concluído: {result.output_path}")
            return result.output_path if not stop.is_set() else None

        elif mode == "fusion":
            print("A executar fusão...")
            out = fuse_flood_outputs(
                Path(field("s1_tif")),
                Path(field("s2_tif")),
                Path(field("out_tif")),
                progress_callback=cb,
                stop_event=stop,
                pause_event=pause,
            )
            print("Fusão cancelada." if stop.is_set() else f"Fusão concluída: {out}")
            return out if not stop.is_set() else None

        elif mode == "auto":
            print("A executar pipeline automático...")
            s1_entry, s2_entry = acquireProductsS1_S2()

            hasS1 = len(s1_entry.productFromIds()) == 2
            hasS2 = len(s2_entry.productFromIds()) == 2

            print(f"Dados disponíveis — S1: {hasS1} | S2: {hasS2}")

            if not hasS1 and not hasS2:
                print("Nenhum dado disponível para processamento automático.")
                return

            s1_path = None
            print(f"entry s1 {s1_entry}")
            if hasS1:
                result = S1Processor(
                    progress_callback=cb,
                    stop_event=stop,
                    pause_event=pause,
                ).run(run_processing=True, view=False, entry=s1_entry.to_dict())
                output_path = getattr(result, "output_path", None)
                s1_path = Path(output_path) if output_path is not None else None
                if not s1_path:
                    s1_path = next(iter(sorted(Path("S1/output").glob("*_flood.tif"), key=lambda p: p.stat().st_mtime, reverse=True)), None)

            s2_path = None
            if hasS2:
                threshold = float(field("threshold")) if field("threshold") else None
                result = S2Processor(
                    out_dir=field("s2_out"),
                    preview=False,
                    threshold=threshold,
                    progress_callback=cb,
                    stop_event=stop,
                    pause_event=pause,
                ).run(run_processing=True, view=False, entry=s2_entry.to_dict())
                output_path = getattr(result, "output_path", None)
                s2_path = Path(output_path) if output_path is not None else None
                if not s2_path:
                    s2_path = next(iter(sorted(Path(field("s2_out")).glob("*flood*.tif"), key=lambda p: p.stat().st_mtime, reverse=True)), None)

            if s1_path and s2_path:
                out = fuse_flood_outputs(
                    s1_path,
                    s2_path,
                    Path(field("out_tif")),
                    progress_callback=cb,
                    stop_event=stop,
                    pause_event=pause,
                )
                print("Fusão automática concluída." if not stop.is_set() else "Fusão automática cancelada.")
                print(out)
                return out if not stop.is_set() else None
            elif s1_path:
                print(f"[auto] apenas S1 disponível — resultado: {s1_path}")
                return s1_path
            elif s2_path:
                print(f"[auto] apenas S2 disponível — resultado: {s2_path}")
                return s2_path
            else:
                print("[auto] nenhum ficheiro produzido apesar dos dados reportados.")
                return None