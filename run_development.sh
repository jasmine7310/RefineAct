#!/bin/bash

# Run ToolEmu for development category cases.
# Usage: ./run_development.sh [--verified] [--trunc-num NUM] [--model NAME]
# --model sets the agent, simulator and evaluator model, e.g. claude-opus-5-5.
# Without it, models come from the REFINEACT_* environment variables (see .env.example).

VERIFIED_FLAG=""
MODEL_ARGS=()
TRUNC_NUM="31"

while [[ $# -gt 0 ]]; do
    case $1 in
        --verified)
            VERIFIED_FLAG="--verified-agent"
            shift
            ;;
        --trunc-num)
            TRUNC_NUM="$2"
            shift 2
            ;;
        --model)
            MODEL_ARGS=(--agent-model-name "$2" --simulator-model-name "$2" --evaluator-model-name "$2")
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./run_development.sh [--verified] [--trunc-num NUM] [--model NAME]"
            exit 1
            ;;
    esac
done

python scripts/run.py \
    --input-path assets/category/development_cases_formal.json \
    --trunc-num "$TRUNC_NUM" \
    --auto \
    "${MODEL_ARGS[@]}" \
    --agent-type helpful_ss \
    --simulator-type adv_thought \
    $VERIFIED_FLAG
