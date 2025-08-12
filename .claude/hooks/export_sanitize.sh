#!/bin/bash
# Claude Code Export Sanitization Hook
# Automatically sanitize sensitive information from exported conversations

EXPORT_FILE="$1"
if [[ -z "$EXPORT_FILE" || ! -f "$EXPORT_FILE" ]]; then
    echo "Usage: $0 <export_file>"
    exit 1
fi

echo "🧹 Sanitizing sensitive information from export file..."

# Create backup
cp "$EXPORT_FILE" "${EXPORT_FILE}.backup"

# Sanitize telegram bot tokens
sed -i 's/bot[0-9]\{8,\}:AAH[A-Za-z0-9_-]\{35\}/bot[REDACTED]:AAH[REDACTED]/g' "$EXPORT_FILE"

# Sanitize general HTTP tokens in telegram.org URLs
sed -i 's|telegram\.org/bot[0-9]\{8,\}:[A-Za-z0-9_-]\{35\}|telegram.org/bot[REDACTED]:[REDACTED]|g' "$EXPORT_FILE"

# Sanitize any standalone API keys (common patterns)
sed -i 's/AAH[A-Za-z0-9_-]\{35\}/AAH[REDACTED]/g' "$EXPORT_FILE"

# Sanitize notion API tokens
sed -i 's/secret_[A-Za-z0-9]\{43\}/secret_[REDACTED]/g' "$EXPORT_FILE"

# Sanitize GitHub tokens
sed -i 's/ghp_[A-Za-z0-9]\{36\}/ghp_[REDACTED]/g' "$EXPORT_FILE"
sed -i 's/github_pat_[A-Za-z0-9_]\{82\}/github_pat_[REDACTED]/g' "$EXPORT_FILE"

# Sanitize IP addresses (optional - uncomment if needed)
# sed -i 's/\b\([0-9]\{1,3\}\.\)\{3\}[0-9]\{1,3\}\b/[IP_REDACTED]/g' "$EXPORT_FILE"

# Count sanitized items
TELEGRAM_COUNT=$(grep -o "bot\[REDACTED\]" "$EXPORT_FILE" | wc -l)
NOTION_COUNT=$(grep -o "secret_\[REDACTED\]" "$EXPORT_FILE" | wc -l)  
GITHUB_COUNT=$(grep -o "gh.*_\[REDACTED\]" "$EXPORT_FILE" | wc -l)

echo "✅ Sanitization complete:"
echo "   🔒 Telegram tokens: $TELEGRAM_COUNT sanitized"
echo "   🔒 Notion tokens: $NOTION_COUNT sanitized"  
echo "   🔒 GitHub tokens: $GITHUB_COUNT sanitized"
echo "   📄 Backup saved as: ${EXPORT_FILE}.backup"

if [[ $((TELEGRAM_COUNT + NOTION_COUNT + GITHUB_COUNT)) -gt 0 ]]; then
    echo "⚠️  Sensitive data was found and sanitized!"
else
    echo "✨ No sensitive data detected in export file"
fi