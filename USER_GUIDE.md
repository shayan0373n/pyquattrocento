# DextView User Guide

Usage guide for DextView. For installation and architecture, see [README.md](README.md).

---

## 1. Before You Start

DextView captures fixed-length windows of force and EMG around analog trigger events from a Quattrocento amplifier. Signals can be calibrated against rest and maximum-voluntary-contraction (MVC) references so force is read in % MVC. Captured windows are plotted per finger and, when `--log-dir` is set, written to JSON; a feedback hook can additionally fire a LabJack TTL pulse when a force condition is met. A full session runs end-to-end as listed under **Session at a glance** below.

**You will need:**
- A computer with DextView installed (see README → Installation).
- One of: a Quattrocento device on the network, the OT BioLab+ application running locally, or the bundled simulator for dry runs.
- *(Optional)* A LabJack T4 connected via USB, if you plan to use closed-loop feedback hooks.
- A channel mapping file (`configs/channels_default.toml` is the starting point).

**Session at a glance:**
1. Pick a connection mode and launch DextView.
2. Verify the live signal looks right.
3. Calibrate (Rest → MVC → optionally Zero).
4. *(Optional)* Arm a feedback hook.
5. Run the task; captures are logged automatically if `--log-dir` is set.
6. Review captures in the visualizer; save calibration before closing.

---

## 2. Choosing a Connection Mode

DextView supports three connection modes:

| Situation | Mode |
| :--- | :--- |
| Lowest latency; manual hardware configuration acceptable | **Direct** |
| OT BioLab+ is already configured | **Rebroadcast** |
| OT BioLab+ records while DextView taps the stream for low-latency hooks | **Proxy** |
| No hardware available; testing the GUI | **Simulator + Rebroadcast** |

### 2.1 Direct (`--source real`)
*DextView connects straight to the Quattrocento hardware.*

- **Use when:** lowest latency is required and OT BioLab+ is not needed.
- **Setup:**
  1. Launch DextView with `--source real`, `--host`/`--port` pointed at the device, an explicit `--sample-rate` (one of 512, 2048, 5120, 10240 Hz — `auto` is rejected here), and `--n-channels`.
  2. `--n-channels` is the *minimum* you need; the device rounds up to the next supported group (120, 216, 312, or 408 channels), and your TOML indices must fall within that rounded-up width.
  3. Optionally pass `--conf2-config` for per-input-block HPF/LPF/mode/side, `--rec-on` to enable on-device recording, and `--no-decimation` to sample directly instead of decimating from 10240 Hz.

  ```bash
  dextview --source real --channels configs/channels_default.toml \
           --host 169.254.1.10 --port 23456 \
           --sample-rate 2048 --n-channels 16 \
           --conf2-config configs/quattrocento_conf2.toml
  ```
- **Channel ordering:** the last 24 channels in the stream are always the 16 AUX channels followed by the 8 accessory channels — TOML channel indices must account for this.
- **Tradeoffs:** lowest latency; hardware must be configured manually.

### 2.2 Rebroadcast (`--source rebroadcast`)
*DextView listens to a stream that OT BioLab+ is broadcasting locally.*

- **Use when:** OT BioLab+ is already handling hardware configuration and DextView only needs to overlay its analysis.
- **Setup:**
  1. In OT BioLab+, start acquisition and enable the local rebroadcast/TCP output (default port `31000`).
  2. Launch DextView with `--source rebroadcast` and `--host 127.0.0.1 --port 31000`.
  3. Leave `--n-channels` and `--sample-rate` unset (both default to `auto` in this mode) to read them from the stream header, or pass explicit integers if you already know them.

  ```bash
  dextview --source rebroadcast --channels configs/channels_default.toml \
           --host 127.0.0.1 --port 31000 \
           --sample-rate auto --n-channels auto --log-dir ./capture_logs
  ```
- **Auto-detection:** set `--n-channels auto` and `--sample-rate auto` to read these from the OT BioLab+ stream header.
- **Channel ordering:** indices match the channels activated in OT BioLab+, with the last 8 channels always being the accessory channels. **Changing OT BioLab+'s channel selection requires updating the TOML mapping.**
- **Tradeoffs:** easiest setup; rebroadcast adds buffering delay — not ideal for time-sensitive hooks.

