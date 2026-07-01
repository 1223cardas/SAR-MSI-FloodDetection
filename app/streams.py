"""
streams.py — Gestão de stdout/stderr/stdin para a GUI.

StreamManager  : redireciona os streams do sistema para a caixa de log e fila de input.
"""

import io
import queue
import sys

from .config import PromptCancelledError


# ---------------------------------------------------------------------------
# Stream Redirector (stdout / stderr → log box)
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
# Interactive stdin reader (stdin → queue com suporte a cancelamento)
# ---------------------------------------------------------------------------

class _InteractiveInputReader(io.TextIOBase):
    def __init__(self, input_queue, stop_event=None, status_callback=None):
        super().__init__()
        self._queue           = input_queue
        self._stop_event      = stop_event
        self._status_callback = status_callback

    def _notify_waiting(self):
        if self._status_callback:
            self._status_callback("A aguardar entrada do utilizador...")

    def readline(self, size=-1):
        self._notify_waiting()
        while True:
            if self._stop_event is not None and self._stop_event.is_set():
                raise PromptCancelledError()
            try:
                line = self._queue.get(block=True, timeout=0.2)
                return line if line.endswith("\n") else line + "\n"
            except queue.Empty:
                continue

    def read(self, size=-1):
        return self.readline(size)

    def isatty(self):
        return True


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class StreamManager:
    """Redireciona stdout/stderr/stdin e restaura-os ao fechar."""

    def __init__(self, log_callback, input_queue, stop_event=None, status_callback=None):
        self._log_callback    = log_callback
        self._input_queue     = input_queue
        self._stop_event      = stop_event
        self._status_callback = status_callback

        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._original_stdin  = sys.stdin

    def redirect(self):
        sys.stdout = _StreamRedirector(self._log_callback)
        sys.stderr = _StreamRedirector(self._log_callback)
        sys.stdin  = _InteractiveInputReader(
            self._input_queue,
            stop_event=self._stop_event,
            status_callback=self._status_callback,
        )

    def restore(self):
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        sys.stdin  = self._original_stdin