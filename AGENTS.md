# Agent instructions

## Project context

- This is a Python 3.11+ project. Keep application code under `app/` and tests under `tests/`.
- Preserve the fixture-first design. Reuse existing collectors, parsers, repositories, and test fixtures rather than duplicating behavior.
- Keep live Facebook, browser-login, and Telegram operations out of routine tests; use fixtures and mocked dependencies.

## Python and Java changes

- Follow the surrounding code style and existing type and error-handling patterns. Avoid new dependencies unless the change requires them.
- Add or update focused tests for behavior changes. For Python, use the existing `pytest` setup and fixtures.
- This repository has no Java module. In Java projects, inspect the existing Maven or Gradle wrapper and use that project's documented build and test commands; do not assume a build tool or install one.

## Debugging and verification

- Establish the failing behavior and root cause before changing code. Prefer the smallest relevant test, then run broader checks when needed.
- Report checks that could not run; do not imply that an untested live integration succeeded.

## Git and workspace safety

- Check `git status` and the relevant diff before editing. Preserve existing user changes and avoid unrelated files.
- Do not commit, push, or discard user changes unless explicitly requested.
- Keep credentials, cookies, browser profiles, and other private runtime data out of source control and logs.

