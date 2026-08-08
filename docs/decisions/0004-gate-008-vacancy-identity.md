# Decision 0004: GATE-008 Vacancy Identity

## Status

Accepted for GATE-008.

## Decision

GATE-008 implements deterministic `HARD_KEY` and `RULE_SCORE` deduplication under `dedup-v0.1`. No machine learning, LLM, embeddings, or external enrichment are used.

`Posting` remains the immutable source-native identity boundary. Vacancy identity is a derived, point-in-time, versioned graph. Every evaluated pair retains method, outcome, score, feature scores, frozen weights, barriers, selected observations, and review state. Review cases are not silently merged.

Reposts retain the same `Vacancy` and create a new `VacancyEpisode`. Advertised position count remains `NULL` unless explicit evidence supports a positive integer; generic plural language only records `multi_hire_possible`.

Future dedup versions may coexist and produce different identity graphs without rewriting `dedup-v0.1`. The frozen `docs/research/v0_4/` package remains authoritative, read-only, and unchanged.

## Point-in-time authority and operational projection

`DedupRunVacancyState` and `DedupRunPostingAssignment` are the authoritative identity state for historical and statistical point-in-time computation. They are immutable and scoped to one exact `DedupRun`.

`Vacancy`, `VacancyPostingMembership`, and `VacancyEpisode` are a mutable current operational projection. A projection watermark prevents an older `as_of` replay from rolling this graph backward. Future Daily Market State computation must select the appropriate run-scoped state, never today's mutable projection.