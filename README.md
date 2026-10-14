# P2E Research Group Public Website

This repository hosts the public website of the P2E Research Group at the Korea Research Institute of Chemical Technology (KRICT).

P2E studies Plant BOP & Energy Systems Engineering: connecting core chemical and energy technologies with BOP, utilities, plant integration, operating constraints and engineering decisions.

Public site: <https://p2e-research-group.github.io/>

## Validation

```bash
python tools/validate_public_site.py
node --check assets/site.js
```

## Shared public record checks

The read-only comparison runs weekly and on manual dispatch. It compares public patent records, publication titles/order, and the PI's current center names with the detailed reference site. PR checks use offline tests and extraction only.

See [operation and recovery instructions](docs/SHARED_RECORD_CHECK.md) for results, reruns, status meanings, and schedule limitations.
