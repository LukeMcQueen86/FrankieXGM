# FrankieXGM

**VGM/VGZ → XGM 1.01 converter for the Sega Mega Drive / Genesis**

FrankieXGM converts Sega Mega Drive VGM/VGZ music to XGM 1.01,
including hybrid **YM2612 + SN76489 + SegaPCM** support.

The name comes from the "Frankenstein" combination of Mega Drive FM/PSG audio
and SegaPCM assembled into one XGM file.

**FrankieXGM v1.0.0 by [Luke McQueen](https://linktr.ee/lukemcqueen_)**

**Based on XGMTool by Stephane Dallongeville, part of [SGDK](https://github.com/Stephane-D/SGDK).**

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

## GUI

The GUI provides:

- VGM/VGZ input file selection
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

## Per-sample pitch control

FrankieXGM does not preserve per-sample pitch changes as a runtime control. Classic XGM 1.01 does not provide a PCM command that changes the pitch of a sample while it is being played.

When the same source sample is used at different playback pitches, FrankieXGM creates separate PCM sample variants for the different pitch rates and reuses those variants whenever the same pitch is requested. This is necessary for compatibility with the standard XGM 1.01 driver, but it can increase the number of PCM samples and the amount of PCM data in the converted XGM.

As with per-sample volume, this is a deliberate trade-off: FrankieXGM prioritizes compatibility with the standard XGM driver rather than adding custom runtime controls that would require a modified driver or increase the complexity and size of the resulting track.

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
```

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
