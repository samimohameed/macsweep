#!/bin/bash
# Seed "good first issue" tasks after publishing. Run once:
#   brew install gh && gh auth login && bash docs/launch/seed-issues.sh
set -euo pipefail
REPO="samimohameed/macsweep"

gh label create "new-target" --repo "$REPO" --color 0e8a16 --description "Proposal for a new cleanup target" 2>/dev/null || true

new_target_issue() {
  gh issue create --repo "$REPO" --label "good first issue,new-target" --title "$1" --body "$2"
}

new_target_issue "Target: Docker build cache" \
"Add a \`CleanupTarget\` for Docker Desktop's build/image cache metadata under \`~/Library/Containers/com.docker.docker\` is protected (Containers is blocklisted), but \`~/.docker\` scratch data such as \`~/.docker/buildx\` cache dirs is fair game. Investigate what is safely regenerable, propose a root + \`min_age_days\`, and add it to \`default_targets()\` in \`macsweep/infrastructure/macos_targets.py\`. See CONTRIBUTING.md for the safety rules."

new_target_issue "Target: Gradle cache (~/.gradle/caches)" \
"Add a \`CleanupTarget\` for \`~/.gradle/caches\` — downloaded dependencies and build caches that Gradle re-fetches on demand. Suggested: \`Risk.SAFE\`, \`min_age_days=30\`. Add to \`default_targets()\` in \`macsweep/infrastructure/macos_targets.py\` and verify with \`python3 -m macsweep scan --only gradle-cache -v\`."

new_target_issue "Target: CocoaPods cache (~/Library/Caches/CocoaPods)" \
"Add a \`CleanupTarget\` for \`~/Library/Caches/CocoaPods\` — pod download cache, re-fetched by \`pod install\`. Suggested: \`Risk.SAFE\`, \`min_age_days=14\`. Note this lives under the existing user-caches root; decide whether a dedicated target (own age policy) is worth it and document the reasoning in the PR."

new_target_issue "Target: Cargo registry cache (~/.cargo/registry)" \
"Add a \`CleanupTarget\` for \`~/.cargo/registry/cache\` (crate downloads, re-fetched by cargo on demand). Suggested: \`Risk.SAFE\`, \`min_age_days=30\`. Be careful to include only \`registry/cache\`, not \`registry/index\` or installed binaries in \`~/.cargo/bin\`."

new_target_issue "Target: Go module cache (~/Library/Caches/go-build and GOMODCACHE)" \
"Add targets for Go's build cache (\`~/Library/Caches/go-build\`) and optionally the module download cache. The build cache is \`Risk.SAFE\` (regenerated on build). Suggested \`min_age_days=14\`."

new_target_issue "Target: old iOS Simulator runtimes" \
"Investigate a target for unused simulator data under \`~/Library/Developer/CoreSimulator/Caches\`. Full device deletion is out of scope (needs \`xcrun simctl\`), but the dyld caches there are regenerable. Propose a safe root + age policy."

new_target_issue "Target: Playwright/Puppeteer browser downloads" \
"Add a \`CleanupTarget\` for \`~/Library/Caches/ms-playwright\` (Playwright's downloaded browser builds; re-downloaded by \`npx playwright install\`). Suggested: \`Risk.MODERATE\` (large re-download), \`min_age_days=60\`."

new_target_issue "GUI: 'Select none / invert' controls above the results tree" \
"Small PySide6 task in \`macsweep/presentation/gui/main_window.py\`: add Select all / Select none buttons above the tree so users can start from zero and opt items in. No changes outside the presentation layer."

new_target_issue "GUI: remember window size and column widths between launches" \
"Use \`QSettings\` in \`macsweep/presentation/gui/main_window.py\` to persist window geometry and tree column widths. Presentation-layer only."

new_target_issue "CLI: --json output for scan reports" \
"Add \`macsweep scan --json\` printing the ScanReport as JSON (path, target_id, size_bytes, age_days). Useful for scripting and for future tooling. Presentation-layer change in \`macsweep/presentation/cli.py\` only."

echo "All seed issues created."
