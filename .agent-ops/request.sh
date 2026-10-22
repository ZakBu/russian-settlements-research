set -e
echo hello
git log -1 --format=%H
df -h /
gh api repos/$REPO --jq .size
