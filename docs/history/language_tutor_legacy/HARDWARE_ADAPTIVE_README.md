# Hardware-Adaptive Language Tutor

**Complete implementation using `llm-engine` and `memory-rag` libraries with automatic hardware detection and cloud fallback.**

---

## Quick Start

### 1. Install Dependencies

```bash
cd ~/ai-projects/language_tutor

# Copy these files to your project
cp /path/to/hardware_strategy.py language_tutor/
cp /path/to/engine_manager.py language_tutor/
cp /path/to/tutor_session.py language_tutor/
cp /path/to/main_example.py language_tutor/

# Libraries already installed
# - llm-engine (from core_infrastructure)
# - memory-rag (from memory_rag)
```

### 2. Configure Based on Your Hardware

The system auto-detects your GPU and recommends the optimal strategy:

#### **High-End GPU (20GB+ VRAM)** - RTX 3090, 4090, A6000
```bash
# Run everything locally (zero cost)
python main_example.py
# → Strategy: local_everything
# → Planner: Ollama 32B
# → Executor: vLLM 7B
# → Cost: $0/session
```

#### **Mid-Range GPU (10-20GB VRAM)** - RTX 3060 12GB, 4060 Ti
```bash
# Hybrid: Cloud planning, local execution
export ANTHROPIC_API_KEY="your-key-here"
python main_example.py
# → Strategy: hybrid_cloud_planning
# → Planner: Claude Sonnet (cloud)
# → Executor: vLLM 7B (local)
# → Cost: $0.06/session
```

#### **No GPU or Low VRAM**
```bash
# Cloud-based (requires API key)
export ANTHROPIC_API_KEY="your-key-here"
python main_example.py
# → Strategy: cloud_everything or cloud_executor_only
# → Planner: Claude Sonnet (cloud)
# → Executor: Claude Sonnet or Haiku (cloud)
# → Cost: $0.15-$0.36/session
```

### 3. First Run

```bash
python main_example.py
```

**First-time setup wizard will:**
1. Detect your hardware
2. Check for Anthropic API key
3. Recommend optimal strategy
4. Show cost estimates
5. Save configuration to `~/.language_tutor_config.json`

---

## Architecture

### Hardware Detection

```python
from hardware_strategy import detect_hardware, get_strategy

# Auto-detect
hardware = detect_hardware()
# HardwareProfile(
#     name="high_end",
#     gpu_name="NVIDIA GeForce RTX 3090",
#     vram_gb=24.0,
#     can_run_7b=True,
#     can_run_32b=True,
#     can_run_voice=True,
#     recommended_strategy="local_everything",
# )

# Get strategy
strategy = get_strategy(hardware)
# {
#     "planner": {"engine": "ollama", "model": "qwen2.5:32b"},
#     "executor": {"engine": "vllm", "model": "qwen-7b-awq"},
#     "surprise_filter": True,
#     "cost_per_session": 0.0,
#     ...
# }
```

### Engine Management

```python
from engine_manager import EngineManager

manager = EngineManager(strategy)

# Executor (keep loaded for conversation)
executor = manager.get_executor()  # VLLMEngine or ClaudeEngine

# Planner (load when needed, unload after)
planner = manager.get_planner()    # OllamaEngine or ClaudeEngine
# ... use planner ...
manager.unload_planner()           # Free VRAM

# Memory engine (for surprise filter)
memory_engine = manager.get_memory_engine()  # May be None (cloud mode)
```

### Memory Integration

```python
from memory_rag import ProjectMemory, ProjectType

# Strategy-aware initialization
memory = ProjectMemory(
    project_id="spanish_tutor",
    project_type=ProjectType.LANGUAGE_TUTOR,
    base_dir=Path("data/memory"),
    llm_engine=memory_engine,  # None if cloud executor (disables surprise filter)
    session_id=session_id,
)

# Works with or without surprise filter
memory.store_episode(
    "User confused ser/estar",
    importance=0.8,
)
# → If surprise filter enabled: gates by perplexity
# → If disabled (cloud mode): always stores (bypass_filter=True)
```

### Session Management

```python
from tutor_session import TutorSession

session = TutorSession(
    language="spanish",
    strategy=strategy,
    base_dir=Path("data"),
)

# Start session (planning with 32B or Claude)
await session.start(duration_minutes=30)

# Interactive conversation (7B or Claude)
response = await session.handle_text("¿Cómo se dice 'hello'?")
print(response.text)

# End session (summary with 32B or Claude)
summary = await session.end_session()
```

---

## Strategies Explained

### Strategy 1: `local_everything` ⭐ Best Performance

