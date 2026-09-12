# HYDCD → Yomitan

Converter for the 漢語大詞典 七訂 source dictionary, including normalized
pinyin readings for matching and tone coloring in Yomitan/Lapis.

## Download and updates

- [Latest full dictionary ZIP](https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/hydcd-qiding-yomitan.zip)
- [Latest Light dictionary ZIP](https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/hydcd-qiding-yomitan-light.zip)
- [Latest release](https://github.com/caocaochan/hydcd-yomitan/releases/latest)
- [Yomitan update index](https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/index.json)
- [Light update index](https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/index-light.json)

**汉语大词典 2025 Light** removes all images, their captions, and complete example blocks,
including their citations and notes. Definitions, readings, historical phonology,
explanatory notes outside examples, lookup aliases, and the full edition's CSS
are preserved. Quotations and source details within definitions remain.
Image/example-only senses display a short omission notice.
Each release includes measured download and uncompressed sizes in its notes and
`edition-comparison.json`.

Measured with converter 1.0.5 and the pinned source inputs (decimal MB):

| Edition | ZIP download | Uncompressed archive contents |
| --- | ---: | ---: |
| Full | 367.79 MB | 2,000.62 MB |
| Light | 50.75 MB | 723.31 MB |

Light reduces the ZIP size by **86.20%**. Both editions retain **936,906 term
rows**; release preparation checks every non-glossary row field and its
multiplicity, along with identical CSS and source input hashes.

The editions have separate names and update channels. To switch editions,
import the chosen ZIP; disable or remove the other edition if installed.

These links follow the latest published dictionary release. Each ZIP embeds
`isUpdatable`, `indexUrl`, and `downloadUrl`, and the release attaches the exact
`index.json` from that ZIP (`index-light.json` for the Light release asset).
In Yomitan's dictionary settings, check for updates
and apply the available update. An older installation without update metadata
must be replaced manually once with an update-enabled ZIP.

CI revisions use `2025.12.13.<workflow run number>.<attempt>` so Yomitan's numeric
revision comparison detects new builds and reruns even if the converter version
has not changed. The converter version and source commit remain in the reports.

## Automatic builds

Every push to any branch runs the **Build dictionary** GitHub Actions workflow.
It tests the converter, downloads the fixed source inputs from this
repository's `source-qiding-2025.12.13` release, verifies their SHA-256 checksums,
builds both editions, and runs archive-wide validation and lookup-row/CSS parity checks. The workflow can also
be started manually from the Actions tab.

Successful builds on `main` also publish a **GitHub Release** with
both dictionary ZIPs for Yomitan, separate conversion and validation reports, the
source commit, and a checksum file. Release titles use the full revision from
the dictionary's `index.json`, matching the version shown in Yomitan (for
example, `HYDCD Qiding build 2025.12.13.3.1`). Releases use the tag
`build-<run ID>-<attempt>` and point to the exact commit that was built. Manual
runs on `main` publish releases too; reruns create a new release without
overwriting an earlier build. Release assets do not have the seven-day
retention limit of Actions artifacts.

Every branch also uploads `hydcd-yomitan-<commit SHA>` to the successful run's
**Artifacts** section, retained for seven days. Other branches do not publish
releases. A push containing multiple commits builds the pushed branch tip.

CI uses `--archive-only` validation: all banks are checked for safety, resource
references, language structure, and normalized pinyin; the index schema is also
validated. Recursive term-schema validation is explicitly skipped. Tests still
exercise term-schema validation on small fixtures. Validation failures or
timeouts fail the build and prevent dictionary artifact and release publication.

The workflow uses Python 3.12 on Ubuntu 24.04, pinned GitHub Actions, and the
existing Python dependency lock file. It needs only the built-in `GITHUB_TOKEN`
with `contents: read` for the build and `contents: write` for the separate release
job; no personal access token or repository secrets are needed. The release job
downloads the validated build artifact and verifies the ZIP checksum before
publishing. Light validation additionally rejects packaged media and retained
image/example nodes. Both editions must have identical non-glossary lookup rows,
CSS, and revisions before release assets are prepared.

## Local build

From the repository root, with Python 3.12 and GitHub CLI authenticated:

```powershell
python .github/scripts/fetch_inputs.py
Set-Location work/hydcd-yomitan
python -m pip install -r requirements-lock.txt
python -m pytest
python -m hydcd_yomitan build --input ../input/hydcd-seven --output ../../outputs/hydcd-qiding-yomitan.zip
python -m hydcd_yomitan validate ../../outputs/hydcd-qiding-yomitan.zip --archive-only
python -m hydcd_yomitan build --input ../input/hydcd-seven --edition light --output ../../outputs/hydcd-qiding-yomitan-light.zip
python -m hydcd_yomitan validate ../../outputs/hydcd-qiding-yomitan-light.zip --edition light --archive-only
```

See [converter documentation](work/hydcd-yomitan/README.md) for conversion policy
and the optional targeted/exhaustive schema-validation modes.

## Source inputs

The MDX, MDD, and source CSS are release assets rather than Git blobs.
Their names, sizes, and checksums are recorded in
[the source manifest](.github/source-inputs.json). The release is fixed to one
source edition; replacing inputs requires a new release and manifest update.

Source dictionaries, generated ZIPs, local environments, and reference checkouts
are excluded from Git. The converter does not
grant redistribution rights to the dictionary data.
