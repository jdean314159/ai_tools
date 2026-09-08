# Provenance audit after the `ai_tools` history rewrites

**Date:** 2026-09-08
**Verifier:** Codex
**Authority:** checks and reports only, plus the Task E editorial repair
**Repositories checked:** `/home/cybernaif/repos/ai_tools` and
`/home/cybernaif/repos/llm-reliability-lab`

## Result

### Applied

- Independently reconstructed the three available `ai_tools` lineages and the
  named archive evidence without recording credential bytes.
- Audited the requested commit and archive-digest references in both
  repositories.
- Removed the orphaned word `Higher` from
  `QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-2026-09-07.md`. No figure or
  conclusion changed.

### Escalated findings

1. **`EP-NAV-LEDGER` provenance is degraded.** Its two recorded commit objects
   do not resolve in the current checkout or the configured cleaned remote.
   They remain available in both retained L1 repositories, and their trees and
   cited file bytes have exact L3 equivalents. The evidence is recoverable, but
   the packet's Git locators are dangling in the current lineage.
2. **One split SHA/archive-digest pair exists.** The handoff was initially
   correct: commit `d87fef1` paired `fe4ba341...` with an archive that embeds
   `fe4ba341...`. Commit `88d8731` first replaced that SHA with `7a4a273...`
   while retaining the digest; `21be7d8` later replaced it again with
   `49026eac...`. Both repair passes left the split in place. The retained
   archive cannot be regenerated from `49026eac...`, although the extracted
   files are identical.
3. **Anonymous public resolution was not observable.** The configured cleaned
   remote could be fetched and was checked independently in a fresh bare
   repository, but the same GitHub repository returned HTTP 404 to anonymous
   API and web requests. Tables therefore distinguish the configured cleaned
   remote from anonymous public availability.
4. **The provenance repair itself is no longer directly verifiable.** Its 47
   literal token pairs normalize to 43 distinct replacement commits, and none
   of the old L2 identities survives in the repositories or archives checked.
   Two independent content anchors support the rewrite, but they do not prove
   the other direct old-to-new mappings.

No packet status, ledger status, verification disposition, ADR, history, or
teaching content was changed.

## Scope and terminology

The current `ai_tools` checkout was at
`61a63fc1eb09c655cfee53aefb96b2045f1ca9bf`. A fresh bare fetch of its
configured origin was created at `/tmp/ai-tools-remote-audit-2026-09-08.git`;
that remote also advertised `main` at `61a63fc...`, `v0.1.0` at `f09211d...`,
and `v0.2.0` at `fb35204...`.

In this report:

- **local** means the current `ai_tools` checkout;
- **cleaned origin** means the independently fetched configured remote;
- **anonymous public** means unauthenticated access to the configured GitHub
  URL; it returned 404 at audit time;
- **L1 recovered** means `/home/cybernaif/repos/temp/ai_tools.tar.gz`, extracted
  at `/home/cybernaif/repos/temp/ai_tools`;
- **L1 08-29** means `/home/cybernaif/repos/temp/repos/ai_tools.tar.gz`,
  extracted at `/home/cybernaif/repos/temp/repos/ai_tools`.

## Task A — `EP-NAV-LEDGER` locator resolution

The packet contains two distinct commit identities across five locator fields
or statements. The verification document repeats both identities.

| Locator field | Recorded SHA | Local | Cleaned origin | Anonymous public | Tree | Disposition |
|---|---|---:|---:|---:|---|---|
| `derivation_method`, `EP-NAV-LEDGER.json:3` — policy parent | `dd8c7f203cb506b70f4d4abe2e85bee6101e9893` | no | no; direct fetch rejected | unobservable (404) | `bff5b3d98fcc56e761dfc002ca1bf2064ac296e8` | Resolves in both L1 repositories. Same tree exists at L3 `21925d2487f219f06a79364b972110bf177dca2d`. |
| `derivation_method`, `EP-NAV-LEDGER.json:3` — result commit | `abcc2f09ba5ee022d2066ed59ea09e01b2dd85be` | no | no; direct fetch rejected | unobservable (404) | `31a4a7cac4cade9209c4af3050638127835287e7` | Resolves in both L1 repositories. Same tree exists at L3 `4ec39323901bec772a2d6fe1934a58f9ce1f1c20`. |
| `sources.nav_policy.locator`, line 108 | `dd8c7f203cb506b70f4d4abe2e85bee6101e9893` | no | no | unobservable (404) | `bff5b3d98fcc56e761dfc002ca1bf2064ac296e8` | Cited file is byte-identical at L3 `21925d2`. |
| `sources.nav_result.locator`, line 117 | `abcc2f09ba5ee022d2066ed59ea09e01b2dd85be` | no | no | unobservable (404) | `31a4a7cac4cade9209c4af3050638127835287e7` | Cited file is byte-identical at L3 `4ec3932`. |
| `sources.nav_validation.locator`, line 126 | `abcc2f09ba5ee022d2066ed59ea09e01b2dd85be` | no | no | unobservable (404) | `31a4a7cac4cade9209c4af3050638127835287e7` | Cited file is byte-identical at L3 `4ec3932`. |
| `sources.nav_token_code.locator`, line 133 | `abcc2f09ba5ee022d2066ed59ea09e01b2dd85be` | no | no | unobservable (404) | `31a4a7cac4cade9209c4af3050638127835287e7` | All three cited files exist in the same L3 tree. |
| `VERIFICATION-2026-08-19-nav-transcription.md:14` | `dd8c7f203cb506b70f4d4abe2e85bee6101e9893` | no | no | unobservable (404) | `bff5b3d98fcc56e761dfc002ca1bf2064ac296e8` | L1 object retained; L3 equivalent above. |
| `VERIFICATION-2026-08-19-nav-transcription.md:15-16` | `abcc2f09ba5ee022d2066ed59ea09e01b2dd85be` | no | no | unobservable (404) | `31a4a7cac4cade9209c4af3050638127835287e7` | L1 object retained; L3 equivalent above. |

