# Day-0 required-source coverage policy v0.1

## Decision

Day-0 uses the frozen denominator of 29 equally weighted required Sources. A Source enters the acquisition numerator only when its C-6 disposition is `ACCEPTED_IMPLEMENTED` and the selected PIT evidence is `FULL_SOURCE`, `SUCCEEDED`, `HEALTHY`, complete, and fresh.

Authorization requires both:

- a coverage ratio of at least 0.80, which requires at least 24 of 29 discrete Sources;
- structural minima of 1/1 federal and 4/6 city Sources.

The canton consequence is derived, not a separate threshold: if 24 total Sources and the federal Source pass, at most six can be cities, so at least 17/22 cantons must be covered. `23/29 = 79.31%` fails; `24/29 = 82.76%` passes.

All 29 must also have a final governed disposition. `ACCEPTED_BLOCKED` remains in the denominator, never enters the numerator, and is presented as `NOT_COVERED`, never as zero demand. Vacancy counts are not weights.

Policy version: `day0-coverage-v0.1`.

## Rationale and alternatives

The rule was frozen before current-state evaluation. Eighty percent is an explicit normative launch-governance threshold, not a statistically estimated market-completeness parameter. Scientific integrity comes from pre-declaration, versioning, equal Source weighting, transparent missingness, no imputation, explicit scope, and sensitivity to future policy versions. The city floor prevents concentrated city loss; federal coverage is indivisible and therefore requires 1/1.

- 100% was rejected as an operational veto by any one scientifically governed blocker.
- 90% (27/29) was rejected because two blocked Sources would veto the product without a separately governed structural reason.
- A bare two-thirds threshold was rejected because it permits excessive missingness and concentration.
- The current-contract ceiling of 20/29 was considered evidence, not a threshold. The selected 24/29 rule is higher than that ceiling and therefore cannot have been selected to make the current state pass.

## Failure conditions and limitations

Authorization fails below either the numeric or structural minimum, when disposition is not 29/29, or when another closed authorization gate fails. The policy does not impute, extrapolate, remove blocked Sources, or claim a national census. Any authorized number means only observed active `GREEN_CONFIRMED` vacancies in the explicitly covered required-source universe at the cutoff.