**Hardware Required:** 20GB+ VRAM (RTX 3090, 4090, A6000)

**Configuration:**
- Planner: Ollama Qwen 32B (`num_gpu=15`, ~12GB VRAM)
- Executor: vLLM Qwen 7B (~12GB VRAM)
- Voice: Full (Whisper + Piper/XTTS)
- Surprise Filter: ✅ Enabled

**Costs:**
- Per session: $0
- Monthly: $0
- Yearly: $0

**Pros:**
- Zero ongoing cost
- Best latency (all local)
- Full privacy
- Voice-enabled

**Cons:**
- Requires high-end GPU
- Higher electricity cost (~$5/month)

---

### Strategy 2: `hybrid_cloud_planning` 🎯 Recommended Balance

**Hardware Required:** 10GB+ VRAM (RTX 3060 12GB, 4060 Ti) + API key

**Configuration:**
- Planner: Claude Sonnet 4 (cloud)
- Executor: vLLM Qwen 7B (local)
- Voice: Full (Whisper + Piper/XTTS)
- Surprise Filter: ✅ Enabled (local executor has logprobs)

**Costs:**
- Per session: $0.06
- Monthly (20 sessions): $1.20
- Yearly (240 sessions): $14.40

**Cost Breakdown:**
- Planning (1 call/session): $0.03
- Summary (1 call/session): $0.03
- Conversation: $0 (local 7B)

**Pros:**
- Affordable ongoing cost
- Excellent planning quality (Claude)
- Fast conversation (local 7B)
- Voice-enabled
- Surprise filter works

**Cons:**
- Requires API key
- Planning phase slower (cloud latency)

---

### Strategy 3: `cloud_executor_only` 💰 Budget Mode

**Hardware Required:** API key only (no GPU needed)

**Configuration:**
- Planner: Claude Sonnet 4 (cloud)
- Executor: Claude Haiku 4 (cloud - cheaper)
- Voice: ❌ Disabled
- Surprise Filter: ❌ Disabled (no logprobs)

**Costs:**
- Per session: $0.15
- Monthly (20 sessions): $3.00
- Yearly (240 sessions): $36.00

**Cost Breakdown:**
- Planning (Sonnet): $0.03
- Summary (Sonnet): $0.03
- Conversation (Haiku): $0.09

**Pros:**
- Works on any hardware (even CPU-only)
- Good quality (Haiku is fast and capable)
- No GPU required

**Cons:**
- Text-only (no voice)
- No surprise filter
- Ongoing API costs
- Slower than local (API latency)

---

### Strategy 4: `cloud_everything` 🌟 Premium Mode

**Hardware Required:** API key only

**Configuration:**
- Planner: Claude Sonnet 4 (cloud)
- Executor: Claude Sonnet 4 (cloud)
- Voice: ❌ Disabled
- Surprise Filter: ❌ Disabled

**Costs:**
- Per session: $0.36
- Monthly (20 sessions): $7.20
- Yearly (240 sessions): $86.40

**Pros:**
- Highest quality responses
- Works on any hardware
- Consistent performance

**Cons:**
- Text-only
- No surprise filter
- Higher ongoing costs
- Slower than local

---

## Feature Comparison

| Feature | Local Everything | Hybrid | Cloud Budget | Cloud Premium |
|---------|-----------------|--------|--------------|---------------|
| **VRAM Required** | 20GB+ | 10GB+ | None | None |
| **API Key Required** | ❌ | ✅ | ✅ | ✅ |
| **Cost/Session** | $0 | $0.06 | $0.15 | $0.36 |
| **Planning Quality** | Excellent | Excellent | Excellent | Excellent |
| **Conversation Quality** | Very Good | Very Good | Good | Excellent |
| **Conversation Speed** | Excellent | Excellent | Good | Acceptable |
| **Voice Support** | ✅ | ✅ | ❌ | ❌ |
| **Surprise Filter** | ✅ | ✅ | ❌ | ❌ |
| **Privacy** | Full | Partial | Cloud | Cloud |

---

## Cost Analysis

### Break-Even Analysis (vs Cloud-Only)

**Scenario:** Currently using `cloud_everything` ($0.36/session), considering GPU upgrade:

**RTX 3060 12GB (~$200 used):**
- New cost: $0.06/session (hybrid strategy)
- Savings: $0.30/session
- Break-even: 667 sessions
- At 20 sessions/month: **33 months**
- Additional benefit: Voice support

**RTX 3090 24GB (~$600 used):**
- New cost: $0/session (local everything)
- Savings: $0.36/session
- Break-even: 1,667 sessions
- At 20 sessions/month: **83 months**
- Additional benefits: Voice support, full privacy, best performance

