# DextView: Triggered Force & EMG Capture Application

Python/PyQt5 GUI for force and EMG capture from the **OT Bioelettronica Quattrocento**. Supports calibration, trigger-based event capture, and LabJack TTL feedback.

---

## Features

- **Connects to the Quattrocento** in three modes: direct, rebroadcast through OT BioLab+, or proxy. See [User Guide §2](USER_GUIDE.md#2-choosing-a-connection-mode).
- **Real-time visualization** of force, EMG, and trigger channels, with toggleable bandpass (10–500 Hz) and powerline-notch (50/100/150 Hz) filters on EMG.
- **Calibration system** (rest, MVC, zero) with save/load to NumPy `.npz` files. Plots can be displayed in % MVC once calibrated.
- **Trigger-based capture** of fixed-length windows around analog trigger events, with per-finger force profiles, peak-to-peak readouts, and auto onset detection.
- **Closed-loop feedback hooks** that emit LabJack TTL pulses on configurable force conditions.
- **JSON event logging** of every captured window. See [User Guide §7](USER_GUIDE.md#7-logging-captures).

---

## Installation

### Prerequisites

- **Python 3.14** or later
- **Optional**: Python environment manager (e.g., Conda)

### Quick Setup
1.  **Clone the repository** and navigate to the project directory:
    ```bash
    git clone https://github.com/shayan0373n/dextview.git
    cd dextview
    ```

2.  **Activate your environment** (e.g., using `dexterity`):
    ```bash
    conda activate dexterity
    ```

3.  **Install DextView**:
    Regular install:
    ```bash
    pip install .
    ```
    Editable install (for development):
    ```bash
    pip install -e .
    ```
    Both install dependencies and register the `dextview` command.

---

## Usage

See the **[User Guide](USER_GUIDE.md)** for the full workflow; per-mode launch commands are in [§2 Choosing a Connection Mode](USER_GUIDE.md#2-choosing-a-connection-mode). Run `dextview --help` for the full flag list.

### Quick start

**No hardware (bundled simulator).** Run the synthetic device in one terminal:
```bash
python run_simulator.py --trigger-interval 8.0
```
and DextView in another, connected to it in rebroadcast mode:
```bash
dextview --source rebroadcast \
         --channels configs/channels_simulator.toml \
         --host 127.0.0.1 --port 31000
```

**Real device (direct connection).**
```bash
dextview --source real \
         --channels configs/channels_default.toml \
         --host 169.254.1.10 --port 23456 \
         --sample-rate 2048 --n-channels 16 \
         --conf2-config configs/quattrocento_conf2.toml
```

---

## Testing

Run from the repository root:
```bash
python -m pytest
```

---

## Repository Architecture

```
├── configs/          # TOML config: channel maps and hardware (conf2) settings
├── dextview/         # Core Python package (stream I/O, processing, hooks, PyQt5 UI)
│   ├── hooks/        # Low-latency feedback hooks and HUD widgets
│   └── stream/       # Connection sources: direct, rebroadcast, proxy
├── tests/            # Unit and integration tests
├── pyproject.toml    # Package metadata and the `dextview` entry point
├── run_dextview.py   # Convenience script to run the GUI
└── run_simulator.py  # Convenience script to run the simulator
```

Within `dextview/`, the flow runs roughly `app.py` (entry point and CLI) → `controller.py` (wiring) → `stream/`, `processing.py`, `hooks/`, and `ui.py`.
