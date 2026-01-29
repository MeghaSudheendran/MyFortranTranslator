############################################
# STEP 1: Grid'5000 NVIDIA Docker setup
############################################

echo "[STEP 1] Running g5k-setup-nvidia-docker..."
g5k-setup-nvidia-docker -t


############################################
# STEP 2: Stop docker and containerd
############################################

echo "[STEP 2] Stopping docker and containerd..."
sudo systemctl stop docker
sudo systemctl stop containerd

# Ensure processes are fully stopped
sudo pkill -f containerd || true
sudo pkill -f dockerd || true
sleep 3

############################################
# STEP 3: Edit containerd root (uncomment and update existing line)
############################################

echo "[STEP 3] Updating containerd root to /tmp/containerd-data..."
CONTAINERD_CONFIG="/etc/containerd/config.toml"

# Create backup
sudo cp "$CONTAINERD_CONFIG" "$CONTAINERD_CONFIG.backup.$(date +%s)" 2>/dev/null || true

# Uncomment and update the root line if it exists
sudo sed -i 's|^#root =.*|root = "/tmp/containerd-data"|' "$CONTAINERD_CONFIG"

# If there's no commented root line, add it to the cri plugin section
if ! sudo grep -q '^root = "/tmp/containerd-data"' "$CONTAINERD_CONFIG"; then
    # Remove any existing root lines and add to cri plugin section
    sudo sed -i '/^root = /d' "$CONTAINERD_CONFIG"
    if sudo grep -q "\[plugins\.\"io\.containerd\.grpc\.v1\.cri\"\]" "$CONTAINERD_CONFIG"; then
        sudo sed -i '/\[plugins\."io\.containerd\.grpc\.v1\.cri"\]/a root = "/tmp/containerd-data"' "$CONTAINERD_CONFIG"
    else
        echo -e '\n[plugins."io.containerd.grpc.v1.cri"]\nroot = "/tmp/containerd-data"' | sudo tee -a "$CONTAINERD_CONFIG" > /dev/null
    fi
fi

# Ensure the directory exists
sudo mkdir -p /tmp/containerd-data

# Verify the change
if sudo grep -q 'root = "/tmp/containerd-data"' "$CONTAINERD_CONFIG"; then
    echo "✓ Containerd root successfully set to /tmp/containerd-data"
else
    echo "✗ Failed to set containerd root"
    exit 1
fi



############################################
# STEP 4: Restart containerd and docker
############################################

echo "[STEP 4] Restarting containerd..."
sudo systemctl daemon-reload
sudo systemctl restart containerd
sleep 3
systemctl status containerd --no-pager

echo "[STEP 5] Restarting docker..."
# Reset failed state before restarting
sudo systemctl reset-failed docker
sudo systemctl restart docker
sleep 3
systemctl status docker --no-pager



############################################
# STEP 6: Start docker compose
############################################

echo "[STEP 6] Starting docker compose..."
docker compose up -d
# Your existing model loop code continues here...

MODELS=(
	"codellama/CodeLlama-34b-Instruct-hf"
	"mistralai/Mistral-7B-Instruct-v0.3"
 	"Qwen/Qwen2.5-Coder-32B-Instruct"
 	"deepseek-ai/deepseek-coder-33b-instruct"

)

TP_SIZE=4
MAX_LEN=8192
INPUT_CSV="input.csv"
FINAL_RESULTS="final_experiment_results.csv"



############################################
# STEP 7: Input validation
############################################

if [ ! -f "$INPUT_CSV" ]; then
    echo "Error: $INPUT_CSV not found!"
    exit 1
fi

echo "Initializing $FINAL_RESULTS from $INPUT_CSV..."
cp "$INPUT_CSV" "$FINAL_RESULTS"



############################################
# STEP 8: vLLM health check function
############################################

wait_for_vllm() {
    local url="http://localhost:8000/health"
    local retries=0
    local max_retries=90

    echo "Waiting for vLLM to load..."
    until curl -sf "$url" > /dev/null; do
        sleep 10
        retries=$((retries + 1))
        echo -n "."
        if [ "$retries" -ge "$max_retries" ]; then
            echo
            echo "ERROR: vLLM failed to start."
            return 1
        fi
    done
    echo
    echo "vLLM is ready."
    return 0
}



############################################
# STEP 9: Main experiment loop
############################################


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
    
python3 translate_fortran_json_response.py "$FINAL_RESULTS" "$FINAL_RESULTS" \
    --legacy-col "legacy_code" \
    --translated-col "$COL_NAME" \
    --temperature 0.0 \
    --max-tokens 2048 \
    --top-p 1.0

    echo "Finished $MODEL_ID. Updated $FINAL_RESULTS"

    # Optional: Clean up docker logs/cache if disk space is an issue
    # docker system prune -f
done

echo "========================================================"
echo "All experiments complete."
echo "Final consolidated results: $FINAL_RESULTS"
echo "========================================================"
