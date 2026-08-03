# AGENTS.md

## Engineering principles

- Implement the smallest complete solution that satisfies the current
  requirements and acceptance criteria. Do not design for hypothetical future
  requirements.

- Inspect the relevant code, tests, configuration, types, and dependency
  documentation before making changes. Follow established project conventions
  unless they are clearly defective or conflict with the task.

- Keep changes focused on the requested behavior. Do not perform unrelated
  refactoring, formatting, dependency upgrades, or cleanup.

- Prefer modifying or removing obsolete internal code over adding compatibility
  layers, duplicate paths, fallbacks, or permanent transitional abstractions.

- Preserve existing public contracts, persisted data, and externally consumed
  behavior unless the task explicitly requires a breaking change. When changing
  persisted schemas or formats, provide the necessary migration.

- Prefer capabilities already available in the project. Add a dependency only
  when it materially reduces implementation complexity or improves correctness,
  security, or maintainability.

- Before reimplementing library functionality, check the installed version's
  documentation, types, and existing project usage.

- Keep responsibilities separated, but do not introduce abstractions without a
  concrete reuse, isolation, or testing benefit.

- Build changes as working vertical slices. Keep the repository in a valid,
  testable state throughout the implementation.

- Avoid knowingly temporary, duplicated, or disposable implementations. A
  bounded incremental solution is acceptable when it is correct, tested, and
  does not create an architectural dead end.

## Validation

- Add or update tests for changed behavior when the repository has an applicable
  test structure.

- Run the most relevant tests, type checks, lint checks, and builds available for
  the affected code.

- Do not claim that the task is complete when validation failed or was not run.
  Report any unverified behavior and the reason it could not be verified.

## Decision priority

When principles conflict, prioritize:

1. Correctness and data safety
2. Explicit task requirements
3. Existing external contracts
4. Simplicity
5. Consistency with the current architecture
6. Extensibility for demonstrated, not hypothetical, needs