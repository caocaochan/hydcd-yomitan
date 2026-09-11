# HYDCD → Yomitan

Converter for the 漢語大詞典 七訂 source dictionary, including normalized
pinyin readings for matching and tone coloring in Yomitan/Lapis.

## Download and updates

- [Latest dictionary ZIP](https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/hydcd-qiding-yomitan.zip)
- [Latest release](https://github.com/caocaochan/hydcd-yomitan/releases/latest)
- [Yomitan update index](https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/index.json)

These links follow the latest published dictionary release. Each ZIP embeds
`isUpdatable`, `indexUrl`, and `downloadUrl`, and the release attaches the exact
`index.json` from that ZIP. In Yomitan's dictionary settings, check for updates
and apply the available update. An older installation without update metadata
must be replaced manually once with an update-enabled ZIP.

CI revisions use `2025.12.13.<workflow run number>.<attempt>` so Yomitan's numeric
revision comparison detects new builds and reruns even if the converter version
has not changed. The converter version and source commit remain in the reports.

## Automatic builds

Every push to any branch runs the **Build dictionary** GitHub Actions workflow.
It tests the converter, downloads the fixed source inputs from this
repository's `source-qiding-2025.12.13` release, verifies their SHA-256 checksums,
builds the dictionary, and runs archive-wide validation. The workflow can also
be started manually from the Actions tab.

Successful builds on `main` also publish a **GitHub Release** with
`hydcd-qiding-yomitan.zip` for Yomitan, conversion and validation reports, the
source commit, and a checksum file. Releases use the tag
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
publishing.

## Local build

From the repository root, with Python 3.12 and GitHub CLI authenticated:

```powershell
python .github/scripts/fetch_inputs.py
Set-Location work/hydcd-yomitan
python -m pip install -r requirements-lock.txt
python -m pytest
python -m hydcd_yomitan build --input ../input/hydcd-seven --output ../../outputs/hydcd-qiding-yomitan.zip
python -m hydcd_yomitan validate ../../outputs/hydcd-qiding-yomitan.zip --archive-only
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
