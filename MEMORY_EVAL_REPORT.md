# Memory Eval Report

## engram_lite

- probe pass rate: 0.714
- prompt pass rate: 0.6
- signal retention: 1.0
- paraphrase retention: 1.0
- decoy rejection: 0.0
- update resolution: 0.0
- noise rejection: 1.0
- failed probes: decision_decoy, update_resolution

- PASS `preference_recall` (signal)
- PASS `preference_paraphrase` (paraphrase)
- PASS `decision_recall` (signal)
- FAIL `decision_decoy` (decoy)
- FAIL `update_resolution` (update)
- PASS `ephemeral_rejection` (noise)
- PASS `assistant_chatter_rejection` (noise)

## engram

- probe pass rate: 1.0
- prompt pass rate: 0.8
- signal retention: 1.0
- paraphrase retention: 1.0
- decoy rejection: 1.0
- update resolution: 1.0
- noise rejection: 1.0
- failed probes: none

- PASS `preference_recall` (signal)
- PASS `preference_paraphrase` (paraphrase)
- PASS `decision_recall` (signal)
- PASS `decision_decoy` (decoy)
- PASS `update_resolution` (update)
- PASS `ephemeral_rejection` (noise)
- PASS `assistant_chatter_rejection` (noise)
