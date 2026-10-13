#!/bin/zsh
# Keeps the InternPilot worker running in the background (restarts it if it crashes, starts at login).
# Stop & remove:
#   launchctl unload ~/Library/LaunchAgents/com.internpilot.worker.plist && rm ~/Library/LaunchAgents/com.internpilot.worker.plist
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DIR/logs"
PLIST=~/Library/LaunchAgents/com.internpilot.worker.plist
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.internpilot.worker</string>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/python</string><string>-m</string><string>worker.agent</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$DIR/logs/worker.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/worker.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Logs: tail -f $DIR/logs/worker.log"
