from __future__ import annotations

import argparse
import sys

from PyQt5 import QtWidgets

from .config import QuattrocentoConfig
from .controller import QuattrocentoController
from .device import (
    MockQuattrocentoStream,
    QuattrocentoStream,
    SocketQuattrocentoStream,
)
from .settings import SocketStreamSettings
from .processing import TriggerWindowProcessor
from .ui import QuattrocentoMainWindow


def load_socket_settings(path: str) -> SocketStreamSettings:
    """Load socket-stream settings from a TOML configuration file."""
    try:
        return SocketStreamSettings.from_toml_file(path)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        raise SystemExit(f"Failed to load socket config {path!r}: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the Quattrocento application."""
    parser = argparse.ArgumentParser(
        description="Run a mocked Quattrocento trigger-based force GUI application."
    )
    parser.add_argument(
        "--source",
        choices=("mock", "real"),
        default="mock",
        help="Data source type.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=512,
        help="Sample rate in Hz (used for mock source; real source uses socket config fsamp).",
    )
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=5.0,
        help="Capture window length after trigger.",
    )
    parser.add_argument(
        "--trigger-threshold",
        type=float,
        default=0.5,
        help="Trigger detection threshold.",
    )
    parser.add_argument(
        "--trigger-interval",
        type=float,
        default=8.0,
        help="How often the mock trigger pulse appears.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Seed for deterministic mock data generation.",
    )
    parser.add_argument(
        "--socket-config",
        type=str,
        default="quattrocento/socket_stream_config.toml",
        help="TOML config path for --source real.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Create and run the GUI application event loop."""
    args = parse_args(argv)

    qt_app = QtWidgets.QApplication.instance()
    if qt_app is None:
        qt_app = QtWidgets.QApplication(sys.argv)

    stream: QuattrocentoStream
    if args.source == "real":
        socket_settings = load_socket_settings(args.socket_config)
        config = QuattrocentoConfig(
            sample_rate_hz=socket_settings.fsamp,
            window_seconds=args.window_seconds,
            trigger_threshold=args.trigger_threshold,
        )
        stream = SocketQuattrocentoStream(
            config=config,
            settings=socket_settings,
        )
    else:
        config = QuattrocentoConfig(
            sample_rate_hz=args.sample_rate,
            window_seconds=args.window_seconds,
            trigger_threshold=args.trigger_threshold,
        )
        stream = MockQuattrocentoStream(
            config=config,
            trigger_interval_seconds=args.trigger_interval,
            random_seed=args.seed,
        )

    processor = TriggerWindowProcessor(config)
    window = QuattrocentoMainWindow(config.finger_labels)
    controller = QuattrocentoController(config, stream, processor, window)
    controller.start()

    try:
        return qt_app.exec_()
    finally:
        stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
