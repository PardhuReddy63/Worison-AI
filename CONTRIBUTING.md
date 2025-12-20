# Contributing to ai-learning-assistant

Thanks for your interest in improving the project! The guidelines below help keep contributions consistent and reviewable.

## How to contribute

1. Fork the repository and create a feature branch from `main`:

```bash
git checkout -b feat/your-short-description
```

2. Run tests (if present) and lint before opening a PR.

3. Open a Pull Request with a clear description of the change and include:
   - What you changed and why
   - Any migration or manual steps needed
   - How to test the change locally

## Coding conventions

- Keep functions small and single-purpose.
- Use clear and concise docstrings for modules and public functions.
- Add unit tests for bug fixes and significant features.
- Follow the project's stylistic conventions (use `ruff` or `flake8` as desired).

## Commit messages

- Use present tense and short, descriptive messages (e.g. `Add PDF OCR fallback`).
- Group related changes into a single commit where reasonable.

## Local development tips

- Use a virtualenv to isolate dependencies.
- When adding dependencies, add them to `backend/requirements.txt` and describe their use in the PR.

Thank you — contributions are welcome! 🎉