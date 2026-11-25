# P2E Research Group Public Website

This repository hosts the public website of the P2E Research Group at the Korea Research Institute of Chemical Technology (KRICT).

P2E studies Plant BOP & Energy Systems Engineering: connecting core chemical and energy technologies with BOP, utilities, plant integration, operating constraints and engineering decisions.

Public site: <https://p2e-research-group.github.io/>

The public pages are in English, including on first load with JavaScript disabled.
The last bilingual public version is preserved at commit
[`7f2983d8`](https://github.com/p2e-research-group/p2e-research-group.github.io/tree/7f2983d8d4efb561fdd3bc5e3e0bd43fe4b6e552).
It is a historical source snapshot; there is no archive route in the public navigation.
The separate reference site retains its own language and indexing settings.

The plant panoramas and research equipment imagery illustrate the group's work;
they do not document a specific KRICT installation.

## Validation

```bash
python tools/validate_public_site.py
node --check assets/site.js
node --check assets/slide.js
python -B -m unittest discover -s tools/tests
```

## Shared public record checks

The read-only comparison runs weekly and on manual dispatch. It compares public patent records, publication titles/order, and the PI's current center names with the detailed reference site. PR checks use offline tests and extraction only.

See [operation and recovery instructions](docs/SHARED_RECORD_CHECK.md) for results, reruns, status meanings, and schedule limitations.
