# Platform Reference

## Polymarket

- **Type**: Decentralized (Polygon/MATIC, USDC collateral)
- **Markets**: US politics, crypto, sports, world events
- **API**: CLOB REST API + WebSocket
- **Auth**: L1 (API key) or L2 (private key signing)
- **Docs**: https://docs.polymarket.com
- **Min trade**: ~$1 USDC
- **Fees**: ~2% maker/taker (varies)

### Key endpoints
| Endpoint | Purpose |
|----------|---------|
| `GET /markets` | List active markets |
| `GET /book?token_id=...` | Order book for a token |
| `POST /order` | Place limit order |
| `DELETE /order/{id}` | Cancel order |
| `GET /positions` | Open positions |

### Notes
- Each outcome is an ERC-1155 token (YES/NO)
- Resolution via UMA optimistic oracle
- Use `py-clob-client` (official Python SDK) for auth

---

## Kalshi

- **Type**: Centralized, CFTC-regulated
- **Markets**: Economics, politics, weather, sports
- **API**: REST v2 + WebSocket
- **Auth**: HMAC-SHA256 signature on each request
- **Docs**: https://trading-api.kalshi.com/trade-api/v2/docs
- **Min trade**: $0.01 per contract
- **Fees**: 1–7% of winnings (varies by market)

### Key endpoints
| Endpoint | Purpose |
|----------|---------|
| `GET /markets` | List markets |
| `GET /markets/{ticker}/orderbook` | Order book |
| `POST /portfolio/orders` | Place order |
| `DELETE /portfolio/orders/{id}` | Cancel order |
| `GET /portfolio/positions` | Open positions |

### Notes
- Contracts pay $1 on YES resolution, $0 on NO
- Demo environment available: `demo-api.kalshi.co`
- Use demo for all testing before going live

---

## Comparison

| Feature | Polymarket | Kalshi |
|---------|-----------|--------|
| Regulation | Unregulated (offshore) | CFTC-regulated |
| Collateral | USDC (crypto) | USD (bank) |
| Withdrawal | Crypto wallet | ACH / wire |
| US residents | Geofenced (VPN risk) | Yes |
| Market types | Broader | More limited |
| Liquidity | Higher on top markets | Lower overall |
