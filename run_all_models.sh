#!/bin/bash
echo "Checking Docker status..."
if ! docker ps > /dev/null 2>&1; then
    echo "Docker is down. Applying Grid'5000 /tmp storage fix..."
    g5k-setup-nvidia-docker -t
    sudo systemctl stop docker
    sudo systemctl stop containerd
    
    
    # Set root to /tmp if not already set
    sudo sed -i 's|^#*root =.*|root = "/tmp/containerd-data"|' /etc/containerd/config.toml
    sudo systemctl restart containerd
    sudo systemctl restart docker   
fi




# --- 3. Experiment Configuration ---
# List of models to experiment on
MODELS=(
   	"codellama/CodeLlama-7b-Instruct-hf"
	"codellama/CodeLlama-13b-Instruct-hf"
   	"mistralai/Mistral-7B-Instruct-v0.3"
    	"Qwen/Qwen2-7B-Instruct"
	"Qwen/Qwen2.5-Coder-3B"
	"Qwen/Qwen2.5-Coder-7B-Instruct"
	"Qwen/Qwen2.5-Coder-7B"
	"Qwen/Qwen2.5-Coder-14B-Instruct"
	"Qwen/Qwen2.5-Coder-14B"
	"Qwen/Qwen3-Coder-30B-A3B-Instruct"
	"Qwen/Qwen2.5-Coder-32B-Instruct"
	"Qwen/Qwen2.5-Coder-32B"
)

# Fixed settings
TP_SIZE=4
MAX_LEN=8192
INPUT_CSV="input.csv"
FINAL_RESULTS="final_experiment_results.csv"

# --- Setup ---
# Initialize the final file with the content of the input file
if [ ! -f "$INPUT_CSV" ]; then
    echo "Error: $INPUT_CSV not found! Please provide an input file."
    exit 1
fi

echo "Initializing $FINAL_RESULTS from $INPUT_CSV..."
cp "$INPUT_CSV" "$FINAL_RESULTS"

# Function to wait for vLLM to fully load the model
wait_for_vllm() {
    echo "Waiting for vLLM to load the model (Health Check)..."
    local url="http://localhost:8000/health"
    local retries=0
    local max_retries=90 # Wait up to 15 minutes (90 * 10s) for large models

    until curl -s -f "$url" > /dev/null; do
        sleep 10
        ((retries++))
        if [ $retries -ge $max_retries ]; then
            echo "Error: vLLM failed to become ready after 15 minutes."
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

    # 1. Generate a sanitized name for the column (no / or -)
    # Using underscores to match your required header format
# This is what I used in the updated script I gave you
    SAFE_NAME=$(echo "$MODEL_ID" | sed 's/[\/\.-]/_/g')
    COL_NAME="output_${SAFE_NAME}"

    # 2. Overwrite .env file dynamically for Docker Compose
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

    # 5. Run the translation script
    # We use FINAL_RESULTS as both input and output to append columns
    echo "Running translation script for column: $COL_NAME"

    # We call the script directly or via make.
    # Passing the same file to input and output allows the Python script to update it.
    python3 translate_fortran.py "$FINAL_RESULTS" "$FINAL_RESULTS" \
        --legacy-col "legacy_code" \
        --translated-col "$COL_NAME"

    echo "Finished $MODEL_ID. Updated $FINAL_RESULTS"

    # Optional: Clean up docker logs/cache if disk space is an issue
    # docker system prune -f
done

echo "========================================================"
echo "All experiments complete."
echo "Final consolidated results: $FINAL_RESULTS"
echo "========================================================"
