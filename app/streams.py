import io
import queue
import sys
import threading

from common import PromptCancelledError

class _StreamRedirector(io.TextIOBase):
    # Pass schedule_callback to handle thread-safe loop scheduling
    def __init__(self, callback, schedule_callback):
        super().__init__()
        self._callback = callback
        self._schedule_callback = schedule_callback
        self._buffer = []
        self._lock = threading.Lock()
        self._flush_scheduled = False

    def write(self, text):
        if text:
            with self._lock:
                self._buffer.append(text)
                if not self._flush_scheduled:
                    self._flush_scheduled = True
                    # Use the explicit app scheduling hook safely from any thread
                    self._schedule_callback(30, self._batch_flush)
        return len(text) if text else 0

    def _batch_flush(self):
        with self._lock:
            text_to_flush = "".join(self._buffer)
            self._buffer.clear()
            self._flush_scheduled = False
        if text_to_flush:
            self._callback(text_to_flush)

    def flush(self):
        pass

    def isatty(self):
        return True


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
                line = self._queue.get(block=True, timeout=0.1)
                return line if line.endswith("\n") else line + "\n"
            except queue.Empty:
                continue

    def read(self, size=-1):
        return self.readline(size)

    def isatty(self):
        return True


class StreamManager:
    # Accept the main scheduling function here
    def __init__(self, log_callback, schedule_callback, input_queue, stop_event=None, status_callback=None):
        self._log_callback = log_callback
        self._schedule_callback = schedule_callback
        self._input_queue = input_queue
        self._stop_event = stop_event
        self._status_callback = status_callback

        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._original_stdin  = sys.stdin

    def redirect(self):
        # Pass both callbacks down to the writer stream
        sys.stdout = _StreamRedirector(self._log_callback, self._schedule_callback)
        sys.stderr = _StreamRedirector(self._log_callback, self._schedule_callback)
        sys.stdin  = _InteractiveInputReader(
            self._input_queue,
            stop_event=self._stop_event,
            status_callback=self._status_callback,
        )

    def restore(self):
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        sys.stdin  = self._original_stdin