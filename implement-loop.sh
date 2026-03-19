# DealRadar MVP Implementation Loop
# This script iterates through all 14 implementation tasks until completion

set -e

PROJECT_DIR="C:\Users\StevenDesk\mywork\dealradar"
PLAN_FILE="$PROJECT_DIR/docs/superpowers/plans/2026-03-19-dealradar-implementation-plan.md"
SPEC_FILE="$PROJECT_DIR/docs/superpowers/specs/2026-03-19-dealradar-mvp-design.md"

cd "$PROJECT_DIR"

echo "============================================"
echo "DealRadar MVP Implementation Loop"
echo "============================================"
echo ""

# Check prerequisites
if [ ! -f "$PLAN_FILE" ]; then
    echo "ERROR: Plan file not found at $PLAN_FILE"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env"
    exit 1
fi

# Export env vars from .env
export $(grep -v '^#' .env | grep -v '^$' | xargs) > /dev/null 2>&1 || true

# Task list
TASKS=(
    "Task 1: Project Scaffolding"
    "Task 2: Jina Client"
    "Task 3: Apify Client"
    "Task 4: Company Extractor"
    "Task 5: Harvester Pipeline"
    "Task 6: AI Models Chain"
    "Task 7: Signal Detection & Scoring"
    "Task 8: Funding Clock"
    "Task 9: Summarizer"
    "Task 10: Reasoner Pipeline"
    "Task 11: Notion Client"
    "Task 12: Weekly Digest"
    "Task 13: End-to-End Integration"
    "Task 14: CLAUDE.md"
)

echo "Found ${#TASKS[@]} tasks to implement"
echo ""

# Implementation loop
for task in "${TASKS[@]}"; do
    echo "============================================"
    echo "NEXT TASK: $task"
    echo "============================================"
    echo ""
    read -p "Press ENTER when '$task' is complete, or 'skip' to skip: " response
    if [ "$response" != "skip" ]; then
        echo "Proceeding..."
    fi
    echo ""
done

echo ""
echo "All tasks completed!"
echo ""
echo "Final steps:"
echo "1. cd $PROJECT_DIR"
echo "2. pip install -r requirements.txt"
echo "3. Set up Notion database"
echo "4. python run.py --phase=all"
