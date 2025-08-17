#!/bin/bash
# Script to set up automated telemetry cleanup via cron

set -e

# Get the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLEANUP_SCRIPT="$PROJECT_DIR/utils/cleanup_telemetry.py"
LOG_FILE="$PROJECT_DIR/logs/telemetry_cleanup.log"

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_DIR/logs"

# Check if cleanup script exists
if [ ! -f "$CLEANUP_SCRIPT" ]; then
    echo "Error: Cleanup script not found at $CLEANUP_SCRIPT"
    exit 1
fi

# Make the cleanup script executable
chmod +x "$CLEANUP_SCRIPT"

# Create the cron job entry
# Run cleanup every day at 2:00 AM
CRON_JOB="0 2 * * * cd $PROJECT_DIR && $CLEANUP_SCRIPT --telemetry-max-age 30 --telemetry-max-records 100000 --mavlink-max-age 30 --mavlink-max-records 100000 >> $LOG_FILE 2>&1"

echo "Setting up cron job for telemetry cleanup..."
echo "Cron job will run daily at 2:00 AM"
echo "Logs will be written to: $LOG_FILE"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "cleanup_telemetry.py"; then
    echo "Warning: A cron job for cleanup_telemetry.py already exists."
    echo "Current cron jobs:"
    crontab -l 2>/dev/null | grep "cleanup_telemetry.py" || true
    echo ""
    read -p "Do you want to replace the existing cron job? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cron job setup cancelled."
        exit 0
    fi
    
    # Remove existing cron job
    (crontab -l 2>/dev/null | grep -v "cleanup_telemetry.py") | crontab -
fi

# Add the new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "Cron job has been set up successfully!"
echo ""
echo "To view current cron jobs:"
echo "  crontab -l"
echo ""
echo "To remove the cron job:"
echo "  crontab -r"
echo ""
echo "To edit cron jobs manually:"
echo "  crontab -e"
echo ""
echo "To test the cleanup script manually:"
echo "  cd $PROJECT_DIR"
echo "  python3 $CLEANUP_SCRIPT --dry-run"
echo ""
echo "To view cleanup logs:"
echo "  tail -f $LOG_FILE"


