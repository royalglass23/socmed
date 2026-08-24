# Social Media Automation - Competitor Validation

This context defines the business language for Phase 4 competitor validation for Royal Glass. It keeps the Royal Glass dataset distinct from a future Blue Haven workflow.

## Language

**Royal Glass Validator**:
The first Phase 4 validation product for the Royal Glass brand only. It does not include Blue Haven records or classification policy.
_Avoid_: shared validator, cross-brand validator

**Needs Validation Cohort**:
The existing Royal Glass candidate records whose current classification needs evidence-based validation. This is the complete input scope for the first validator run.
_Avoid_: all entities, confirmed cohort, adjacent cohort

**Input Workbook**:
The single authoritative Royal Glass `.xlsx` file supplied for one validation run. Its original values and provenance remain unchanged.
_Avoid_: working spreadsheet, editable source

**Competitor Entity**:
The real-world business being assessed as a Royal Glass competitor, which may be represented by more than one discovered or imported record.
_Avoid_: duplicate row, website record

**Source Record**:
An immutable imported or discovered record that contributed information about a Competitor Entity. It keeps its own provenance even when linked to an entity.
_Avoid_: canonical row, disposable duplicate

**Protected Human Override**:
An attributable reviewer decision that remains authoritative until a reviewer explicitly supersedes it. Automation may propose a conflicting result but cannot replace it.
_Avoid_: automatic correction, silent reclassification

**Evidence History**:
The retained record of factual support for a validation outcome, including compact evidence retained indefinitely and raw captures retained for a defined period.
_Avoid_: opaque score, transient crawl output

**New Zealand Competitor Universe**:
Businesses with credible evidence of relevant service delivery anywhere in New Zealand. A business headquartered overseas is included when it demonstrably delivers relevant work in New Zealand.
_Avoid_: Auckland-only competitor universe, headquarters-only coverage

**Market Priority**:
The relative importance of a New Zealand market to Royal Glass competitor monitoring, separate from whether a business is eligible for classification. Auckland is currently higher priority.
_Avoid_: eligibility rule, exclusion region

**Direct Competitor**:
A business with credible evidence of Tier 1 Royal Glass service delivery in New Zealand. Tags retain service and business-model nuance without changing the primary classification.
_Avoid_: broad category, untagged direct

**Review Required**:
A validation outcome used when evidence is insufficient, contradictory, or unavailable for a reliable classification. It is not a competitor classification.
_Avoid_: uncertain class, temporary irrelevant

**Fetch Failure**:
An unsuccessful attempt to retrieve a source page, such as a timeout, block, error response, or unavailable site. It is retained for retry and review and never proves irrelevance.
_Avoid_: negative evidence, irrelevant result

**High Confidence**:
A validation result supported by clear official evidence of the relevant service and New Zealand delivery, without a material conflict. It is eligible for automatic approval except when the result is Irrelevant.
_Avoid_: percentage score, implied certainty

**Medium Confidence**:
A validation result with relevant but incomplete evidence. It requires human review.
_Avoid_: auto-approved result, almost certain

**Low Confidence**:
A validation result with weak, conflicting, unavailable, or failed evidence. It requires human review.
_Avoid_: low-priority result, irrelevant result

**Gold Set**:
A small, manually approved set of representative validation cases used to verify the classifier before a full run. The user approves genuinely ambiguous cases.
_Avoid_: production dataset, assumed truth

**Reproducible Outcome**:
A validation result whose classification or review requirement can be traced to retained evidence and preserved input provenance.
_Avoid_: unsupported decision, opaque score
