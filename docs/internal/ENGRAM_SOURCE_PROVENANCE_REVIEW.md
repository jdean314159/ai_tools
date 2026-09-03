# Engram source-provenance review

**Date:** 2026-08-14  
**Status:** Complete for sources identifiable from the repository and public
search; exact Medium-article comparison remains unavailable  
**Scope:** Current tracked source under `engram/`, its Git history, the archived
`jdean314159/engram` repository, and named research sources. This is an
engineering provenance review, not legal advice.

## Question

Does current Engram contain indications that code came from another source,
particularly from Medium articles used as conceptual input?

## Conclusion

No evidence of third-party source-code copying was found in the material that
could be identified and compared.

There is clear, near-verbatim code lineage from the current optional neural
subsystem to the earlier `jdean314159/engram` repository. That is an internal
predecessor relationship, not an unidentified external source: the repository
owner has already confirmed ownership and relicensing authority for that
predecessor in `OWNERSHIP_PROVENANCE_AUDIT.md`.

The public research sources explain concepts and mathematics used by the code:

- Jeffrey S. Dean's 1994 AFIT thesis supplies the subgrouped-RTRL lineage;
- the TITANS and Miras papers supply test-time-memory, surprise, associative
  memory, and retention concepts;
- older RTRL/subgrouping literature supplies underlying algorithms.

Those conceptual relationships do not by themselves imply copied program
expression. Exact searches for distinctive class names and prose from the
neural implementation did not locate a separate public implementation. This is
supporting evidence only, not proof that no match exists anywhere.

The exact Medium articles Claude reviewed cannot be checked because no Medium
URLs, article titles, saved article bodies, or source manifest were found in
`ai_tools` or the adjacent `llm-failure-lab` repository. Supplying that list
would permit a source-by-source comparison and is the only material gap in the
requested review.

## Evidence

### 1. Current lightweight Engram history

The current non-neural Engram surface descends through the repository's own
`engram_lite` implementation and its later rename/replacement of the frozen
heavy Engram. Its current files have ordinary multi-commit history under the
same owner identity documented by the broader ownership audit. No current
Engram file contains a Medium URL, third-party copyright header, `adapted from`
marker naming an external codebase, or vendored-source notice.

This history establishes repository lineage, not authorship by itself. The
owner declarations in the broader audit supply the ownership evidence Git
cannot.

### 2. Recovered neural subsystem

All four current neural implementation files first entered `ai_tools` in
recovery commit `58e07a042e5030c78a57f4b3fa1b59bcc315e07e`. Comparison with
the archived repository at commit
`5696ce49752d895a703d68203951f6c8c12c61d3` shows direct lineage:

| Current file | Archived predecessor | Comparison |
|---|---|---|
| `engram/src/engram/neural/core.py` | `engram/rtrl/core.py` | Essentially the same recovered file; current diff is 5 added and 4 removed lines |
| `engram/src/engram/neural/neural_memory.py` | `engram/rtrl/neural_memory.py` | Direct predecessor with subsequent integration changes; 119 additions and 18 removals |
| `engram/src/engram/neural/surprise_filter.py` | `engram/filters/surprise_filter.py` | Direct predecessor with subsequent integration changes; 66 additions and 81 removals |
| `engram/src/engram/neural/coordinator.py` | archived neural/memory integration | Recovered subsystem integration, later adapted to the current extension seam |

The archived repository also contains `engram_article.docx`, titled “Building
a Five-Layer Memory Runtime for Local LLMs” and attributed in its text to
Jeffrey Dean. It describes the implementation in the first person and relates
the RTRL component to the author's 1994 thesis. The document contains no
external hyperlink relationships and supplied no Medium-source list.

The archived commit's placeholder Git author (`Your Name <you@example.com>`)
is not useful ownership evidence. The owner declaration and the public
repository relationship are therefore important parts of the provenance
record.

### 3. Research influence versus implementation copying

`neural/core.py` labels itself an implementation of Dean (1994) subgrouped
RTRL, modernized with common optimizer, gating, and normalization techniques.
The AFIT repository confirms the thesis's author, date, subject, and
subgrouped-RTRL results. Public searches for the distinctive identifiers
`ModernSubgroupedRTRL` and `TITANSMemory`, and for distinctive module prose,
did not find another source-code origin.

`neural/surprise_filter.py` cites two papers:

- **Titans: Learning to Memorize at Test Time**, arXiv:2501.00663, presents a
  neural long-term-memory module and a family of architectures combining it
  with attention.
- **It's All Connected: A Journey Through Test-Time Memorization, Attentional
  Bias, Retention, and Online Optimization**, arXiv:2504.13173, presents the
  Miras design framework in terms of associative memory, attentional-bias
  objectives, retention gates, and memory-learning algorithms.

These are appropriate conceptual citations. The current implementation is an
Engram-specific RTRL approximation/interface, not a claim to reproduce either
paper's full architecture. Repository evaluation documents now make that
distinction explicitly and keep the subsystem default-off and output-isolated.

### 4. Indicators that deserve correction or better attribution

The review found evidence-quality issues, but none is evidence of copied code:

1. `neural/surprise_filter.py` states “Reduces memory storage by 70-90%” and
   repeats “70-90% memory reduction” as a feature. No local experiment or
   pinpoint paper citation found in this review establishes that range for
   Engram. It should be removed, qualified as a target/hypothesis, or backed by
   a reproducible Engram result.
2. “Based on Google Research TITANS papers” is too broad for a module that uses
   token perplexity and percentile thresholds as its concrete gate. “Inspired
   by” is more accurate unless a mapping from paper equations to implementation
   is documented.
3. The code cites arXiv URLs but not paper titles/authors, and `core.py` names
   “Dean (1994)” without a durable bibliographic link. Adding a short source
   note would make conceptual provenance auditable without implying code was
   ported from the papers.
4. The archived heavy Engram contained a utility saying it was “based on 57
   articles of LLM best practices.” That utility is not part of the current
   `engram` package; related structured-output code now lives elsewhere in
   `ai_tools` and falls outside this focused review. The phrase is nevertheless
   a warning against treating article synthesis as a source manifest.

## Search and comparison limits

- Public exact-phrase search is not an exhaustive source-code similarity
  service and does not index every repository or historical version.
- No original Claude conversation or article bibliography was available.
- Ideas, algorithms, APIs, and program expression are different provenance
  questions. This review checked observable expression and lineage; it does
  not attempt to decide legal protectability of individual concepts.
- Dependency packages were not treated as copied source merely because Engram
  imports them.

## Recommended closure

1. Keep the existing owner declaration for the archived Engram and recovered
   neural implementation.
2. Correct the unsupported 70–90% statement and tighten the TITANS wording.
3. Add a compact `SOURCES.md` or equivalent bibliographic section for Engram's
   conceptual sources.
4. If the Medium article list can be recovered, append it to that source note
   and run a final exact-expression comparison against the article text and
   any code repositories the articles link.

## Primary/public references checked

- AFIT thesis record: <https://scholar.afit.edu/etd/6693/>
- TITANS paper: <https://arxiv.org/abs/2501.00663>
- Miras paper: <https://arxiv.org/abs/2504.13173>
- Archived owner repository: <https://github.com/jdean314159/engram>