### 2.3 Proxy (`--source proxy`)
*DextView sits between the device and OT BioLab+, forwarding commands and tapping the data stream.*

- **Use when:** OT BioLab+ must keep recording while DextView taps the stream first for low-latency hooks.
- **Setup:**
  1. Launch DextView in proxy mode with `--host` pointing at the device and `--proxy-listen-host`/`--proxy-listen-port` set to a local address.
  2. In OT BioLab+, change the target device IP to the proxy address (typically `127.0.0.1`).
  3. Start acquisition in OT BioLab+. It connects to DextView, which forwards to the device.

  ```bash
  dextview --source proxy --channels configs/channels_default.toml \
           --host 169.254.1.10 --port 23456 \
           --proxy-listen-host 127.0.0.1 --proxy-listen-port 31001
  ```
- **Channel ordering:** same as Direct mode.
- **Tradeoffs:** OT BioLab+ records normally and DextView gets first-hand data; requires reconfiguring OT BioLab+'s target IP.

### 2.4 Simulator (dry run)
*A bundled fake device that emits synthetic force and trigger signals; all other channels carry low-amplitude noise.*

- **Use when:** practicing the workflow, demoing, or testing without hardware.
- **Setup:** run `python run_simulator.py --trigger-interval 8.0` in one terminal, then launch DextView in `rebroadcast` mode with `--channels configs/channels_simulator.toml` pointed at `127.0.0.1:31000`.
- **Channel mapping:** the simulator always streams a fixed layout — synthetic force on channels 0–9 and the trigger pulse on channel 10. `configs/channels_simulator.toml` matches this layout. The bundled `configs/channels_default.toml` is an example mapping from a real recording and does **not** line up, so triggers will not fire if you use it here.

---

## 3. Channel Configuration

The `--channels` TOML maps each stream channel index to a label, a kind, and a `scale`. It is read once at launch. Exactly one channel must be `kind = "trigger"`, and the main window requires exactly 10 `finger` channels. Indices must be valid for the stream width, and the mapping is acquisition-specific — it changes whenever the set of active channels changes, so treat the bundled config as a worked example rather than a universal default.

