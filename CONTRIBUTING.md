# Contributing

## A channel failed for you

Open a [channel report](https://github.com/john-rocky/litertlm-release-gate/issues/new?template=channel-report.yml):
which channel, the command, the output. The row is re-run against the pinned generation and the
result lands in `results/`; a confirmed failure is filed upstream and linked back. Check the
current table under [`results/`](results/) first: your failure may already be a row with an
issue number.

## Pull requests

- **A new check in an existing runner.** One check id, one verdict, one line of evidence. A FAIL
  says what a user would see; a SKIP is "not measured", never a pass.
- **A host the gate does not run on.** The npm, GitHub-asset, PyPI and quickstart rows have no
  macOS dependency in principle. A PR that makes `run_channels.sh --only npm,gh_assets,quickstart`
  run on Linux, skipping the SwiftPM and device legs cleanly, is welcome.
- **A new channel.** A runner that installs what a user gets today, runs something real, writes
  one JSON per check into `--out`, and adds a row to the README's channel table.

Issues labeled [good first issue](https://github.com/john-rocky/litertlm-release-gate/labels/good%20first%20issue)
are scoped for a first PR.

Rules:

- **Content checks, not existence checks.** Unpack the tarball, diff the checksum, decode a token.
  "The URL returned 200" is not a check.
- **Pinned canaries.** The model is never the variable; use the ones in `pins.env`. Resolve what a
  user gets today and record it next to the pin; a mismatch is a finding, not a harness error.
- **Every FAIL maps to an upstream issue or is marked new.** Filing upstream is the maintainer's
  step; a PR that changes a verdict comes with the evidence line.
- **Stdlib Python and bash.** No new host dependencies beyond the README's requirements list.
- Apache-2.0. Issue numbers point at google-ai-edge/LiteRT-LM and google-ai-edge/LiteRT.
