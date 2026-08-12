# ADR-002: Module application ports

Status: Accepted

## Context

Agriculture owns flights, telemetry, agronomic capability releases, and findings.
Video Analysis owns videos, inference jobs, detections, and evidence. Vision owns
projects, datasets, model artifacts, evaluation, and model lifecycle. Direct
cross-module ORM and repository imports made those ownership boundaries
unenforceable and allowed consumers to depend on persistence details.

## Decision

The application remains a modular monolith with synchronous typed ports:

- Agriculture exports telemetry DTOs from `agriculture.contracts` and a query
  function from `agriculture.ports`. Video and Vision may call that function,
  but may not import Agriculture ORM models or repositories.
- Vision exports model-release DTOs and a read port. Agriculture capability
  release code may consume that port, but may not import Vision ORM models.
- Agriculture may consume Video's existing DTO/application port. It may not
  import Video ORM models.
- Georeferencing algorithms may remain in Agriculture. Consumers pass DTOs to
  them and receive value objects; ORM instances never cross the boundary.
- Vision deployment may call the Agriculture capability-release service because
  deployment is the lifecycle event that activates the agronomic capability.

The executable module-port guard enforces these dependency rules.

## Alternatives

- Moving all contracts to a global shared package was rejected because the
  current contracts have clear owners and no independent shared lifecycle.
- Duplicating telemetry queries in each consumer was rejected because it leaks
  Agriculture persistence and creates divergent ordering/mapping behavior.
- Splitting modules into separately deployed services was rejected because no
  independent deployment or scaling requirement justifies the operational cost.

## Consequences

Cross-module calls add explicit DTO mapping and narrow read functions. Persistence
schema changes remain private to the owning module, and boundary violations fail
in local/CI guardrails. The ports are in-process and share the caller's database
transaction; converting them to remote APIs would require new failure semantics.

## Revisit conditions

Revisit contract placement if a third independent owner consumes the same
contracts, or replace in-process ports if modules gain independent deployment,
availability, or scaling requirements.
