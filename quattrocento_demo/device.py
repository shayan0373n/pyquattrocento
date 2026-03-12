from __future__ import annotations

from abc import ABC, abstractmethod
import socket

import numpy as np
from numpy.typing import NDArray

from .config import DemoConfig
from .models import DataBatch
from .protocol import NCH_BITS_TO_NUM_CHANNELS, build_quattrocento_command
from .settings import SocketStreamSettings


class QuattrocentoStream(ABC):
    """Abstract batch stream API used by the controller."""

    @abstractmethod
    def read_batch(self) -> DataBatch:
        """Read the next batch of samples from the data source."""

    def close(self) -> None:
        """Release any underlying resources."""


class MockQuattrocentoStream(QuattrocentoStream):
    """Deterministic mock source that simulates force sensors and AUX-in pulses."""

    def __init__(
        self,
        config: DemoConfig,
        trigger_interval_seconds: float = 8.0,
        trigger_duration_seconds: float = 0.03,
        trigger_start_delay_seconds: float = 1.0,
        random_seed: int = 7,
    ) -> None:
        """Initialize mock signal and AUX-in trigger generation."""
        if trigger_interval_seconds <= 0:
            raise ValueError("trigger_interval_seconds must be positive")
        if trigger_duration_seconds <= 0:
            raise ValueError("trigger_duration_seconds must be positive")
        if trigger_start_delay_seconds < 0:
            raise ValueError("trigger_start_delay_seconds cannot be negative")

        self._config = config
        self._trigger_interval_seconds = trigger_interval_seconds
        self._trigger_duration_seconds = trigger_duration_seconds
        self._trigger_start_delay_seconds = trigger_start_delay_seconds
        self._sample_index = 0
        self._samples_per_batch = max(
            1, int(round(config.sample_rate_hz * config.batch_duration_seconds))
        )
        self._rng = np.random.default_rng(random_seed)

        sensor_count = config.sensor_count
        self._phase_offsets = np.linspace(0.1, 2.2, sensor_count, endpoint=True)
        self._base_frequencies_hz = np.linspace(0.28, 0.7, sensor_count, endpoint=True)
        self._event_profile = np.linspace(7.0, 12.0, sensor_count, endpoint=True)

    def read_batch(self) -> DataBatch:
        """Return the next fixed-size time block of synthesized data."""
        sample_indices = np.arange(
            self._sample_index, self._sample_index + self._samples_per_batch, dtype=np.int64
        )
        timestamps = sample_indices.astype(np.float64) / self._config.sample_rate_hz
        forces = self._synthesize_forces(timestamps)
        aux_in = self._synthesize_aux_in(timestamps)

        self._sample_index += self._samples_per_batch
        return DataBatch(timestamps=timestamps, forces=forces, aux_in=aux_in)

    def _synthesize_forces(self, timestamps: NDArray[np.float64]) -> NDArray[np.float64]:
        base_force = 18.0 + (
            2.7
            * np.sin(
                2.0
                * np.pi
                * self._base_frequencies_hz[np.newaxis, :]
                * timestamps[:, np.newaxis]
                + self._phase_offsets[np.newaxis, :]
            )
        )
        slow_modulation = 0.8 * np.sin(
            2.0 * np.pi * 0.6 * timestamps[:, np.newaxis]
            + (0.6 * self._phase_offsets[np.newaxis, :])
        )
        noise = self._rng.normal(0.0, 0.35, size=base_force.shape)

        event_envelope = self._event_envelope(timestamps)
        event_response = event_envelope[:, np.newaxis] * self._event_profile[np.newaxis, :]

        forces = base_force + slow_modulation + noise + event_response
        return np.clip(forces, a_min=0.0, a_max=None)

    def _synthesize_aux_in(self, timestamps: NDArray[np.float64]) -> NDArray[np.float64]:
        baseline = 0.06 * np.sin(2.0 * np.pi * 0.45 * timestamps)
        noise = self._rng.normal(0.0, 0.025, size=timestamps.shape[0])
        trigger = baseline + noise

        active_mask = timestamps >= self._trigger_start_delay_seconds
        if np.any(active_mask):
            phase = np.mod(
                timestamps[active_mask] - self._trigger_start_delay_seconds,
                self._trigger_interval_seconds,
            )
            pulse = (phase < self._trigger_duration_seconds).astype(np.float64)
            trigger[active_mask] += 1.2 * pulse

        return np.clip(trigger, a_min=0.0, a_max=1.5)

    def _event_envelope(self, timestamps: NDArray[np.float64]) -> NDArray[np.float64]:
        event = np.zeros_like(timestamps, dtype=np.float64)
        active_mask = timestamps >= self._trigger_start_delay_seconds
        if not np.any(active_mask):
            return event

        phase = np.mod(
            timestamps[active_mask] - self._trigger_start_delay_seconds,
            self._trigger_interval_seconds,
        )
        event[active_mask] = np.exp(-0.5 * np.square((phase - 1.15) / 0.55))
        return event


