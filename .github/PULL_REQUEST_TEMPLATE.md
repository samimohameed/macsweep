# What does this PR do?

## Safety checklist (required)

- [ ] `SafetyPolicy` (blocklist, symlink, age checks) is untouched or strictly stronger
- [ ] All removal still goes through `CleanUseCase` only
- [ ] New locations are whitelist `CleanupTarget` entries under user scope (no `sudo`)
- [ ] `python3 -m pytest tests/ -v` passes

## How I verified it

<!-- e.g. output of `python3 -m maccleaner scan --only my-target -v` -->
