import requests
import time

OLLAMA = "http://localhost:11434/v1/chat/completions"
MODEL = "qwen3.5:9b"

def chat(messages, *, temperature=0.7, model=MODEL) -> str:
    r = requests.post(
        OLLAMA,
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

question = "Give me a name for a Python library that profiles memory leaks."

for i, t in enumerate((0.0, 0.7, 1.2), 1):
    print(f"Starting call {i}/3 at temperature {t}...")
    start = time.time()
    answer = chat([{"role": "user", "content": question}], temperature=t)
    elapsed = time.time() - start
    print(f"[t={t}, {elapsed:.1f}s] {answer.strip()[:120]}\n")