class SocketQuattrocentoStream(QuattrocentoStream):
    """TCP stream client for a real Quattrocento device."""

    def __init__(self, config: DemoConfig, settings: SocketStreamSettings) -> None:
        """Initialize socket stream configuration and channel mapping."""
        if config.sample_rate_hz != settings.fsamp:
            raise ValueError(
                "DemoConfig sample_rate_hz must match socket settings fsamp "
                f"({config.sample_rate_hz} != {settings.fsamp})"
            )
        if settings.fsamp % 16 != 0:
            raise ValueError("fsamp must be divisible by 16 in socket mode")

        self._config = config
        self._settings = settings
        self._host = settings.host
        self._port = settings.port
        self._num_channels = NCH_BITS_TO_NUM_CHANNELS[settings.nch]
        self._samples_per_packet = settings.fsamp // 16
        self._bytes_per_packet = 2 * self._num_channels * self._samples_per_packet
        self._socket_read_size = settings.socket_read_size
        self._sample_index = 0

        self._force_channel_indices = settings.force_channel_indices
        self._aux_in_channel_index = settings.aux_in_channel_index
        self._validate_channel_selection()

        self._socket: socket.socket | None = None
        self._byte_buffer = bytearray()

    def read_batch(self) -> DataBatch:
        """Read all complete packets currently available from the TCP stream."""
        self._ensure_connected()
        self._drain_socket()

        packet_count = len(self._byte_buffer) // self._bytes_per_packet
        if packet_count == 0:
            return self._empty_batch()

        bytes_to_parse = packet_count * self._bytes_per_packet
        raw = bytes(self._byte_buffer[:bytes_to_parse])
        del self._byte_buffer[:bytes_to_parse]

        sample_count = packet_count * self._samples_per_packet
        channel_matrix = np.frombuffer(raw, dtype="<i2").reshape(sample_count, self._num_channels)
        force_matrix = channel_matrix[:, self._force_channel_indices].astype(np.float64)
        aux_in = channel_matrix[:, self._aux_in_channel_index].astype(np.float64)

        sample_indices = np.arange(
            self._sample_index, self._sample_index + sample_count, dtype=np.int64
        )
        timestamps = sample_indices.astype(np.float64) / self._config.sample_rate_hz
        self._sample_index += sample_count

        return DataBatch(timestamps=timestamps, forces=force_matrix, aux_in=aux_in)

    def close(self) -> None:
        """Stop acquisition and close the TCP socket."""
        if self._socket is None:
            return

        try:
            self._socket.setblocking(True)
            stop_command = self._build_command(start_acquisition=False)
            self._socket.sendall(stop_command)
        except OSError:
            pass
        finally:
            try:
                self._socket.close()
            finally:
                self._socket = None
                self._byte_buffer.clear()

    def _validate_channel_selection(self) -> None:
        if len(self._force_channel_indices) != self._config.sensor_count:
            raise ValueError(
                "force_channel_indices must contain exactly "
                f"{self._config.sensor_count} channels"
            )
        if len(set(self._force_channel_indices)) != len(self._force_channel_indices):
            raise ValueError("force_channel_indices must not contain duplicates")

        for channel_index in self._force_channel_indices:
            self._validate_channel_index(channel_index, "force channel")
        self._validate_channel_index(self._aux_in_channel_index, "aux_in_channel_index")

    def _validate_channel_index(self, channel_index: int, label: str) -> None:
        if channel_index < 0 or channel_index >= self._num_channels:
            raise ValueError(
                f"{label} index {channel_index} must be between 0 and {self._num_channels - 1}"
            )

    def _ensure_connected(self) -> None:
        if self._socket is not None:
            return

        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tcp_socket.settimeout(3.0)
            tcp_socket.connect((self._host, self._port))
            start_command = self._build_command(start_acquisition=True)
            tcp_socket.sendall(start_command)
            tcp_socket.setblocking(False)
        except BaseException:
            tcp_socket.close()
            raise
        self._socket = tcp_socket

    def _build_command(self, *, start_acquisition: bool) -> bytes:
        return build_quattrocento_command(
            decimation_enabled=self._settings.decimation_enabled,
            rec_on=self._settings.rec_on,
            fsamp=self._settings.fsamp,
            nch=self._settings.nch,
            input_conf2_bytes=self._settings.input_conf2_bytes,
            start_acquisition=start_acquisition,
        )

    def _drain_socket(self) -> None:
        if self._socket is None:
            return

        while True:
            try:
                chunk = self._socket.recv(self._socket_read_size)
            except BlockingIOError:
                return
            except InterruptedError:
                continue

            if not chunk:
                raise ConnectionError("Quattrocento socket closed the connection")

            self._byte_buffer.extend(chunk)
            if len(chunk) < self._socket_read_size:
                return

    def _empty_batch(self) -> DataBatch:
        return DataBatch(
            timestamps=np.empty(0, dtype=np.float64),
            forces=np.empty((0, self._config.sensor_count), dtype=np.float64),
            aux_in=np.empty(0, dtype=np.float64),
        )