The parent relationship also survives by content lineage:
`4ec39323901bec772a2d6fe1934a58f9ce1f1c20^` is
`21925d2487f219f06a79364b972110bf177dca2d`.

### Artifact digests

| Source | Recorded digest | Digest target | Recomputed at L1 locator | Recomputed at L3 equivalent | Disposition |
|---|---|---|---:|---:|---|
| `nav_policy` | `4c547a22b27556102ae2d8cebafcdf396b0418dd983b589d83c2a24e48f2088a` | file bytes at commit | match | match | Stable across the rewrite. |
| `nav_result` | `16aab52af2eb2b5e27d10102b4dfd521bdee7773f1d2151571d5ea381dae9c99` | file bytes at commit | match | match | Stable across the rewrite. |
| `nav_validation` | `ef72f40469ce68cbd08c6dcfed0a436291c367bfcc06bd9330873efc9f5aaa79` | file bytes at commit | match | match | Stable across the rewrite. |

These are digests of file bytes, not Git archives. The packet digest is also a
digest of packet bytes, not an archive. The recorded artifact bytes therefore
survive identity-only history rewrites even though the Git locators do not.

**Task A disposition:** degraded, not destroyed. The current provenance claim
contains dangling Git identities, while retained objects, tree matches, file
digests, and the parent relationship make the cited content recoverable.
Changing the locator grammar or packet assertion is Escalated and was not done.

## Task B — audit across both repositories

### Repository-assessment campaign target

This campaign is not affected by the earlier dangling identities:

| Record | What it identifies | Local | Cleaned origin | Anonymous public | Tree/content result |
|---|---|---:|---:|---:|---|
| `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532` | Frozen assessment target | yes | yes | unobservable (404) | Tree `bbbcc61570c2144ec046402658dc6a463c6e01cf`. |
| `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2` | Uncompressed `git archive --format=tar` bytes for the frozen target | exact match | reproducible from fetched commit | unobservable (404) | Recomputed exactly from `83e1d09...`. |
| `61a63fc1eb09c655cfee53aefb96b2045f1ca9bf` | Corrected L3 HEAD | yes | yes | unobservable (404) | Current checkout and cleaned origin agree. |

The target and archive digest are load-bearing but intact. The files containing
these records were created after the September 3 rewrite and cite L3 objects.
One separate durability limitation remains: the entire
`docs/projects/repository_assessment/` directory is currently untracked in the
working tree, so these records do not yet have committed repository provenance.

The following is the complete reference inventory found for those three values.
Columns give current line numbers; `-` means that value does not occur in the
file. Every target occurrence has the first disposition above, every archive
occurrence the second, and every corrected-HEAD occurrence the third. The
archive digest occurs 71 times across 43 of these files.

