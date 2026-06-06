from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class IngestStreamEvent:
    event: str
    data: str = ""


class IngestEventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[IngestStreamEvent]] = set()
        self._current_lines: list[str] = []
        self._last_completed_lines: list[str] = []
        self._active_run_id: int | None = None

    def subscribe(self) -> tuple[queue.Queue[IngestStreamEvent], list[IngestStreamEvent]]:
        subscriber: queue.Queue[IngestStreamEvent] = queue.Queue()
        with self._lock:
            lines = self._current_lines if self._active_run_id is not None else self._last_completed_lines
            replay = [IngestStreamEvent("reset"), *(IngestStreamEvent("line", line) for line in lines)]
            self._subscribers.add(subscriber)
        return subscriber, replay

    def unsubscribe(self, subscriber: queue.Queue[IngestStreamEvent]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def start_run(self, run_id: int, header_line: str) -> None:
        with self._lock:
            self._active_run_id = run_id
            self._current_lines = []
            subscribers = list(self._subscribers)
        self._broadcast(IngestStreamEvent("reset"), subscribers)
        self.append_line(header_line)

    def append_line(self, line: str) -> None:
        event = IngestStreamEvent("line", line)
        with self._lock:
            if self._active_run_id is not None:
                self._current_lines.append(line)
            subscribers = list(self._subscribers)
        self._broadcast(event, subscribers)

    def complete_run(self, summary_line: str) -> None:
        self.append_line(summary_line)
        with self._lock:
            self._last_completed_lines = list(self._current_lines)
            self._current_lines = []
            self._active_run_id = None

    def snapshot_last_completed(self) -> list[str]:
        with self._lock:
            return list(self._last_completed_lines)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._current_lines = []
            self._last_completed_lines = []
            self._active_run_id = None
            subscribers = list(self._subscribers)
        self._broadcast(IngestStreamEvent("reset"), subscribers)

    def _broadcast(
        self,
        event: IngestStreamEvent,
        subscribers: list[queue.Queue[IngestStreamEvent]] | None = None,
    ) -> None:
        targets = subscribers
        if targets is None:
            with self._lock:
                targets = list(self._subscribers)
        for subscriber in targets:
            subscriber.put(event)


ingest_events = IngestEventHub()


def format_sse_event(event: IngestStreamEvent) -> str:
    payload = [f"event: {event.event}"]
    if event.data:
        for line in event.data.splitlines():
            payload.append(f"data: {line}")
    else:
        payload.append("data:")
    return "\n".join(payload) + "\n\n"


def stream_ingest_events() -> Iterator[str]:
    subscriber, replay = ingest_events.subscribe()
    try:
        for event in replay:
            yield format_sse_event(event)
        while True:
            try:
                yield format_sse_event(subscriber.get(timeout=15))
            except queue.Empty:
                yield ": heartbeat\n\n"
    except GeneratorExit:
        return
    finally:
        ingest_events.unsubscribe(subscriber)
