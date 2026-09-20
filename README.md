# tlf-profilers

Monorepo for three civic-data profiler packages built on top of TLF (The Living Fact)'s
existing field registry and geo-resolution work.

| Package | Status | Purpose |
|---|---|---|
| [`tlf-geo-profiler`](packages/tlf-geo-profiler) | In progress | coordinate -> admin unit + demographic profile |
| `tlf-disaster-profiler` | Planned | CAP alert area -> exposure profile (population, roads, buildings, facilities) |
| `tlf-db-profiler` | Planned | unfamiliar civic dataset -> schema/quality report + tlf-core registry mapping |

Each package is independently installable; they share this repo because `tlf-disaster-profiler`
depends directly on `tlf-geo-profiler`'s output, and `tlf-db-profiler` is expected to feed back
into the same field registry both other profilers rely on.

See each package's own README for details.
