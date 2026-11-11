# FMR measurement model and conventions

How the acquisition app relates instrument values to fields, and what physics
it assumes. Every formula here is implemented in `src/app/calibration.py` and
reaches the page only through the API.

## Field from Aux Out (Kepco supply)

`H_nominal = s · V_aux · k`, where:

- `k` is the field per volt: about 996.3 Oe/V with one Kepco supply, about
  1984.4 Oe/V with two;
- `s = −1` when the output is inverted, as in the VI, and `+1` otherwise.

This nominal field sets the sweep and the safety checks. The recorded field
is always the gaussmeter's.

## Measured field (Lake Shore 425)

`H = scale · reading + offset`, with defaults `scale = 1.544` and
`offset = −11.956 Oe`, taken from the VI panel ("calibrated 08/20/2026").

This form is inferred from the panel labels; confirm it against the VI
diagram (TASKS.md, Q5). The LabVIEW warning still applies: if the start
field and H begin disagree, the conversion factors need recalibrating.

## Modulation field

`Hmod,rms = A_sine · m`, where:

- `A_sine` is the SR830 sine output in V rms (0.004–5 V, in 2 mV steps).
  0.004 V is the minimum the lock-in allows, and the app uses it as
  "modulation off".
- `m` is the coil constant through the amplifier: 5.219 Oe/V at 700 Hz. It
  depends on frequency, so recalibrate it if the reference frequency changes.

The user sets `Hmod,rms` (default 2.0 Oe rms). The backend sends
`A_sine = Hmod,rms / m`, rounded to 2 mV. For example, 2.0 Oe rms gives
0.384 V, which is 2.004 Oe rms. The preview and the file name report the
field that the rounded amplitude gives. A field outside `0.004·m` to `5·m`
(0.02–26 Oe rms at 5.219 Oe/V) is rejected.

With field modulation, the lock-in X signal is approximately the field
derivative of the absorption. That only holds while `Hmod` is small compared
with the linewidth. A common rule is `Hmod,pp` below about a third of
`ΔHpp`, where `Hmod,pp = 2√2 · Hmod,rms`; larger modulation broadens and
distorts the line.

## Resonance-field estimate (centres each sweep)

The estimate uses CGS units: `γ = g μB / h` in MHz/Oe (2.799 for the
default `g = 2`), `f` in MHz, and `4πMeff` in G from `Meff` in emu/cc:

- in plane: Eq. (2) of Appl. Phys. Lett. 127, 032406 (2025),
  `f = γ √((H + H4∥)(H + H4∥ + 4πMeff))`, with the in-plane fourfold
  anisotropy `H4∥ = 0` (it is very small in our films). So
  `H = −2πMeff + √((2πMeff)² + (f/γ)²)`. Check: `g = 2.02`,
  `μ0Meff = 20 mT` and 13 GHz give the paper's 451 mT.
- saturated out of plane: `f = γ (H − 4πMeff)`, so `H = f/γ + 4πMeff`. If
  that is not positive, the frequency has no sweep and the run is refused.

## Sweep placement

The user sets a field range `R` and a field step. For each frequency the
backend computes `Hres` from the estimate above and sweeps from
`Hres + R/2` down to `Hres − R/2`. For example, `R = 1000 Oe` and
`Hres = 1500 Oe` give a sweep from 2000 Oe to 1000 Oe. The endpoints are
converted to Aux Out voltages with the magnet calibration and rounded to the
SR830's 1 mV resolution, as is the step. The supply is bipolar, so the sweep
may cross zero; the safety limits apply to the magnitude of every endpoint.

The estimate only places the sweep. It is not a fit; resonance fields,
linewidths and damping are extracted afterwards by the FMR analysis app from
the saved files.

## Simulated instruments

The simulated lock-in returns
`X = A · Hmod,rms · (−2u / (1 + u²)²) + noise`, with `u = (|H| − Hres)/Γ`.

`Hres` comes from the in-plane estimate above, with `g = 2`,
`Meff = 140 emu/cc` and `Γ = 15 Oe` HWHM. The signal is zero when RF or
modulation is off.

The simulated gaussmeter returns the reading that the calibration maps back
to the true field. The simulation exists only so the engine, the API and the
page can be tested without hardware; it is not a model of the real sample.
