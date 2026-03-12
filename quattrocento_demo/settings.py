from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .protocol import (
    DEFAULT_CONF2_BYTE,
    DEFAULT_FORCE_CHANNELS,
    DEFAULT_INPUT_CONF2_BYTES,
    HPF_HZ_TO_BITS,
    INPUT_BLOCK_INDEX,
    INPUT_BLOCK_NAMES,
    LPF_HZ_TO_BITS,
    MODE_NAME_TO_BITS,
    NCH_BITS_TO_NUM_CHANNELS,
    SIDE_NAME_TO_BITS,
    SUPPORTED_SAMPLE_RATES,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return int(value)


def _coerce_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError(f"{field_name} must be a boolean")


def _coerce_channel_indices(raw_values: Sequence[Any], field_name: str) -> tuple[int, ...]:
    coerced: list[int] = []
    for value in raw_values:
        coerced.append(_coerce_int(value, field_name))
    if not coerced:
        raise ValueError(f"{field_name} cannot be empty")
    return tuple(coerced)


def _normalize_token(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _parse_lookup_or_bits(
    value: Any, *, field_name: str, name_to_bits: Mapping[str, int], allow_bit_3: bool = True
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a string or integer")

    if isinstance(value, int):
        upper = 3 if allow_bit_3 else 2
        if 0 <= value <= upper:
            return value

    token = _normalize_token(value)
    if token in name_to_bits:
        return name_to_bits[token]

    raise ValueError(f"Unsupported {field_name} value: {value!r}")


def _parse_filter_bits(value: Any, *, field_name: str, hz_to_bits: Mapping[float, int]) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a frequency or bit value")

    if isinstance(value, int) and 0 <= value <= 3:
        return value

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported {field_name} value: {value!r}") from exc

    for hz, bits in hz_to_bits.items():
        if abs(numeric - hz) < 1e-9:
            return bits
    raise ValueError(f"Unsupported {field_name} value: {value!r}")


def _parse_conf2_block(
    raw_block: Mapping[str, Any] | None, *, default_byte: int, block_name: str
) -> int:
    if raw_block is None:
        return default_byte
    if not isinstance(raw_block, Mapping):
        raise ValueError(f"{block_name} must be a TOML table")

    side_bits = (default_byte >> 6) & 0b11
    hpf_bits = (default_byte >> 4) & 0b11
    lpf_bits = (default_byte >> 2) & 0b11
    mode_bits = default_byte & 0b11

    allowed = {"side", "hpf", "lpf", "mode"}
    unknown_fields = set(raw_block.keys()) - allowed
    if unknown_fields:
        unknown = ", ".join(sorted(unknown_fields))
        raise ValueError(f"{block_name} has unknown field(s): {unknown}")

    if "side" in raw_block:
        side_bits = _parse_lookup_or_bits(
            raw_block["side"],
            field_name=f"{block_name}.side",
            name_to_bits=SIDE_NAME_TO_BITS,
        )
    if "hpf" in raw_block:
        hpf_bits = _parse_filter_bits(
            raw_block["hpf"],
            field_name=f"{block_name}.hpf",
            hz_to_bits=HPF_HZ_TO_BITS,
        )
    if "lpf" in raw_block:
        lpf_bits = _parse_filter_bits(
            raw_block["lpf"],
            field_name=f"{block_name}.lpf",
            hz_to_bits=LPF_HZ_TO_BITS,
        )
    if "mode" in raw_block:
        mode_bits = _parse_lookup_or_bits(
            raw_block["mode"],
            field_name=f"{block_name}.mode",
            name_to_bits=MODE_NAME_TO_BITS,
        )

    return (side_bits << 6) | (hpf_bits << 4) | (lpf_bits << 2) | mode_bits


def _parse_conf2_overrides(
    raw_overrides: Mapping[str, Any] | None, *, default_byte: int
) -> tuple[int, ...]:
    conf2_bytes = [default_byte for _ in range(len(INPUT_BLOCK_NAMES))]
    if raw_overrides is None:
        return tuple(conf2_bytes)
    if not isinstance(raw_overrides, Mapping):
        raise ValueError("conf2_overrides must be a TOML table")

    for raw_name, raw_block in raw_overrides.items():
        name_token = str(raw_name).upper().replace(" ", "_")
        block_idx = INPUT_BLOCK_INDEX.get(name_token)
        if block_idx is None:
            raise ValueError(
                f"Unknown conf2_overrides key {raw_name!r}. "
                f"Expected one of: {', '.join(INPUT_BLOCK_NAMES)}"
            )
        conf2_bytes[block_idx] = _parse_conf2_block(
            raw_block,
            default_byte=default_byte,
            block_name=f"conf2_overrides.{raw_name}",
        )
    return tuple(conf2_bytes)


@dataclass(slots=True, frozen=True)
class SocketStreamSettings:
    """Settings for a real Quattrocento socket stream."""

    host: str = "169.254.1.10"
    port: int = 23456
    force_channel_indices: tuple[int, ...] = DEFAULT_FORCE_CHANNELS
    aux_in_channel_index: int = 10
    decimation_enabled: bool = True
    socket_read_size: int = 65536
    rec_on: bool = False
    fsamp: int = 512
    nch: int = 3
    input_conf2_bytes: tuple[int, ...] = DEFAULT_INPUT_CONF2_BYTES

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("host cannot be empty")
        if self.port <= 0:
            raise ValueError("port must be positive")
        if self.socket_read_size <= 0:
            raise ValueError("socket_read_size must be positive")
        if not self.force_channel_indices:
            raise ValueError("force_channel_indices cannot be empty")
        if self.fsamp not in SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                f"fsamp must be one of {SUPPORTED_SAMPLE_RATES}, got {self.fsamp}"
            )
        if self.nch not in NCH_BITS_TO_NUM_CHANNELS:
            raise ValueError("nch must be one of 0, 1, 2, 3")
        if len(self.input_conf2_bytes) != len(INPUT_BLOCK_NAMES):
            raise ValueError(
                f"input_conf2_bytes must contain {len(INPUT_BLOCK_NAMES)} entries"
            )
        for conf2 in self.input_conf2_bytes:
            if conf2 < 0 or conf2 > 255:
                raise ValueError("input_conf2_bytes must contain values in [0, 255]")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SocketStreamSettings:
        """Create settings from a TOML-compatible mapping."""
        allowed_fields = {
            "host",
            "port",
            "force_channel_indices",
            "aux_in_channel_index",
            "decimation_enabled",
            "socket_read_size",
            "rec_on",
            "fsamp",
            "nch",
            "conf2_defaults",
            "conf2_overrides",
        }
        unknown_fields = set(payload.keys()) - allowed_fields
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unknown socket settings field(s): {unknown}")

        defaults = cls()

        host = str(payload.get("host", defaults.host))
        port = _coerce_int(payload.get("port", defaults.port), "port")
        aux_channel = _coerce_int(
            payload.get("aux_in_channel_index", defaults.aux_in_channel_index),
            "aux_in_channel_index",
        )
        socket_read_size = _coerce_int(
            payload.get("socket_read_size", defaults.socket_read_size),
            "socket_read_size",
        )
        decimation_enabled = _coerce_bool(
            payload.get("decimation_enabled", defaults.decimation_enabled),
            "decimation_enabled",
        )
        rec_on = _coerce_bool(payload.get("rec_on", defaults.rec_on), "rec_on")
        fsamp = _coerce_int(payload.get("fsamp", defaults.fsamp), "fsamp")
        nch = _coerce_int(payload.get("nch", defaults.nch), "nch")

        raw_force_channels = payload.get("force_channel_indices", defaults.force_channel_indices)
        if not isinstance(raw_force_channels, Sequence) or isinstance(raw_force_channels, str):
            raise ValueError("force_channel_indices must be a sequence of integers")
        force_channel_indices = _coerce_channel_indices(
            raw_force_channels, "force_channel_indices"
        )

        conf2_defaults = _parse_conf2_block(
            payload.get("conf2_defaults"),
            default_byte=DEFAULT_CONF2_BYTE,
            block_name="conf2_defaults",
        )
        input_conf2_bytes = _parse_conf2_overrides(
            payload.get("conf2_overrides"),
            default_byte=conf2_defaults,
        )

        return cls(
            host=host,
            port=port,
            force_channel_indices=force_channel_indices,
            aux_in_channel_index=aux_channel,
            decimation_enabled=decimation_enabled,
            socket_read_size=socket_read_size,
            rec_on=rec_on,
            fsamp=fsamp,
            nch=nch,
            input_conf2_bytes=input_conf2_bytes,
        )

    @classmethod
    def from_toml_file(cls, path: str | Path) -> SocketStreamSettings:
        """Load settings from a TOML file path."""
        config_path = Path(path)
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
        return cls.from_dict(payload)
