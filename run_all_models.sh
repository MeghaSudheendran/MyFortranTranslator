#!/bin/bash

# --- Configuration ---
# List of models to experiment on
MODELS=(
    "codellama/CodeLlama-7b-Instruct-hf"
    "mistralai/Mistral-7B-Instruct-v0.3"
    "Qwen/Qwen2-7B-Instruct"
    "codellama/CodeLlama-13b-Instruct-hf"
    "Qwen/Qwen2.5-Coder-14B-Instruct"
    "Qwen/Qwen2.5-Coder-3B"
    "Qwen/Qwen2.5-Coder-7B"
    "Qwen/Qwen2.5-Coder-7B-Instruct"
    "Qwen/Qwen2.5-Coder-14B"
    "Qwen/Qwen2.5-Coder-32B"
    "Qwen/Qwen2.5-Coder-32B-Instruct"
    "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    # Add other models here...
)

# Fixed settings
TP_SIZE=4
MAX_LEN=8192
INPUT_CSV="input.csv"
RESULTS_DIR="experiment_results"

# --- Setup ---
mkdir -p "$RESULTS_DIR"

# Function to wait for vLLM to fully load the model
wait_for_vllm() {
    echo "Waiting for vLLM to load the model (Health Check)..."
    local url="http://localhost:8000/health"
    local retries=0
    local max_retries=60 # Wait up to 10 minutes (60 * 10s)
    
    until curl -s -f "$url" > /dev/null; do
        sleep 10
        ((retries++))
        if [ $retries -ge $max_retries ]; then
            echo "Error: vLLM failed to become ready after 10 minutes."
            return 1
        fi
        echo -n "."
    done
    echo " vLLM is ready!"
    return 0
}

# --- Main Loop ---
for MODEL_ID in "${MODELS[@]}"; do
    echo "========================================================"
    echo "Starting experiment for: $MODEL_ID"
    echo "========================================================"

    # 1. Generate a sanitized name for files (replace / and - with _)
    SAFE_NAME=$(echo "$MODEL_ID" | tr '/-' '__')
    OUTPUT_FILE="${RESULTS_DIR}/output_${SAFE_NAME}.csv"
    
    # 2. Overwrite .env file dynamically
    echo "Generating .env for $MODEL_ID..."
    cat > .env <<EOF
MODEL_ID=$MODEL_ID
TP_SIZE=$TP_SIZE
MAX_LEN=$MAX_LEN
EOF

    # 3. Restart Docker Container
    echo "Restarting Docker containers..."
    docker compose down
    docker compose up -d

    # 4. Wait for the server to be ready
    if ! wait_for_vllm; then
        echo "Skipping $MODEL_ID due to server failure."
        continue
    fi

    # 5. Run the experiment
    # We pass the specific output file and a specific column name for clarity
    echo "Running translation script..."
    
    make run \
        INPUT_CSV="$INPUT_CSV" \
        OUTPUT_CSV="$OUTPUT_FILE" \
        LEGACY_COL="legacy_code" \
        TRANSLATED_COL="trans_${SAFE_NAME}"

    echo "Finished $MODEL_ID. Results saved to $OUTPUT_FILE"
    
    # Optional: Prune docker to save disk space between large model loads if needed
    # docker system prune -f
done

# --- Packaging ---
echo "========================================================"
echo "All experiments complete."
echo "Zipping results..."
tar -czf all_experiment_results.tar.gz "$RESULTS_DIR"
echo "Results ready: all_experiment_results.tar.gz"
echo "========================================================"
