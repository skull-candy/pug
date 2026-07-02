# Contributing

Thanks for helping make PowerPi UPS Gateway useful and boring in the best way.

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

If there is genuinely nothing to change in one of those files, say so in the pull request or commit message.

## Style

- Keep the SNMP core dependency-free unless there is a strong maintenance reason.
- Keep protocol frontends read-only unless a write/control feature has an explicit safety design.
- Prefer clear code over clever abstractions.
- Add focused tests for parser, codec, registry, and state behavior.