| File | Target lines | Archive lines | Corrected HEAD lines |
|---|---:|---:|---:|
| `docs/internal/CODEX_THREAD_HANDOFF.md` | 22, 81 | - | - |
| `docs/internal/REPOSITORY_ASSESSMENT_HANDOFF_2026-09-02.md` | 20 | - | - |
| `docs/internal/ROADMAP.md` | 26, 188 | - | - |
| `docs/internal/STATUS.md` | 70, 117, 136, 184 | - | - |
| `docs/projects/repository_assessment/ORNITH-1.5-35B-KNOWN-DEFECT-BASELINE-2026-09-07.md` | 22 | 24 | 72 |
| `docs/projects/repository_assessment/ORNITH-1.5-35B-KNOWN-DEFECT-PREREGISTRATION-2026-09-07.md` | 35 | 37 | - |
| `docs/projects/repository_assessment/ORNITH-1.5-35B-STAGED-ASSESSMENT-2026-09-07.md` | 23 | 24 | 83 |
| `docs/projects/repository_assessment/ORNITH-1.5-35B-STAGED-ASSESSMENT-PREREGISTRATION-2026-09-07.md` | 43, 143-145 | 45 | - |
| `docs/projects/repository_assessment/ORNITH-ADAPTIVE-STAGED-V2-2-ASSESSMENT-2026-09-08.md` | 19 | - | 20 |
| `docs/projects/repository_assessment/ORNITH-ADAPTIVE-STAGED-V2-PLAN-2026-09-07.md` | 16, 22, 170, 353-355, 455 | - | - |
| `docs/projects/repository_assessment/ORNITH-ADAPTIVE-STAGED-V2-PREREGISTRATION-2026-09-07.md` | 43, 63 | 45 | - |
| `docs/projects/repository_assessment/ORNITH-POST-V2-2-NEXT-ROUND-RECOMMENDATION-2026-09-08.md` | 9, 198 | - | - |
| `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-KNOWN-DEFECT-BASELINE-2026-09-06.md` | 10, 44, 49, 57 | - | 53, 58 |
| `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-PREREGISTRATION-2026-09-07.md` | 34, 128 | 36 | - |
| `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-PLANNER-COMPARISON-2026-09-07.md` | 19 | 21 | 70 |
| `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-PLANNER-RERUN-PREREGISTRATION-2026-09-06.md` | 33, 140-142 | - | - |
| `docs/projects/repository_assessment/runs/2026-09-06-qwen3-coder-30b-a3b/independent-adjudication.json` | 10, 30 | - | 3 |
| `docs/projects/repository_assessment/runs/2026-09-06-qwen3-coder-30b-a3b/run-metadata.json` | 23 | - | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-known-defect-baseline/01-baseline-seed17/run-metadata.json` | 54, 177 | 53, 176 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-known-defect-baseline/02-baseline-seed31/run-metadata.json` | 54, 177 | 53, 176 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-known-defect-baseline/03-baseline-seed47/run-metadata.json` | 54, 177 | 53, 176 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-known-defect-baseline/independent-adjudication.json` | 4, 14 | - | 5 |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-known-defect-baseline/independent-trust-reproducer-results.json` | 9 | - | 21 |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-known-defect-baseline/server-fingerprint.json` | 43 | 42 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-staged-assessment/01-staged-seed17/run-metadata.json` | 57, 341 | 56, 340 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-staged-assessment/02-staged-seed31/run-metadata.json` | 57, 341 | 56, 340 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-staged-assessment/03-staged-seed47/run-metadata.json` | 92, 381 | 91, 380 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-staged-assessment/independent-adjudication.json` | 4, 25, 28, 29 | - | 5 |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-staged-assessment/independent-grader-results.json` | 4, 6 | 7 | 13 |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-1.5-35b-staged-assessment/server-fingerprint.json` | 43 | 42 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-adaptive-staged-v2-development/pair-seed17/01-v1-seed17/run-metadata.json` | 161, 447 | 160, 446 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-ornith-adaptive-staged-v2-development/pair-seed17/02-v2-seed17/run-metadata.json` | 74, 602 | 73, 601 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/independent-adjudication.json` | 4 | - | 5 |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/q4-control-selection.json` | 9 | 10 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/q8/01-baseline-seed17/run-metadata.json` | 50, 178 | 49, 177 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/q8/02-baseline-seed31/run-metadata.json` | 50, 178 | 49, 177 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/q8/03-baseline-seed47/run-metadata.json` | 50, 179 | 49, 178 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/q8-server-fingerprint.json` | 3 | 4 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/01-baseline-seed17/run-metadata.json` | 47, 114 | 46, 113 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/confirmatory/01-baseline-seed17/run-metadata.json` | 47, 174 | 46, 173 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/confirmatory/02-planner-seed17/run-metadata.json` | 138, 263 | 137, 262 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/confirmatory/03-planner-seed31/run-metadata.json` | 171, 316 | 170, 315 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/confirmatory/04-baseline-seed31/run-metadata.json` | 47, 175 | 46, 174 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/confirmatory/05-baseline-seed47/run-metadata.json` | 47, 176 | 46, 175 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/confirmatory/06-planner-seed47/run-metadata.json` | 167, 292 | 166, 291 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/independent-adjudication.json` | 4, 7 | - | 5 |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/server-fingerprint.json` | 36 | 35 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/valid/01-baseline-seed17/run-metadata.json` | 47, 180 | 46, 179 | - |
| `docs/projects/repository_assessment/runs/2026-09-07-qwen3-coder-30b-a3b-planner-comparison/valid/02-planner-seed17/run-metadata.json` | 181, 311 | 180, 310 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-1-development/pair-seed17/01-v1-seed17/run-metadata.json` | 57, 346 | 56, 345 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-1-development/pair-seed17/02-v2-1-seed17/run-metadata.json` | 115, 710 | 114, 709 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/independent-adjudication.json` | 4, 27, 227 | 5 | 6 |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/independent-grader-results.json` | 4, 7 | 8 | 14 |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/pair-seed17/01-v1-seed17/run-metadata.json` | 57, 345 | 56, 344 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/pair-seed17/02-v2-2-seed17/run-metadata.json` | 121, 846 | 120, 845 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/pair-seed31/01-v2-2-seed31/run-metadata.json` | 74, 750 | 73, 749 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/pair-seed31/02-v1-seed31/run-metadata.json` | 57, 343 | 56, 342 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/pair-seed47/01-v1-seed47/run-metadata.json` | 92, 378 | 91, 377 | - |
| `docs/projects/repository_assessment/runs/2026-09-08-ornith-adaptive-staged-v2-2-development/pair-seed47/02-v2-2-seed47/run-metadata.json` | 121, 836 | 120, 835 | - |

### Other `llm-reliability-lab` records

| File and line | Recorded identity | Claim | Current/cleaned-origin resolution | Recoverability |
|---|---|---|---|---|
| `evidence/EP-NAV-LEDGER.json:3,108,117,126,133`; `docs/planning/VERIFICATION-2026-08-19-nav-transcription.md:14-16`; `docs/planning/VERIFICATION-2026-08-19-nav-disclosure-review.md:30-31`; `docs/planning/AUDIT-2026-08-22-m0-rev8-evidence-support.md:50,52`; `docs/planning/VERIFICATION-2026-08-23-m0-rev8-evidence-support.md:40-41`; `docs/planning/ADR-001-course-durable-artifacts.md:161` | `dd8c7f...`, `abcc2f...` | NAV policy/result provenance | no / no | L1 objects retained; L3 tree equivalents `21925d2` and `4ec3932`. |
| `docs/planning/INCIDENT-LOG.md:314,335` | recorded `9606d9b`; full L1 `9606d9b46a1dad9fc4a5a96aad0a473ecf5b25eb` | Characterization v2 artifacts and fix | no / no | Tree `31a0c92a15539c3c4bca5457622b5faf7e48028b`; same tree at L3 `e4a932feff274b35439c61604e6ce57aa259ebe6`. |
| `docs/planning/INCIDENT-LOG.md:362` | recorded `5b08c89`; full L1 `5b08c89b66160b8ca7fa4815649d5bfc169d8d01` | Recovery artifacts | no / no | Tree `8df6a0c6238dbf556713cc27e2aa9ee9b279e548`; same tree at L3 `7c73ca5d6288604930a62c4928b0095f433796b4`. |
| `docs/planning/INCIDENT-LOG.md:362` | recorded `67742d5`; full L1 `67742d5dd8a1c36d97fc43e7e9cf2170e0b45a33` | Recovery artifacts | no / no | Tree `c8fd66380f9588f967827af469287991e88248ba`; same tree at L3 `9ed67c177e766f44519c8f5730a68f5a77dc67dc`. |
| `docs/planning/INCIDENT-LOG.md:384` | recorded `518babd`; full L1 `518babdfd9d55a899cba523fdea70fb28afd764c` | Headroom-gate finding | no / no | Tree `7153cdcd382f3aab06841563a207844c1f86d3dc`; same tree at L3 `3467ff95fd56a08435bda7774f6cc06f11c5a47f`. |
| `docs/planning/M0-IMPLEMENTATION-STATUS.md:322` | `1413fac358a5c90c93c6dcb86d0e97b686ddfe8b87361c0ad3430421e8bdb77b` | `EP-NAV-LEDGER` packet bytes | not a commit | Recomputed packet-byte digest; not rewrite-sensitive. |

`M0-IMPLEMENTATION-STATUS.md:93,95,278` also contains `4c8f3b7` and `bbcddd8`;
these identify commits in `llm-reliability-lab`, not `ai_tools`, and resolve in
that repository. Other 64-character values in lab packets and failure-lab
fixtures identify packet bytes, source bytes, or fixture records rather than an
`ai_tools` commit or archive. `ENGRAM_SOURCE_PROVENANCE_REVIEW.md`'s
`5696...` reference belongs to a separately archived Enram repository and was
excluded from this `ai_tools` audit.

## Task C — what `21be7d8` repaired

Commit `21be7d84e7c141078e843c0d472688b105f3b083` is dated
2026-09-03 10:00:40 -0700 and changes 19 files. Parsing its zero-context diff
found **94 changed SHA-token occurrences representing 47 literal old/new token
pairs**. It changed **zero 64-character SHA-256 digest occurrences**.

| Count | Old token | New token | Files |
|---:|---|---|---|
| 3 | `011d049` | `18c763a` | `ADR-020`, `SESSION_HANDOFF` |
| 1 | `0c478b1` | `987d743` | `CODEX_THREAD_HANDOFF` |
| 1 | `1265f92` | `95c6ab1` | `NAV-STRUCT-00-VALIDATION` |
| 6 | `14ac320` | `6c22fc5` | `ADR-019`, `SESSION_HANDOFF`, `SPEC-LIVE-01`, `SPEC-LIVE-00` |
| 1 | `1c288d6` | `e95498e` | `STATUS` |
| 2 | `1d7a057` | `40f3017` | `SPEC-MAIL-00` |
| 3 | `2191e09` | `b5e911d` | `STATUS`, `SESSION_HANDOFF`, `mail_lib_status_v0.1` |
| 1 | `24100ff` | `60c1df2` | `CODEX_THREAD_HANDOFF` |
| 1 | `253069c` | `38a6099` | `CODEX_THREAD_HANDOFF` |
| 1 | `2e0597a` | `ba535a3` | `CLAUDE_VERIFICATION_HANDOFF` |
| 2 | `2e51683` | `7d37920` | `CODEX_THREAD_HANDOFF` |
| 3 | `32f32a7` | `0d0b0c3` | `CLAUDE_VERIFICATION_HANDOFF`, `CODEX_THREAD_HANDOFF` |
| 1 | `3981e40` | `cbc0bc9` | `NAV-TEST-00-ACTION-GUARD-VALIDATION` |
| 4 | `4a5c671` | `ae377bc` | `SESSION_HANDOFF`, both `SPEC-COORD-02` files, `SPEC-LIVE-00` |
| 1 | `4a7f26e` | `d4c4aec` | `CODEX_THREAD_HANDOFF` |
| 1 | `4fc8493` | `479bb15` | `SPEC-EXEC-00` |
| 1 | `5410204` | `2307988` | `CODEX_THREAD_HANDOFF` |
| 4 | `58e07a0` | `4ddf31e` | `OWNERSHIP_PROVENANCE_AUDIT`, `SESSION_HANDOFF` |
| 1 | `58e07a042e5030c78a57f4b3fa1b59bcc315e07e` | `4ddf31e8f12f768cd6ef2d6e2d9a9de182c97f9a` | `ENGRAM_SOURCE_PROVENANCE_REVIEW` |
| 2 | `72caded` | `17211fe` | `STATUS`, `mail_lib_status_v0.1` |
| 1 | `77c6a86` | `6bdd44c` | `STATUS` |
| 5 | `7a4a273` | `49026ea` | `CLAUDE_VERIFICATION_HANDOFF` |
| 1 | `7a4a27354290f1174f3f4fb1e1707239176d9e66` | `49026eac3d2e24b02641bf9db0a76e94909e9386` | `CLAUDE_VERIFICATION_HANDOFF` |
| 3 | `7a6e0d1` | `cda69ca` | `CLAUDE_VERIFICATION_HANDOFF`, `CODEX_THREAD_HANDOFF` |
| 1 | `7a8013a` | `22d7c14` | `CODEX_THREAD_HANDOFF` |
| 1 | `832591a` | `550a197` | `SESSION_HANDOFF` |
| 1 | `869c46d` | `35b3a2c` | `NAV-TEST-00-ACTION-GUARD-VALIDATION` |
| 2 | `9668ec8` | `d0753fc` | `NAV-TEST-00-ACTION-GUARD-VALIDATION` |
| 1 | `9badf67` | `c0b0f02` | `NAV-TEST-00-ACTION-GUARD-VALIDATION` |
| 2 | `9ea8d28` | `b3d2abe` | `CLAUDE_VERIFICATION_HANDOFF`, `CODEX_THREAD_HANDOFF` |
| 1 | `9ea8d28a2cfb9a04c796368bfba3694067bdce5b` | `b3d2abe59bf3b47550851e938facfec3bc98f2e0` | `STATUS` |
| 3 | `9f9125f` | `f9451b2` | `STATUS`, `SESSION_HANDOFF`, `mail_lib_status_v0.1` |
| 2 | `9fa29c1` | `070dbd6` | `ADR-019`, `SPEC-LIVE-01` |
| 1 | `a616670` | `31cfdb0` | `CODEX_THREAD_HANDOFF` |
| 6 | `a80c45c` | `5e95695` | `STATUS`, `SESSION_HANDOFF`, `SPEC-MAIL-01`, `mail_lib_status_v0.1` |
| 1 | `a95b5cb` | `4122f45` | `CODEX_THREAD_HANDOFF` |
| 3 | `c7f2d89` | `8d36243` | `STATUS`, `SESSION_HANDOFF`, `mail_lib_status_v0.1` |
| 5 | `cb5ad2a2` | `3fd5fc24` | `CLAUDE_VERIFICATION_HANDOFF` |
| 1 | `cb5ad2a2a21ffabe2bee814fdc4a91342dbe21b1` | `3fd5fc24a351774c0b0220c4da153d88b9072376` | `CLAUDE_VERIFICATION_HANDOFF` |
| 1 | `d5b795c` | `25c4ff0` | `STATUS` |
| 2 | `db81d51` | `5e5da55` | `ADR-023`, `OWNERSHIP_PROVENANCE_AUDIT` |
| 2 | `e71c9b0` | `250c1b8` | `SESSION_HANDOFF` |
| 1 | `ee5b14a` | `f52aa22` | `SESSION_HANDOFF` |
| 1 | `f0f1e6e` | `c0cf400` | `CODEX_THREAD_HANDOFF` |
| 3 | `f151893` | `4ec3932` | `STATUS`, `SESSION_HANDOFF` |
| 2 | `f8fd116` | `fbf8934` | `ADR-019`, `SESSION_HANDOFF` |
| 1 | `fdac861` | `8a9677c` | `NAV-TEST-00-ACTION-GUARD-VALIDATION` |

The 19 changed files were:

- `adr/ADR-019-lease-lifecycle-recovery-contract.md`
- `adr/ADR-020-data-only-model-loading.md`
- `adr/ADR-023-split-repository-licensing.md`
- `docs/internal/CLAUDE_VERIFICATION_HANDOFF_2026-09-01.md`
- `docs/internal/CODEX_THREAD_HANDOFF.md`
- `docs/internal/ENGRAM_SOURCE_PROVENANCE_REVIEW.md`
- `docs/internal/OWNERSHIP_PROVENANCE_AUDIT.md`
- `docs/internal/STATUS.md`
- `docs/internal/history/SESSION_HANDOFF.md`
- `docs/projects/SPEC-COORD-02-enforced-reservations.md`
- `docs/projects/SPEC-COORD-02-unified-ownership.md`
- `docs/projects/SPEC-EXEC-00-command-failclosed.md`
- `docs/projects/SPEC-LIVE-01-termination.md`
- `docs/projects/agent_lib/NAV-STRUCT-00-VALIDATION.md`
- `docs/projects/agent_lib/NAV-TEST-00-ACTION-GUARD-VALIDATION.md`
- `docs/projects/computer_helper/SPEC-LIVE-00-live-multi-agent.md`
- `docs/projects/mail_lib/SPEC-MAIL-00-triage.md`
- `docs/projects/mail_lib/SPEC-MAIL-01-personal-rules.md`
- `docs/projects/mail_lib/mail_lib_status_v0.1.md`

Only one of these files contains a 64-character archive digest after the
repair: `CLAUDE_VERIFICATION_HANDOFF_2026-09-01.md:20`. Its paired commit was
changed on line 19, but its digest was untouched. Therefore the count of
records pairing a repaired SHA with an unrepaired digest is **one**.

The split predates `21be7d8`, but not the original handoff. At
`d87fef10478b404bfa04a9f664f29f0765d4c413` (2026-09-01 15:24:52 -0700),
line 19 cited `fe4ba3416c04d2e6e460a759cd295d48feb7ba18` and line 20 contained the
retained archive digest; `git get-tar-commit-id` confirms that exact embedded
identity. Commit `88d87318b736b027e029e0d97e02e19331f2b5b9` (2026-09-03
09:22:09 -0700) changed the cited SHA to `7a4a273...` and did not change the
digest. Commit `21be7d8` then changed `7a4a273...` to `49026eac...`, again
without changing the digest. The record was internally consistent when
written, became split in the first provenance-repair pass, and remained split
through the second.

### Confirmed split pair

| Property | Retained archive | Repaired locator |
|---|---|---|
| Recorded value | archive digest `78dd869926b3b581f8ef7bffbc2962b5aa589e83a3e73a860d1cf4ce45b9e93e` | commit `49026eac3d2e24b02641bf9db0a76e94909e9386` |
| Embedded commit | `fe4ba3416c04d2e6e460a759cd295d48feb7ba18` | `49026eac...` |
| Tree | extracted files match `49026eac...` | `a55d073413f0f5d83a711d9e5a59e1d85040c6ca` |
| Uncompressed tar digest | `320aafed0e9cc64c5e7650fa75986e6ead66bda613ab0607a4afd2ef53d5de94` | regenerated with matching prefix: `db59d87548f041fad8d2327a2d58f449530ff89624d09dad945b3287f64ece93` |

Both extracted trees contained 903 files and `diff -qr` found no differences.
The tar bytes differ because `git archive` writes the source commit identity
into its pax header. Thus the archive digest is valid for its retained L2
archive but is not reproducible from the repaired L3 commit identity.

## Task D — archive verification record

### Archive inventory

| Archive/copy | Recomputed SHA-256 | Lineage and HEAD | Scope checked |
|---|---|---|---|
| `/home/cybernaif/repos/ai_tools-fe4ba34.tar.gz` | `78dd869926b3b581f8ef7bffbc2962b5aa589e83a3e73a860d1cf4ce45b9e93e` | Git archive of L2 `fe4ba341...`; no `.git`; 1,052 tar entries | Digest, embedded commit, extraction, tar-level comparison |
| `/home/cybernaif/repos/temp/repos/ai_tools.tar.gz` | `586862ee905e68bd01ba248d720e1e3a8e72e48be6177c759f6c0fef203b2649` | L1, HEAD `518babdfd9d55a899cba523fdea70fb28afd764c`, 301 commits across `--all` | History, credential reachability, tags, branches |
| `/home/cybernaif/repos/temp/ai_tools.tar.gz` | `1c3e1ee4f157f0c115b2810d7bf5ad3e2f0c40f67be7551831eeaa51691ac720` | L1, HEAD `da15c329e3de431e7cd994d6823d1ce4dc82d9c2`, 340 commits across `--all` | History, credential reachability, reflog, tags, branches, trees |
| Current L3 checkout | deliberately not assigned an archive digest | L3, HEAD `61a63fc1eb09c655cfee53aefb96b2045f1ca9bf` | Current history and credential scan |

### Credential reachability, without credential bytes

Codex independently scanned every `origin/main` revision in each L1
repository for a credential-shaped 64-character lowercase-hex value in the six
known configuration paths. The scan retained only counts, paths, commit IDs,
dates, and ancestor-test booleans; it did not print or store the value.

Both L1 repositories produced the same result: seven carrying revisions, six
paths, one distinct value, and all seven revisions are ancestors of
`origin/main`.

| Carrying revision | Commit date | Ancestor of L1 `origin/main` |
|---|---|---:|
| `3d7ee71310b741e05acbee4d5fe8c7e7a14e73d2` | 2026-06-01 08:25:08 -0700 | yes |
| `752ba5e9fdedb073ae45e476baf0304315b1cb03` | 2026-06-01 11:03:08 -0700 | yes |
| `e2644b28754333f414dce1fccb8083744eeb745a` | 2026-06-04 20:40:39 -0700 | yes |
| `55ca732f4c06f8d55ef3bdc08c33de05035c3e50` | 2026-06-05 07:13:46 -0700 | yes |
| `04682bf19be6100f2d98067448432573e65c2ae0` | 2026-06-07 09:31:05 -0700 | yes |
| `ed73f04338997e3feee9b6c4c815a9dfe94f60e2` | 2026-06-20 20:56:38 -0700 | yes |
| `a057e76743bd96f96bb5f7e2c46f15b29064de0e` | 2026-06-21 09:05:25 -0700 | yes |

In the retained L1 lineage, the first carrying revision is `3d7ee713...` on
2026-06-01. Its first `origin/main` successor without the value is
`3dceb3e87e18f75fe20aa94025ffc3a06e99f14e` on 2026-06-21 10:51:24 -0700.
That removal tree is `062f88a3953480823f6ddf43848e2b82a79afeed`, identical to
current L3 `4ddf31e8f12f768cd6ef2d6e2d9a9de182c97f9a`. Thus the reported
June 1 introduction and June 21 removal dates reproduce under different L1/L3
commit identities.

The six carrying paths were:

- `asc/mcp_agent_mail/.claude.backup/settings.json`
- `asc/mcp_agent_mail/.claude.backup/settings.local.json`
- `asc/mcp_agent_mail/.mcp.json`
- `asc/mcp_agent_mail/cline.mcp.json`
- `asc/mcp_agent_mail/codex.mcp.json`
- `asc/mcp_agent_mail/windsurf.mcp.json`

The current L3 `main` scan covered 295 revisions and found zero carrying
revisions, zero distinct values, and zero carrying paths. This establishes
absence only for the scanned pattern and current reachable `main` history.

### Reflog

The recovered L1 repository's last `refs/remotes/origin/main` reflog entry is
dated 2026-08-31 06:38:19 -0700 and says `update by push`. The preceding
retained entries also say `update by push`, not fetch. The 08-29 copy ends
earlier, as expected from its capture date.

### Tree and lineage stability

| Content | Earlier identity | Current identity | Tree/result |
|---|---|---|---|
| `refactor: simplify repository structure` | L1 `da15c329e3de431e7cd994d6823d1ce4dc82d9c2` | L3 `7d37920a81a...` | Both tree `0177f7c8288a42ca771084c42362ddb6f90a9640`. |
| `fix: fail publication hygiene closed without git` | L2 archive `fe4ba3416c04d2e6e460a759cd295d48feb7ba18` | L3 `49026eac3d2e24b02641bf9db0a76e94909e9386` | Extracted file comparison: zero differences across 903 files; L3 tree `a55d073413f0f5d83a711d9e5a59e1d85040c6ca`. |
| LICENSE lineage marker | L1 `01a875abd1da44dddaa3785f56125af4c544c7ca` | L3 `f09211d70c28cb701dac789c4dd495b3845bcfb0` | Distinct commit identities for the same early milestone. |

Host-file times bracket the first rewrite between the recovered L1 archive
mtime (2026-09-01 09:42:22 -0700) and the L2 `fe4ba34` archive mtime
(2026-09-01 15:07:59 -0700), assuming those mtimes were preserved. The latest
working-tree mtime reproduced from the L1 archive is 2026-09-01 13:41:33 UTC,
which is 06:41:33 -0700—not 13:41 -0700. The timezone in the supplied
Claude-reported bracket therefore did not reproduce. The second rewrite is
recorded by `21be7d8` at 2026-09-03 10:00:40 -0700.

### `Qwen_findings.md`

The file's cited `d9f58f7`, `58e07a0`, and assessed HEAD `b6780b8` resolve in
none of the current checkout, cleaned-origin clone, L1 recovered repository, or
L1 08-29 repository. The cleaned origin rejected direct fetches of all three.

The content-derived claims were independently reproduced without relying on
those missing identities:

- seven carrying revisions and six files, as listed above;
- both release tags are lightweight;
- `salvage/detached-venv-fixes` has seven patch-unique commits and
  `split/llm-failure-lab` has sixteen, totaling 23, in both L1 repositories;
- the recovered L1 `origin/main` reflog records pushes.

The audit does not reproduce the credential fragment already redacted in that
file.

### Post-review check of the excluded archives

After Claude reviewed the first audit, Codex inspected the additional archives
that had initially been excluded:

| Archive | Result | Can recover L2 mappings? |
|---|---|---:|
| `/home/cybernaif/repos/ai_tools-pre-fix-untracked-2026-09-03.tar.gz` | SHA-256 `89e3f3a6c533b17ab65a3f7f9b849ae124e1f5ce4f9ec5199b4e4c14185efa40`; seven ordinary untracked files; no `.git` directory | no |
| `/home/cybernaif/repos/ai_tools.tar.gz` | SHA-256 `9280aac5ff48d562786016be53d4ee9542eb722ab5582cbf46759691593a7d19`; full L3 checkout at `61a63fc...`; `git fsck --full --no-reflogs --unreachable` returned no unreachable objects | no |
| `/home/cybernaif/repos/temp/repos.tar.gz` | SHA-256 `c307051f0abdfbc5803be94c14cd4338d970f186cb21a03f6f616356da53473a`; extracted `ai_tools/.git` has L1 HEAD `518babdf...` and 301 commits across refs; `fsck` finds unreachable L1 objects | no; none of the 47 old literal tokens resolves, including among unreachable objects |

The most promising filename therefore does not contain Git history, and the
newer full checkout has no unreachable L2 objects. This follow-up did not
recover any of the missing identities.

The `21be7d8` count also needs precise interpretation. The diff contains 47
distinct **literal token pairs**, but four pairs are duplicate short/full
spellings. Resolving the replacement side produces **43 distinct L3 commit
identities**. Every old token in all 47 literal pairs is absent from the current
checkout, both L1 copies, and the additional L3 archive. Consequently none of
the 43 direct L2-to-L3 commit mappings can now be verified from retained Git
objects. The two tree comparisons in this report are independent content
anchors from other retained identities; they support the rewritten lineages
but do not directly validate the missing `21be7d8` source commits.

### Exact commands used

The following are the load-bearing command forms used. The credential scanner
printed metadata only and deliberately never printed matched bytes.

```text
sha256sum /home/cybernaif/repos/ai_tools-fe4ba34.tar.gz
sha256sum /home/cybernaif/repos/temp/ai_tools.tar.gz
sha256sum /home/cybernaif/repos/temp/repos/ai_tools.tar.gz

