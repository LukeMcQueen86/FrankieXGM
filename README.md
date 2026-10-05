# FrankieXGM

**VGM/VGZ → XGM 1.01/XGM2 converter for the Sega Mega Drive/Genesis**

FrankieXGM converts Sega Mega Drive VGM/VGZ music to either classic XGM 1.01 or XGM2,
including hybrid **YM2612 + SN76489 + SegaPCM** playback.

The name comes from the "Frankenstein" combination of Mega Drive FM/PSG audio
and SegaPCM assembled into one XGM soundtrack.

**FrankieXGM v1.1.0 by [Luke McQueen](https://linktr.ee/lukemcqueen_)**

**Based on XGMTool/XGM2Tool by Stephane Dallongeville, part of [SGDK](https://github.com/Stephane-D/SGDK).**

> FrankieXGM is an independent project and is not an official SGDK project.

## Features

- YM2612 FM conversion (channels 1..5)
- SN76489 PSG conversion
- SegaPCM → XGM PCM conversion (14 kHz resampling)
- VGM 1.51+ SegaPCM support
- Older YM2612/PSG-only VGM support where applicable
- NTSC / PAL timing
- Automatic PCM normalization (optional)
- Manual PCM gain in dB
- XGMTool-compatible delayed YM key-off behavior
- VGM header and command-stream validation
- GD3 metadata preservation
- Command-line conversion engine
- Standalone executable build (Win/Linux)
- Selectable XGM 1.01 or XGM2 output

## GUI

The GUI provides:

- VGM/VGZ input file selection
- XGM 1.01 or XGM2 output selection
- XGM output file selection
- NTSC (60 Hz) or PAL (50 Hz)
- PCM unchanged
- Automatic PCM normalization (optional)
- Manual PCM gain in dB
- Delayed YM key-off option
- Live conversion/optimization log
- Conversion summary and error dialogs
- About/Info window with project attribution

## Audio mapping

| Source | XGM |
|---|---|
| YM2612 | FM commands |
| SN76489 | PSG commands |
| SegaPCM channel 1 | XGM PCM 1 |
| SegaPCM channel 2 | XGM PCM 2 |
| SegaPCM channel 3 | XGM PCM 3 |
| SegaPCM channel 4 | XGM PCM 4 |

SegaPCM channels 5..16 are ignored.

XGM PCM uses the FM DAC path in place of YM2612 channel 6, as specified by the
XGM format/driver.

## PCM volume balancing

SegaPCM samples can optionally be balanced using a conservative mix-level
heuristic.

- **Unchanged** — preserves PCM data as-is.
- **Automatic normalization** — targets RMS ≈ −14.9 dBFS and applies a
  −3 dBFS peak ceiling.
- **Manual gain** — applies the specified gain in dB and applies the same
  −3 dBFS peak ceiling.

This is a heuristic mix-level adjustment rather than a full acoustic model of
YM2612/PSG loudness.

### Per-sample volume

FrankieXGM does **not** preserve or generate separate XGM PCM volume settings
for individual samples. Classic XGM 1.01 does not provide a per-sample volume
field in its PCM play command; the command specifies the PCM priority, channel,
and sample ID. To reproduce different static volume levels with the standard
XGM driver, FrankieXGM would have to generate separate PCM data variants of
the same sample (for example, one copy at 100%, another at 50%, and another at
25%). This can unnecessarily increase the converted XGM's PCM data size and
consume additional sample IDs, especially when combined with sample variants
already required for different playback rates.

For this reason, per-sample volume conversion is intentionally not implemented.
If different samples need different static levels, set their volume in the
source music before exporting the track to VGM, then convert that VGM with
FrankieXGM. Dynamic volume changes while a sample is already playing are also
not reproduced.

## XGM 1.01 and XGM2 output

FrankieXGM can now generate either classic **XGM 1.01** or **XGM2** files.

- **XGM 1.01** — up to 4 simultaneous PCM channels at 14 kHz.
- **XGM2** — up to 3 simultaneous PCM channels, with a user-selectable PCM
  playback rate of 13.3 kHz or 6.65 kHz. The selected rate is used for all
  XGM2 PCM samples; the backend no longer chooses the rate automatically.

For the command line, use `--xgm2-rate 13300` for 13.3 kHz or
`--xgm2-rate 6650` for 6.65 kHz. The default is 13.3 kHz. The graphical
interface provides the same two choices under **XGM2 PCM sampling rate**.

The XGM2 backend follows the XGM2 file layout and command encoding documented
by SGDK and the supplied `xgm2tool` implementation. It currently writes
unpacked XGM2 files.

Because XGM2 has only three PCM channels, FrankieXGM reports an error instead
of silently dropping audio if more than three PCM voices would need to play
simultaneously. When possible, inactive XGM2 PCM slots are reused for different
source SegaPCM channels.

XGM2 uses a two-level PCM priority field. FrankieXGM currently emits music PCM
with the low priority, leaving the higher priority available for SFX use by the
standard driver.

### Per-sample pitch control

FrankieXGM does not provide runtime per-sample pitch control. The XGM and XGM2
formats use fixed PCM playback rates, so when the same source sample is needed
at different playback rates, FrankieXGM creates separate PCM variants and
reuses them for matching pitch/rate requests. This can increase PCM data size
and the number of sample IDs, but is necessary to reproduce different sample
pitches while remaining compatible with the standard drivers.

## VGM validation

FrankieXGM validates the VGM before conversion.

- VGM signature is checked.
- VGM version is reported.
- Header offsets are validated.
- Command boundaries are validated.
- Data-block lengths are validated.
- The `0x66` end command is required.
- VGM 1.51 or newer is required when SegaPCM data is present.
- Older VGM files can still be processed when they are valid YM2612/PSG-only
  files.

## Command-line usage


```text
python FrankieXGM.py input.vgm output.xgm --ntsc
python FrankieXGM.py input.vgm output.xgm --pal
python FrankieXGM.py input.vgm output.xgm --pcm-normalize
python FrankieXGM.py input.vgm output.xgm --pcm-gain 3
python FrankieXGM.py input.vgm output.xgm --format xgm2 --ntsc
python FrankieXGM.py input.vgm output.xgm --format xgm2 --pal
python FrankieXGM.py input.vgm output.xgm --format xgm2 --xgm2-rate 13300
python FrankieXGM.py input.vgm output.xgm --format xgm2 --xgm2-rate 6650
```

## Windows executable

The repository includes `build_windows.bat`.

On Windows:

```text
py -m pip install pyinstaller
build_windows.bat
```

The standalone executable is created at:

```text
dist\FrankieXGM.exe
```

The resulting executable does not require Python to be installed on the target
machine.

## Credits

### FrankieXGM

**Luke McQueen**

[Linktree](https://linktr.ee/lukemcqueen_)

### XGMTool / SGDK

FrankieXGM is based on the work and XGMTool implementation by
**Stephane Dallongeville**, part of SGDK.

- [SGDK](https://github.com/Stephane-D/SGDK)
- [XGMTool source](https://github.com/Stephane-D/SGDK/tree/master/tools/xgmtool)
- [XGM specification](https://github.com/Stephane-D/SGDK/blob/master/bin/xgm.txt)
- [XGM2 specification](https://github.com/Stephane-D/SGDK/blob/master/bin/xgm2.txt)

See `THIRD-PARTY-NOTICES` for the applicable third-party attribution and
license information.

## License

FrankieXGM is released under the **MIT License**.

See [`LICENSE`](LICENSE) for the full license text.

Third-party SGDK/XGMTool attribution and license information is documented in
[`THIRD-PARTY-NOTICES`](THIRD-PARTY-NOTICES).

## Disclaimer

FrankieXGM is provided "as is", without warranty of any kind. See the LICENSE
file for the complete terms.

FrankieXGM is not affiliated with or endorsed by Sega.

## Linux executable

The repository includes `build_linux.sh` for building the GUI on Linux.

```text
chmod +x build_linux.sh
./build_linux.sh
```

The standalone executable is created at:

```text
dist/FrankieXGM_GUI
```

PyInstaller builds native executables for the platform on which it runs, so the
Linux executable should be built on Linux (or in a Linux environment such as
WSL).
