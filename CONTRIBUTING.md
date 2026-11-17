# Contributing to harmony-device-db

Thank you for helping keep Harmony hardware working. This repository is part of
[Harmony Revival](https://github.com/aleksgain/harmony-org), an open-source replacement
for Logitech's MyHarmony software and cloud.

## The most useful thing you can do right now

**Capture your hub talking to Logitech's cloud while it is still online.**
The config-sync service (`svcs.myharmony.com/Discovery/Discovery.svc`) is not
documented anywhere, and once Logitech turns it off, the traffic can never be
recorded again. Follow the
[hub capture template](https://github.com/aleksgain/harmony-device-db/issues/new?template=hub-capture.md).
Read its redaction section before posting anything: captures contain account
tokens.

## Ground rules

- Be decent. See the [Code of Conduct](https://github.com/aleksgain/harmony-org/blob/main/.github/CODE_OF_CONDUCT.md).
- Security problems go to the [security policy](https://github.com/aleksgain/harmony-org/blob/main/.github/SECURITY.md), not to public issues.
- Do not contribute Logitech code, binaries, private keys or certificates, or
  anything copied from decompiled Logitech software. Describe protocols in your
  own words and with your own captures.
- By contributing, you agree that your contribution is licensed under the
  [Apache License 2.0](LICENSE).

## Workflow

1. Open an issue first for anything bigger than a small fix.
2. Fork, branch from `main`, and open the PR against `main`. CI must pass.
3. Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
   messages, for example `fix(verify): accept empty input lists`.

Releases here are not driven by commit messages. They follow the pinned upstream
snapshot: see "Versioning" in [README.md](README.md).

## Development

This repository holds no device data of its own. Fix data problems
[upstream](https://github.com/pickysysadmin/logitech-harmony-ir-archive). Changes
here are to the sync and verification scripts and workflows.

```sh
shellcheck scripts/*.sh
python3 scripts/verify.py              # committed metadata
scripts/sync-archive.sh fetch          # full pinned tree into api/v1/
python3 scripts/verify.py --full
```

See [README.md](README.md) for how syncing and releases work.

