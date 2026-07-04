# Contributing

Thanks for helping make PowerPi UPS Gateway useful and boring in the best way.

Public repository: `https://git.vns.ae/ahsan/pug`

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e .
pip install pytest
pytest
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install pytest
pytest
```

## Maintenance Rule

Every codebase update must also consider:

- `CHANGELOG.md`: add user-visible changes under `[Unreleased]`.
- `TODO.md`: add, remove, or update task status as needed.
- `pyproject.toml` and `src/pug/__init__.py`: increment the version for every codebase change.

If there is genuinely nothing to change in one of those files, say so in the pull request or commit message.

## Style

- Keep the SNMP core dependency-free unless there is a strong maintenance reason.
- Keep protocol frontends read-only unless a write/control feature has an explicit safety design.
- Keep Web UI administration actions conservative: updates must be fast-forward-only and must not overwrite local configuration.
- Prefer clear code over clever abstractions.
- Add focused tests for parser, codec, registry, and state behavior.