gzip -dc /home/cybernaif/repos/ai_tools-fe4ba34.tar.gz | git get-tar-commit-id
gzip -dc /home/cybernaif/repos/ai_tools-fe4ba34.tar.gz | sha256sum
git -C /home/cybernaif/repos/ai_tools archive --format=tar --prefix=ai_tools-fe4ba34/ 49026eac3d2e24b02641bf9db0a76e94909e9386 | sha256sum
diff -qr /tmp/ai-tools-provenance-audit-fe4 /tmp/ai-tools-provenance-audit-490

git -C <repo> rev-parse <commit>^{tree}
git -C <repo> cat-file -e <commit>^{commit}
git -C <repo> cat-file -p <commit>:<path> | sha256sum
git -C <repo> merge-base --is-ancestor <revision> origin/main
git -C <repo> reflog show --date=iso refs/remotes/origin/main
git -C <repo> for-each-ref refs/tags --format='%(refname:short) %(objecttype) %(objectname)'
git -C <repo> rev-list --count main..<branch>
git -C <repo> cherry main <branch>

python3 /tmp/credential_reachability_audit.py /home/cybernaif/repos/temp/ai_tools
python3 /tmp/credential_reachability_audit.py /home/cybernaif/repos/temp/repos/ai_tools
python3 /tmp/credential_reachability_audit.py /home/cybernaif/repos/ai_tools

