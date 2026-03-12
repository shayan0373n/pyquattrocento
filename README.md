Quattrocento Trigger Demo

A modular GUI demo app with a mocked Quattrocento stream is available at:

- `run_quattrocento_demo.py`
- package: `quattrocento_demo/`

Run it with:

`python run_quattrocento_demo.py`

The demo uses:

- 10 force sensors mapped one-to-one to 10 fingers
- analog AUX-in trigger detection
- event history with Back/Forward buttons and Left/Right arrow key navigation

Real Quattrocento Source
Use `--source real` and configure socket/channel settings in:

- `quattrocento_demo/socket_stream_config.toml`

The TOML file exposes:

- `rec_on`, `fsamp`, `nch`, `decimation_enabled` (`ACQ_SETT` bits)
- `force_channel_indices`, `aux_in_channel_index`
- `conf2_defaults` and `conf2_overrides` for per-input `hpf` / `lpf` / `mode` (and `side`)

Run with:

`python run_quattrocento_demo.py --source real`