- **Channel kinds:** `finger` (force, exactly 10), `emg` (muscle activity, optional), `trigger` (the AUX channel that fires capture events; exactly one).
- **`scale` field:** converts raw int16 counts to physical units. The full-scale int16 range maps to ±`scale`, i.e. `physical = raw / 32768 × scale`. The unit is whatever the recording uses — `scale` is just a multiplier (see §7.1). Defaults to `1.0` if omitted.
- **Edit the TOML when:** the active channels change (e.g. OT BioLab+'s channel selection in rebroadcast mode) or sensors are rewired.
- **Swapping configs without restarting:** not supported. The channel mapping is read once from `--channels` at launch; changing it requires relaunching DextView. (Calibration, by contrast, can be saved and loaded at runtime via the **Cal ▾** menu — see §4.4.)

---

## 4. Calibration

**Order matters: Rest → MVC → Zero (if needed).** Recalibrate at the start of every session and after any change to sensor placement.

### 4.1 Rest Calibration
*Establishes the baseline force for each finger at rest. Use the **Cal ▾ → Calibrate Rest** menu. The participant should be relaxed; DextView averages over the capture window.*

### 4.2 MVC Calibration
*Records the peak force per finger during a maximum voluntary contraction. Unlocks the **% MVC** toggle on the main plot.*

### 4.3 Zero Calibration
*Captures a true unloaded reference (e.g., sensors removed or detached). Used when baseline drift between sessions matters.*

### 4.4 Saving and Loading
*Save calibrations to a `.npz` file via the Cal menu. Load at the start of a session if reusing the same participant/setup.*

---

## 5. Running a Session

### 5.1 Live Monitors (`Live ▾`)

Open these *before* starting captures so you can confirm the signal looks right.

- **Trigger Channel Monitor** — confirms the trigger channel is wired correctly. Shows the adaptive threshold tracking the baseline.
- **Force Live Monitor** — rolling 10-second force traces; check sensors are responsive.
- **EMG Live Monitor** — rolling 10-second EMG traces. Toggle the bandpass (10–500 Hz) and 50/100/150 Hz powerline notch filters if you see line noise.

### 5.2 Capturing Trigger Events

*When the trigger channel crosses threshold, DextView automatically captures a fixed-length window.*

- **Window length and pre-trigger offset** are set on the command line (`--window-seconds`, `--window-offset`); run `dextview --help` for these and the other flags.
- The main visualizer plots all 10 finger profiles with P2P readouts and auto-detected onset markers.

### 5.3 Onset Markers

*Auto-detected dashed lines marking force onset per finger.*

- Drag a marker to override the auto-detection.
- Right-click a marker to reset it to the auto-detected position.

### 5.4 Browsing Capture History

*Use **< Prev** / **Next >** or the Left/Right arrow keys to navigate captures from the current session.*

---

## 6. Closed-Loop Feedback (Hooks)

*Hooks send a 5 ms TTL pulse on a LabJack T4 (pin FIO4) when a force condition is met — used to trigger external equipment (TMS, stimulators, recorders).*

**Requirements:** LabJack T4 connected via USB before launching DextView. Calibration (at minimum Rest + MVC) must be complete.

### 6.1 Any Finger Threshold
*Arms on force onset; fires when any finger crosses the % MVC threshold; re-arms when forces drop below the release threshold. HUD shows the running maximum.*

### 6.2 Hold In Target
*Tracks time spent inside a target % MVC band (e.g., 30% ± 20%). Fires once dwell time is reached and repeats periodically while held.*

---

## 7. Logging Captures

When `--log-dir` is set, DextView writes every captured trigger event to JSON at `<log-dir>/session_<timestamp>/event_NNNNN.json`. Pass `--log-dir` for real sessions.

Each event JSON contains:
- Trigger timestamp and sample index.
- Device configuration and channel metadata (labels, scales, kinds).
- Baseline, MVC, and zero calibration arrays at the time of capture.
- Full timestamp and signal arrays for the captured window.

### 7.1 Physical Unit Scaling
Logged signal arrays contain 16-bit signed integers. Convert to physical units with:

$$
\text{Signal}_{\text{physical}} = \frac{\text{Raw}_{\text{int16}}}{32768} \times \text{scale}
$$

where `scale` is the channel-specific conversion factor from the `--channels` TOML.

### 7.2 MVC Normalization
Once rest and MVC calibrations are complete, normalized force is:

$$
\text{Force}_{(\%\text{ MVC})} = \frac{\text{Force}_{\text{physical}} - \text{Baseline}_{\text{physical}}}{\text{Peak}_{\text{physical}} - \text{Baseline}_{\text{physical}}} \times 100
$$

Plot readouts and threshold hooks use this normalized value.

---

## 8. Troubleshooting

Common issues and where to look first:

- **DextView won't connect** — wrong mode, wrong host/port, OT BioLab+ not started yet, firewall.
- **No captures firing** — trigger channel wrong in TOML, threshold too high, no signal on AUX. With the simulator, use `configs/channels_simulator.toml` (trigger on index 10 — see §2.4).
- **Force values look wrong / clipped** — channel ordering off in TOML (especially after changing OT BioLab+ config), wrong `scale`, wrong sensor wired to wrong input.
- **% MVC toggle is greyed out** — MVC calibration not yet completed this session.
- **Hooks not firing the TTL** — LabJack not detected (connect before launch), or threshold conditions never met.
- **`auto` sample-rate/n-channels fails** — only supported in rebroadcast mode. For direct, supply explicit values; for proxy, both are read from the wire and these flags are unused.

---

## 9. Glossary

- **MVC** — Maximum Voluntary Contraction. The peak force a participant can produce.
- **% MVC** — force expressed as a percentage of MVC, used for thresholds and hooks.
- **P2P** — Peak-to-peak; max minus min within the capture window.
- **Baseline** — the resting force level subtracted before normalization.
- **Trigger** — an analog event (AUX channel crossing threshold) that initiates a capture.
- **AUX / Accessory channels** — the last channels in the device stream; AUX (16) come before accessory (8) in direct/proxy mode.
- **Hook** — a closed-loop rule that emits a TTL pulse when a force condition is met.

---

## 10. CLI Reference

Run `dextview --help` for the full list of flags, types, and defaults. Which flags matter for each connection mode is covered in [§2 Choosing a Connection Mode](#2-choosing-a-connection-mode).