### Long-Term Projection

**3-year usage (720 sessions):**

| Strategy | Hardware Cost | API Cost | Total | Per Session |
|----------|--------------|----------|-------|-------------|
| Cloud Everything | $0 | $259 | $259 | $0.36 |
| Hybrid (RTX 3060) | $200 | $43 | $243 | $0.34 |
| Local (RTX 3090) | $600 | $0 | $600 | $0.83 |

**5-year usage (1,200 sessions):**

| Strategy | Hardware Cost | API Cost | Total | Per Session |
|----------|--------------|----------|-------|-------------|
| Cloud Everything | $0 | $432 | $432 | $0.36 |
| Hybrid (RTX 3060) | $200 | $72 | $272 | $0.23 |
| Local (RTX 3090) | $600 | $0 | $600 | $0.50 |

---

## Manual Override

Override auto-detection with environment variable:

```bash
# Force specific strategy
export LANGUAGE_TUTOR_STRATEGY="hybrid_cloud_planning"
python main_example.py

# Available strategies:
# - local_everything
# - hybrid_cloud_planning
# - cloud_executor_only
# - cloud_everything
```

---

## Surprise Filter Behavior

### With Local Executor (Strategies 1 & 2)

```python
# ✅ Surprise filter active
memory.store_episode("User confused ser/estar", importance=0.8)
# → Computes perplexity with local 7B
# → Stores only if perplexity > threshold
# → 70-90% memory reduction
```

### With Cloud Executor (Strategies 3 & 4)

```python
# ⚠️ No logprobs from Claude API - filter disabled
memory.store_episode("User confused ser/estar", importance=0.8)
# → Always stores (bypass_filter=True automatically)
# → More episodes stored
# → Use importance threshold as fallback
```

---

## Testing

### Quick Test (No Setup Wizard)

```bash
# Run test mode
python main_example.py --test

# Or test individual components
python hardware_strategy.py    # Test hardware detection
python engine_manager.py        # Test engine loading
python tutor_session.py         # Test session lifecycle
```

### Test With Specific Strategy

```bash
# Test hybrid mode
export LANGUAGE_TUTOR_STRATEGY="hybrid_cloud_planning"
export ANTHROPIC_API_KEY="your-key"
python main_example.py --test

# Test local mode (requires vLLM + Ollama running)
export LANGUAGE_TUTOR_STRATEGY="local_everything"
python main_example.py --test
```

---

## Integration with Graceful Shutdown

Copy graceful shutdown utility from yesterday's work:

```python
# In tutor_session.py, add to __init__:

from graceful_shutdown import setup_graceful_shutdown_for_session

self.shutdown = setup_graceful_shutdown_for_session(
    session=self,
    save_callback=self.end_session,
    project_name=f"{language}_tutor",
    enable_auto_save=True,
    idle_seconds=300,  # 5 min idle = auto-save
)

# In conversation loop:
if detect_goodbye_intent(user_input):
    await self.shutdown.end_session("user_goodbye")
else:
    self.shutdown.update_activity()
```

---

## Troubleshooting

### "Cannot initialize executor engine"

**For vLLM:**
```bash
# Check if server is running
curl http://localhost:8000/health

# If not, start it:
vllm serve Qwen/Qwen2.5-7B-Instruct-AWQ --port 8000 --max-logprobs 5
```

**For Ollama:**
```bash
# Check if server is running
curl http://localhost:11434/api/tags

# If not, start it:
ollama serve

# Pull model if needed:
ollama pull qwen2.5:32b
```

### "No API key found"

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# Add to ~/.bashrc for persistence:
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc
```

### "Surprise filter disabled"

This is normal for cloud strategies (no logprobs available). The system still works:
- Episodes are stored based on importance threshold
- No perplexity gating
- Slightly more memory usage (acceptable tradeoff)

---

## Next Steps

1. **Copy files to your language_tutor project**
2. **Run setup wizard:** `python main_example.py`
3. **Start first session** and verify it works
4. **Add voice pipeline** (STT/TTS from spec)
5. **Implement drill system**
6. **Build FastAPI web interface**

---

## Summary

This implementation provides:

✅ **Automatic hardware detection**
✅ **Optimal local/cloud strategy selection**  
✅ **Cost tracking and transparency**
✅ **Graceful degradation** (works on any hardware)
✅ **Full API compatibility** (uses llm-engine and memory-rag)
✅ **Surprise filter when possible** (local models)
✅ **Professional session management**

The system **adapts to what you have** and **optimizes for cost and performance**.
