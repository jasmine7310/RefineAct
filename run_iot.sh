#!/bin/bash

# Run ToolEmu for IoT category cases.
# Usage: ./run_iot.sh [--verified] [--trunc-num NUM] [--model NAME]
# --model sets the agent, simulator and evaluator model, e.g. claude-opus-5-5.

VERIFIED_FLAG=""
MODEL="gpt-4o-mini-2024-07-18"
TRUNC_NUM="25"

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
            MODEL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./run_iot.sh [--verified] [--trunc-num NUM] [--model NAME]"
            exit 1
            ;;
    esac
done

python scripts/run.py \
    --input-path assets/category/iot_cases_formal.json \
    --trunc-num "$TRUNC_NUM" \
    --auto \
    --agent-model-name "$MODEL" \
    --simulator-model-name "$MODEL" \
    --evaluator-model-name "$MODEL" \
    --agent-type helpful_ss \
    --simulator-type adv_thought \
    $VERIFIED_FLAG
