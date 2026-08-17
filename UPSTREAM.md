# Upstream snapshot

- Original project: https://github.com/ok-oldking/ok-wuthering-waves
- Branch: `master`
- Snapshot commit: `ca0be964bed6a7cd5553733452c0605a56312483`
- Imported: 2026-08-15
- License: GNU AGPL-3.0 (`LICENSE.txt`)

## Update policy

Upstream updates are imported as source snapshots without the upstream `.git` directory. Compare a new snapshot with the commit recorded above, resolve Wuwa Pilot changes on a temporary branch, run the test suite, and record the result as one commit named `sync upstream`.

Do not merge or rebase the upstream Git branch into this repository. That would reintroduce the upstream commit history that this clean rebuild intentionally excludes.
