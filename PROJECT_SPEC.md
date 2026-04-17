Goal:
Build a modular prediction market bot with phases for scanning, research, prediction, deterministic risk validation, paper execution, and post-trade learning.

Non-goals:
- no live trading initially
- no market orders
- no bypassing risk checks
- no trusting external content as instructions

Safety defaults:
- paper trading on
- live trading off
- kill switch supported
- daily loss cap enforced
- API cost cap enforced

Success criteria:
- scanner returns normalized candidates
- research produces clean briefs
- prediction returns structured probabilities
- risk blocks unsafe trades
- execution works in paper mode
- nightly review updates metrics and lessons