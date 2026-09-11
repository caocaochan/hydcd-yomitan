# HYDCD → Yomitan

Private converter for the 漢語大詞典 七訂 source dictionary, including normalized
pinyin readings for matching and tone coloring in Yomitan/Lapis.

## Automatic builds

Every push to any branch runs the **Build dictionary** GitHub Actions workflow.
It tests the converter, downloads the fixed source inputs from this private
repository's `source-qiding-2025.12.13` release, verifies their SHA-256 checksums,
builds the dictionary, and runs archive-wide validation. The workflow can also
be started manually from the Actions tab.

Download `hydcd-yomitan-<commit SHA>` from the successful run's **Artifacts**
section. It contains `hydcd-qiding-yomitan.zip` for Yomitan, conversion and
validation reports, the source commit, and a checksum file. Artifacts are kept
for seven days; rerun a workflow to rebuild an older commit. A push containing
multiple commits builds the pushed branch tip.

CI uses `--archive-only` validation: all banks are checked for safety, resource
references, language structure, and normalized pinyin; the index schema is also
validated. Recursive term-schema validation is explicitly skipped. Tests still
exercise term-schema validation on small fixtures. Validation failures or
timeouts fail the build and prevent dictionary artifact publication.

The workflow uses Python 3.12 on Ubuntu 24.04, pinned GitHub Actions, and the
existing Python dependency lock file. It needs only the built-in `GITHUB_TOKEN`
with `contents: read`; no personal access token or repository secrets are needed.

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

The MDX, MDD, and source CSS are private release assets rather than Git blobs.
Their names, sizes, and checksums are recorded in
[the source manifest](.github/source-inputs.json). The release is fixed to one
source edition; replacing inputs requires a new release and manifest update.

Source dictionaries, generated ZIPs, local environments, and reference checkouts
are excluded from Git. Keep this repository private; the converter does not
grant redistribution rights to the dictionary data.
