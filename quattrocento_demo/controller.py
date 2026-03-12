from __future__ import annotations

from collections import deque

from PyQt5 import QtCore

from .config import DemoConfig
from .device import QuattrocentoStream
from .models import CapturedWindow
from .processing import TriggerWindowProcessor
from .ui import DemoMainWindow

_DEFAULT_MAX_HISTORY = 200


class DemoController(QtCore.QObject):
    """Coordinate stream polling, trigger processing, and UI updates."""

    def __init__(
        self,
        config: DemoConfig,
        stream: QuattrocentoStream,
        processor: TriggerWindowProcessor,
        window: DemoMainWindow,
        max_history: int = _DEFAULT_MAX_HISTORY,
    ) -> None:
        super().__init__()
        self._config = config
        self._stream = stream
        self._processor = processor
        self._window = window
        self._history: deque[CapturedWindow] = deque(maxlen=max_history)
        self._current_event_index: int | None = None

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        self._window.previous_requested.connect(self._show_previous_event)
        self._window.next_requested.connect(self._show_next_event)

    def start(self) -> None:
        """Show the window and start periodic acquisition updates."""
        self._refresh_status()
        self._window.show()
        self._timer.start(self._config.ui_refresh_ms)

    def _on_timer_tick(self) -> None:
        try:
            batch = self._stream.read_batch()
        except Exception:
            self._timer.stop()
            self._window.set_stream_error()
            return

        captured = self._processor.process_batch(batch)

        if captured is not None:
            self._append_capture(captured)

        self._refresh_status()

    def _append_capture(self, captured: CapturedWindow) -> None:
        was_showing_latest = self._current_event_index is None or (
            self._current_event_index == len(self._history) - 1
        )
        was_full = len(self._history) == self._history.maxlen
        self._history.append(captured)
        self._window.set_last_trigger_now()

        # When the deque evicts the oldest entry, shift the viewed index back.
        # If the user is viewing index 0, the evicted event is silently replaced
        # by its neighbor rather than clearing the view.
        if was_full and self._current_event_index is not None and not was_showing_latest:
            self._current_event_index = max(0, self._current_event_index - 1)

        if was_showing_latest:
            self._current_event_index = len(self._history) - 1
            self._window.update_capture(captured)

    def _show_previous_event(self) -> None:
        if self._current_event_index is None or self._current_event_index <= 0:
            return
        self._current_event_index -= 1
        self._window.update_capture(self._history[self._current_event_index])
        self._refresh_status()

    def _show_next_event(self) -> None:
        if self._current_event_index is None:
            return
        if self._current_event_index >= len(self._history) - 1:
            return
        self._current_event_index += 1
        self._window.update_capture(self._history[self._current_event_index])
        self._refresh_status()

    def _refresh_status(self) -> None:
        self._window.set_stream_state(
            sample_rate_hz=self._config.sample_rate_hz,
            captures=len(self._history),
            capturing=self._processor.is_capturing,
        )
        self._window.set_event_navigation(
            current_index=self._current_event_index,
            total_events=len(self._history),
        )
