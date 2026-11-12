#!/bin/bash

# Run ToolEmu for IoT category cases.
# Usage: ./run_iot.sh [--verified] [--trunc-num NUM]

VERIFIED_FLAG=""
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
        *)
            echo "Unknown option: $1"
            echo "Usage: ./run_iot.sh [--verified] [--trunc-num NUM]"
            exit 1
            ;;
    esac
done

python scripts/run.py \
    --input-path assets/category/iot_cases_formal.json \
    --trunc-num "$TRUNC_NUM" \
    --auto \
    --agent-model-name gpt-4o-mini-2024-07-18 \
    --agent-type helpful_ss \
    --simulator-type adv_thought \
    $VERIFIED_FLAG
