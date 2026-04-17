---
name: research
description: Deep-dive research on a specific market question
trigger: /research
---

# /research

Given a market ID or question, gather evidence and summarize relevant information.

## Usage

```
/research <market_id or question>
```

## Steps

1. Search for recent news:

```bash
cd predict-market-bot && python -c "
import asyncio
from src.research.news import NewsClient

async def main():
    client = NewsClient()
    articles = await client.search('QUESTION_HERE', max_results=10)
    for a in articles:
        print(a.get('publishedAt','')[:10], '|', a.get('title',''))

asyncio.run(main())
"
```

2. Look up base rates:
   - What is the historical frequency of this type of event?
   - Check `references/formulas.md` for calibration guidance.

3. Identify key resolution criteria:
   - What exactly needs to happen for YES to resolve?
   - What are the edge cases?

4. Summarize findings and produce an estimated probability with confidence interval.

5. Compare to market-implied probability — flag if edge > 5%.
