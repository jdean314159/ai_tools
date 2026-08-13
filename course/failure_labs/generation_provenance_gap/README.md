# Generation provenance gap

This no-GPU lab uses one real local Ollama generation recorded on an RTX 3090.
The output followed the prompt exactly. Your task is to separate what that
successful result proves from what the artifact explicitly does not establish.

From the course repository root:

```bash
llm-inspect artifact show \
  failure_labs/generation_provenance_gap/record.json \
  --format json
```

Answer from the Inspector output and then, where needed, the record itself:

1. Which backend and requested/reported model labels were recorded?
2. Did the response satisfy the synthetic prompt, and what usage was measured?
3. Can this record establish the exact model weights, quantization, tokenizer,
   chat template, runtime build, queue time, or prefill time?
4. Does `temperature: 0.0` plus one successful response establish deterministic
   replay?
5. Why is an empty `capabilities` list the honest declaration here?

Write a short conclusion before reading `SOLUTION.md`. Do not turn an absent
fact into a negative fact: “quantization not reported” does not mean “not
quantized.”

