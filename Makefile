# Makefile

# --- Configuration Variables ---
PYTHON := python3
PIP := $(PYTHON) -m pip
VENV_NAME := venv
VENV_BIN := $(VENV_NAME)/bin
ACTIVATE := $(VENV_BIN)/activate
REQUIREMENTS := requirements.txt
SCRIPT := translate_fortran.py
INPUT_CSV ?= input.csv
OUTPUT_CSV ?= output.csv
LEGACY_COL ?= legacy_code
TRANSLATED_COL ?= mistral_translated_code
EXAMPLE_ENV := example.env # Name of the example file
ENV_FILE := .env          # Name of the actual config file

# --- Default target ---
help:
    @echo "Available targets:"
    @echo "  setup    - Create virtual environment and install dependencies"
    @echo "  check-env - Check if .env file exists, copy example.env if it doesn't"
    @echo "  run      - Run the translation script (requires setup and .env)"
    @echo "  clean    - Remove virtual environment"
    @echo ""
    @echo "Example usage:"
    @echo "  make check-env # Do this first to set up .env"
    @echo "  make setup"
    @echo "  make run INPUT_CSV=my_input.csv OUTPUT_CSV=my_output.csv"

# --- Check Environment target ---
check-env:
    @echo "Checking for $(ENV_FILE)..."
    @if [ ! -f $(ENV_FILE) ]; then \
        echo "$(ENV_FILE) not found. Copying $(EXAMPLE_ENV) to $(ENV_FILE)."; \
        if [ -f $(EXAMPLE_ENV) ]; then \
            cp $(EXAMPLE_ENV) $(ENV_FILE); \
            echo "Copied $(EXAMPLE_ENV) to $(ENV_FILE). Please review and edit $(ENV_FILE) if necessary."; \
        else \
            echo "Warning: $(EXAMPLE_ENV) also not found. You may need to create $(ENV_FILE) manually."; \
        fi; \
    else \
        echo "$(ENV_FILE) found."; \
    fi

# --- Setup target ---
setup: check-env # Make check-env a dependency
    @echo "Checking for Python..."
    @which $(PYTHON) || (echo "Error: $(PYTHON) not found."; exit 1)
    @echo "Creating virtual environment: $(VENV_NAME)"
    $(PYTHON) -m venv $(VENV_NAME)
    @echo "Activating virtual environment and installing dependencies from $(REQUIREMENTS)..."
    bash -c "source $(ACTIVATE) && $(PIP) install --upgrade pip && $(PIP) install -r $(REQUIREMENTS)"
    @echo "Setup complete. Virtual environment '$(VENV_NAME)' created and dependencies installed."

# --- Run target ---
run: setup # Ensure setup (and check-env via setup's dependency) runs first
    @echo "Checking if virtual environment '$(VENV_NAME)' exists..."
    @test -d $(VENV_NAME) || (echo "Error: Virtual environment '$(VENV_NAME)' not found. Run 'make setup' first."; exit 1)
    # Optional: Load the environment variables from .env before running the script
    @echo "Activating virtual environment and running $(SCRIPT)..."
    @echo "Input CSV: $(INPUT_CSV)"
    @echo "Output CSV: $(OUTPUT_CSV)"
    @echo "Legacy Column: $(LEGACY_COL)"
    @echo "Translated Column: $(TRANSLATED_COL)"
    # Use 'set -a' to export all variables sourced from .env, then run the script within that environment
    bash -c "set -a; source $(ENV_FILE) 2>/dev/null || true; set +a; source $(ACTIVATE); python $(SCRIPT) '$(INPUT_CSV)' '$(OUTPUT_CSV)' --legacy-col '$(LEGACY_COL)' --translated-col '$(TRANSLATED_COL)'"
    @echo "Run complete. Output saved to $(OUTPUT_CSV)"

# --- Clean target ---
clean:
    @echo "Removing virtual environment: $(VENV_NAME)"
    rm -rf $(VENV_NAME)
    @echo "Clean complete."

# --- Phony targets (targets that don't represent files) ---
.PHONY: help setup check-env run clean