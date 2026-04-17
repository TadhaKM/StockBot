# Failure Log

Track trades where our prediction was significantly wrong, and what we learned.
Appended by `scripts/nightly_review.py` automatically.

---

## Template

```
### YYYY-MM-DD | Market: <question>
- **Our probability**: X%
- **Market price**: Y%
- **Edge claimed**: +Z%
- **Outcome**: WIN / LOSS
- **PnL**: $...
- **Root cause**: (overconfident on news signal / ignored base rate / resolution edge case / ...)
- **Fix**: (adjust sentiment weight / add base-rate anchor / tighten edge threshold / ...)
```

---

<!-- Nightly review script appends entries below this line -->
