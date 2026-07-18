from collections import deque
import threading
import queue
import sys

from common import PromptCancelledError

class _StreamRedirector:
	def __init__(self, callback, schedule_callback, original_stream):
		self._callback = callback
		self._schedule_callback = schedule_callback
		self._original_stream = original_stream
		
		self._buffer = deque()
		self._lock = threading.Lock()
		self._flush_scheduled = False

		self.encoding = getattr(original_stream, "encoding", "utf-8")
		self.errors = getattr(original_stream, "errors", "strict")

	def write(self, text):
		if not text:
			return 0

		if self._original_stream is not None:
			self._original_stream.write(text)
		self._buffer.append(text)
		
		with self._lock:
			if not self._flush_scheduled:
				self._flush_scheduled = True
				self._schedule_callback(30, self._batch_flush)
				
		return len(text)

	def flush(self):
		if self._original_stream is not None:
			self._original_stream.flush()

	def _batch_flush(self):
		with self._lock:
			chunks = list(self._buffer)
			self._buffer.clear()
			self._flush_scheduled = False
		
		if chunks:
			text_to_flush = "".join(chunks)
			self._callback(text_to_flush)


class _InteractiveInputReader:
	def __init__(self, input_queue, original_stdin, stop_event=None, status_callback=None):
		self._queue = input_queue
		self._original_stdin = original_stdin
		self._stop_event = stop_event
		self._status_callback = status_callback
		self.encoding = getattr(original_stdin, "encoding", "utf-8")

	def _notify_waiting(self):
		if self._status_callback:
			self._status_callback("Awaiting user input...")

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

	def isatty(self):
		return self._original_stdin.isatty() if self._original_stdin is not None else False


class StreamManager:
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
		sys.stdout = _StreamRedirector(self._log_callback, self._schedule_callback, None)
		sys.stderr = _StreamRedirector(self._log_callback, self._schedule_callback, None)
		sys.stdin  = _InteractiveInputReader(
			self._input_queue,
			self._original_stdin,
			stop_event=self._stop_event,
			status_callback=self._status_callback,
		)

	def restore(self):
		sys.stdout = self._original_stdout
		sys.stderr = self._original_stderr
		sys.stdin  = self._original_stdin