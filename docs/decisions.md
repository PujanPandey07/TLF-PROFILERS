# Design log

Running record of decisions and open questions across all 3 profilers.
Add an entry whenever a real decision gets made in discussion - keeps
context from getting lost between sessions.

## tlf-geo-profiler

- **Monorepo, not 3 separate repos** (2026-09-20): profilers share
  dependencies and Profiler 2 consumes Profiler 1 directly; splitting
  now would mean version-pinning overhead on code that isn't stable yet.
- **Boundary source**: OSM Nepal is the working candidate. Province/
  district/local-level (admin_level 4/6/7) look reasonably complete;
  ward-level (admin_level 9/10) coverage is unconfirmed and likely
  patchy outside major cities - needs an Overpass check before committing.
- **Postal codes**: not in OSM as polygon data. Nepal Post publishes a
  flat district-level code list - join by district, not by point-in-polygon.
- **Open**: how much demographic depth to return by default (population
  count only vs. full CBS breakdown via tlf-core's existing vocabulary).

## tlf-disaster-profiler

- Input is a CAP (Common Alerting Protocol) message: area as `polygon`,
  `circle`, or `geocode`, plus `category`/`event`/`urgency`/`severity`/
  `certainty` metadata (all standard CAP fields, filled in by the issuing
  authority - e.g. DHM for hydromet hazards).
- Nepal's DHM ran a national CAP training with WMO (Apr 2025) and has a
  draft national implementation plan - CAP is a real direction, not
  hypothetical, but likely no live production feed yet. Early dev will
  need sample/hand-built CAP test messages.
- Depends on tlf-geo-profiler for the population-count part of the
  exposure profile; adds roads/buildings/facilities from OSM entity layers.

## tlf-db-profiler

- Working hypothesis (unconfirmed with senior): profiles an unfamiliar
  civic dataset's schema against tlf-core's field registry, flagging
  known-vs-unmapped fields.
- tlf-core's registry is currently CBS-census-shaped only - has ~nothing
  to match against BIPAD-style incident/damage data. Plan: (1) seed a
  disaster-domain vocabulary using the existing Youth Innovation Lab
  report's field-mapping tables (DesInventar/BIPAD/Nepal Police), and
  (2) treat "unmapped field" as a useful output on its own, not a failure.
- LLM fallback for fields the registry can't match: registry match first
  (deterministic), LLM only for genuine unknowns, suggestions stored with
  a confidence score and require human confirmation before being accepted
  into the registry - never auto-accepted, to avoid silently corrupting
  civic data mappings.
