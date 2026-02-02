
## Automated Translation of ESOPE–Fortran to Fortran 2008 using vLLM

---

## 1. Project Overview

This project automates the **translation of legacy ESOPE-Fortran (Fortran 77 + ESOPE extensions)** into **modern Fortran 2008**, using **Large Language Models (LLMs)** served locally via **vLLM**.

The system:

* Runs **multiple LLMs sequentially**
* Sends legacy Fortran code to each model
* Enforces **strict translation rules**
* Stores each model’s output in a **single CSV file**, one column per model

This allows **systematic comparison of model performance** on legacy code modernization.

---

## 2. High-Level Architecture

```
CSV (legacy code)
   ↓
Python translation script
   ↓
OpenAI-compatible API (vLLM)
   ↓
LLM (one at a time, in Docker)
   ↓
Translated Fortran 2008
   ↓
CSV (new column per model)
```

---

## 3. Key Technologies & Tools

### 3.1 Python

Used for:

* CSV processing
* HTTP API calls
* Prompt construction
* JSON response validation
* Retry and error handling

Key libraries:

* `requests` – HTTP communication with vLLM
* `csv` – CSV read/write
* `json` – strict JSON parsing
* `argparse` – CLI arguments
* `re` – fallback extraction via regex

---

### 3.2 vLLM

**vLLM** is a high-performance inference engine for LLMs.

Why vLLM?

* Fast inference
* OpenAI-compatible API (`/v1/chat/completions`)
* Supports large models (30B+)
* GPU parallelism via tensor parallelism

The container exposes:

```
http://localhost:8000/v1/chat/completions
```

---

### 3.3 Docker & Docker Compose

Docker ensures:

* Reproducibility
* GPU isolation
* Easy model switching

Docker Compose is used to:

* Start/stop vLLM
* Swap models dynamically
* Inject environment variables

---

### 3.4 NVIDIA & Grid’5000

The project runs on **Grid’5000 GPU nodes**:

* `g5k-setup-nvidia-docker` configures NVIDIA runtime
* `containerd` is relocated to `/tmp` to avoid disk quota issues

---

## 4. Python Translation Script

### 4.1 Purpose

`translate_fortran_json_response.py`:

* Reads legacy code from CSV
* Sends it to the LLM with strict instructions
* Extracts valid JSON output
* Writes results back to the CSV

---

### 4.2 System Prompt

The `SYSTEM_PROMPT`:

* Defines **ESOPE concepts**
* Enforces **Fortran 2008 rules**
* Provides **explicit examples**
* Forces **JSON-only output**

This dramatically improves consistency and reduces hallucinations.

---

### 4.3 JSON Enforcement Strategy

The model **must** return:

```json
{
  "translated_code": "..."
}
```

To ensure robustness, `extract_code_from_json()` tries:

1. Direct JSON parsing
2. Markdown JSON blocks
3. Regex-based extraction
4. Brace-matching recovery
5. Code block fallback
6. Manual JSON stripping

This makes the pipeline resilient to imperfect model outputs.

---

### 4.4 API Call Logic

Function: `translate_code()`

Steps:

1. Build OpenAI-style payload
2. Send POST request to vLLM
3. Parse response
4. Retry on failure (exponential backoff)
5. Return translated code or error message

Parameters:

* `temperature` → deterministic output (usually `0.0–0.1`)
* `max_tokens` → output length cap
* `top_p` → nucleus sampling (usually `1.0`)

---

### 4.5 CSV Processing

Function: `process_csv()`

Workflow:

1. Load input CSV (`;` separator)
2. Add output column if missing
3. Translate each non-empty legacy cell
4. Append model output
5. Preserve existing columns
6. Write back to disk

Each model writes into **its own column**, enabling comparison.

---

## 5. Docker Compose Configuration

### 5.1 vLLM Service

```yaml
image: vllm/vllm-openai:latest
```

Key options:

* `MODEL_ID` → Hugging Face model name
* `TP_SIZE` → tensor parallelism (number of GPUs)
* `MAX_LEN` → maximum context length
* NVIDIA GPUs exposed via `deploy.resources`

The container behaves like an **OpenAI API server**.

---

## 6. Infrastructure Setup (Grid’5000)

### Step 1 – NVIDIA Docker

```bash
g5k-setup-nvidia-docker -t
```

Enables GPU support inside Docker.

---

### Step 2 – Stop Services

Docker and containerd are stopped to allow safe reconfiguration.

---

### Step 3 – Relocate containerd Storage

```bash
root = "/tmp/containerd-data"
```

Why?

* Avoids home directory quotas
* Improves I/O performance on Grid’5000

---

### Step 4 – Restart Services

Ensures containerd and Docker pick up the new configuration.

---

## 7. Model Experiment Loop

### 7.1 Model List

```bash
MODELS=(
  "codellama/CodeLlama-34b-Instruct-hf"
  "mistralai/Mistral-7B-Instruct-v0.3"
  "Qwen/Qwen2.5-Coder-32B-Instruct"
  "deepseek-ai/deepseek-coder-33b-instruct"
)
```

Each model is tested **independently**.

---

### 7.2 Environment Injection

For each model:

* `.env` is regenerated
* Docker Compose restarted
* vLLM loads exactly one model

---

### 7.3 Health Check

```bash
GET /health
```

The script waits until vLLM reports readiness before sending requests.

---

### 7.4 Translation Execution

The Python script is run with:

* Same CSV as input/output
* New column name derived from model ID
* Deterministic settings

Example column name:

```
output_codellama_CodeLlama_34b_Instruct_hf
```

---

## 8. Final Output

### Output File

```
final_experiment_results.csv
```

Contains:

* Original legacy code
* One column per model
* Side-by-side comparison

This format is ideal for:

* Manual review
* Automated scoring
* Regression testing
* Research publications

---

## 9. Design Strengths

✅ Deterministic translation
✅ Strict JSON validation
✅ Model-agnostic
✅ GPU-efficient
✅ Scalable to more models
✅ Reproducible experiments
