# Release AISAD 1.1.0

- Status: active
- Source: maintainer request to publish a new release from main
- Last updated: 2026-09-07

## Goal
Publish stable v1.1.0 from main with verified portable assets.

## Relevant context
Main a07a58cdcd83778376745343e42facf9fef7adaa; prior release v1.0.7.
VERSION already equals 1.1.0. The tag workflow gates publication on tests.

## Constraints
Use synthetic fixtures only. Preserve existing local installations and reports.
No signing, credentials or network configuration changes.

## Done when
GitHub Latest is v1.1.0, release CI passes, and asset checksums match.

## Verification
python3 -m unittest discover -v
python3 scripts/build_release.py --tag v1.1.0
GitHub main CI: 34093126590, all six jobs passed.
Verify release tag ancestry, assets and SHA256SUMS after publication.

## Out of scope
New features, installing the release locally, modifying user data.

## Current status
Release metadata prepared; main CI passed all six jobs. Local unittest suite passed 77 tests. The v1.1.0 asset build passed.

## Next step
Push verified release metadata to main and tag v1.1.0; verify publication and assets.

## Open risks
Version 1.1.0 removes --watch and --stdin; disclose this in release notes.
