# Inspector UI artifact replay — 2026-08-31

## Question and boundary

Can the workbench load a shared run-artifact JSON file and reproduce Inspector's
offline inspection summary without executing the recorded model, tools, or
experiment?

The new **Artifact replay** tab accepts one JSON file up to 5 MB, parses it
through `llm_harness_core`'s validated artifact contract, and delegates summary
semantics to `llm_inspector.inspect_artifact`. It does not import the record into
the workbench session database, resolve a bundle directory, rerun inference,
execute tools, or reconstruct raw content omitted by the producer.

## Deterministic validation

Two committed artifacts exercise both supported outcomes:

- The Flash-Next model-characterization campaign loads as a supported body and
  reconstructs its `model_characterization_campaign` summary.
- The newer `agent_lib.command_isolation` profile loads successfully but remains
  envelope-only because Inspector does not declare that body profile supported.
  The UI displays the existing unsupported-body notice instead of guessing at
  its semantics.

Malformed JSON, non-object JSON, invalid artifact envelopes, and oversized
uploads are rejected. Error messages report the failure class without echoing
uploaded content.

## Interpretation limit

This validates read-only inspection replay for single JSON artifacts. It is not
deterministic execution replay, model replay, tool replay, session import,
artifact editing, or portable bundle upload. Bundle-directory resolution remains
available in the Inspector library and CLI but is not exposed through this
browser upload path.
