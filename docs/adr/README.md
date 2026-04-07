# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for cross-cutting
decisions that shape how the drone operations platform evolves.

## Index

- `ADR-001`: Canonical live-ops runtime architecture
- `ADR-002`: Canonical runtime envelope schemas

## Usage

- Add a new ADR when changing a boundary that affects multiple backend or
  frontend modules.
- Prefer one ADR per decision, not one ADR per implementation step.
- When a decision is superseded, keep the old ADR and mark the newer one as the
  replacement.
