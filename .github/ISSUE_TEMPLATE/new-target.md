---
name: New cleanup target
about: Propose a new cache/log location for MacSweep to clean
title: "Target: <tool or app name>"
labels: ["new-target", "good first issue"]
---

**Location (absolute path, user scope only):**
e.g. `~/Library/Caches/SomeTool`

**What lives there and why is it safe to remove?**

**Is it regenerated automatically?** (yes → `Risk.SAFE`, costs a re-download/re-index → `Risk.MODERATE`, could surprise users → `Risk.OPT_IN`)

**Suggested minimum age (days):**