git clone --bare https://github.com/jdean314159/ai_tools.git /tmp/ai-tools-remote-audit-2026-09-08.git
git -C /tmp/ai-tools-remote-audit-2026-09-08.git fetch origin <recorded-sha>
git ls-remote --heads --tags origin
curl -sS -o /dev/null -w '%{http_code}' https://api.github.com/repos/jdean314159/ai_tools
curl -sS -o /dev/null -w '%{http_code}' https://github.com/jdean314159/ai_tools
```

## Task E — editorial repair

Removed the standalone word `Higher` between two sentences in the Result
section of
`docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-2026-09-07.md`.
No numerical result, interpretation, or experiment record changed.

## Not checked

- No credential value, prefix, suffix, or carrying-file contents were inspected
  for reporting or copied into this record. The automated scanner necessarily
  matched bytes in memory to count distinct values, but suppressed them from
  all output.
- None of the 43 semantic `21be7d8` old/new commit mappings can be checked
  directly because every old L2 identity is absent. The 47 literal token pairs,
  94 changed occurrences, 43 normalized replacement identities, and digest
  change count were checked. The two load-bearing content anchors above were
  independently reproduced, but they do not restore the missing L2 objects.
- Anonymous GitHub resolution could not be tested beyond the observed 404. The
  configured remote, its advertised refs, a fresh fetched object database, and
  direct old-object fetch failures were checked separately.
- The additional archives received the bounded L2-recovery check reported
  above. Only `ai_tools/.git` was extracted from the 3.8-GiB
  `temp/repos.tar.gz`; its unrelated repository contents were not extracted.
- No archive digest was created for the current L3 checkout, preserving the
  work order's explicit omission.
- No `llm-reliability-lab` teaching claim or packet body was re-adjudicated;
  this audit checked provenance references and recoverability only.
