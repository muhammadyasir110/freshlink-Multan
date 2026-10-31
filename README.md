# FreshLink Multan: Urban Food Desert Supply Chain Matchmaker

**Hacktoberfest 2026 Hack Day, Multan · Challenge 3**
Scenario: Predictive Agricultural Logistics & Hyper-Local Marketplace

## 🌐 Live demo (no setup, no API key needed)

### 👉 https://boy8p4t5ek3sd6nmrowaxx.streamlit.app

The Gemini API key is configured on the server backend (Streamlit Cloud Secrets), so judges only need to open the link.
*(If the app is asleep, click "Yes, get this app back up" and wait about 30 seconds.)*

---

## ✅ Mandatory evaluation deliverables

| # | Requirement from the brief | Where to find it |
|---|---|---|
| 1 | Public GitHub repository with an explicit open-source license | This repo · [`LICENSE`](LICENSE) (MIT) |
| 2 | Live code demo of the Gemma model using the Gemini API to analyse visual assets or text logs | Live demo → **Tab 1** (photo analysis) and **Tab 3** (text bargaining) · code: [`gemma_agent.py`](gemma_agent.py) |
| 3 | Onchain validation interactions visible in the codebase or a live terminal demo | Code: [`solana_registry.py`](solana_registry.py) · UI: Live demo → **Tab 4** · terminal: `python cli_demo.py` |
| 4 | Clear README annotations of the exact prompts used with GitHub Copilot to solve a development blocker | [Section below](#github-copilot-exact-prompts-used) |

## 🧪 How to test in 2 minutes
1. Open the live demo link.
2. **Tab 1:** pick a farm and upload any photo of a fruit or vegetable, then click **Grade with Gemma 4**. Gemma 4 checks quality and writes the listing.
3. **Tab 2:** choose a delivery day to see farm-to-store matches, the map, and the deficit-by-day chart.
4. **Tab 3:** type an offer as the store owner, e.g. `40 kg chahiye, Rs 80 per kg?`, and the Gemma 4 seller agent bargains back.
5. **Tab 4:** register a buyer or seller agent and record feedback after a deal.

---

## Track integration (as specified in the brief)

### Google Gemma 4 Core: localized community assistant
*Brief: accepts images of produce from farms to verify quality, automatically writes descriptions, and handles conversational text bargaining.*

All Gemma code is in [`gemma_agent.py`](gemma_agent.py), and every call goes through one function:
```python
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")

def _call_gemma(contents) -> str:
    resp = _get_client().models.generate_content(model=GEMMA_MODEL, contents=contents)
    return resp.text
```
| Function | Purpose | Gemini API input |
|---|---|---|
| `grade_produce()` | verify quality and write the listing description | image (`types.Part.from_bytes`) + prompt → JSON (grade, freshness, shelf life, defects, description, price) |
| `bargain()` | conversational text bargaining | chat history + seller's ask and floor price → reply, ending in `DEAL: <price> PKR/kg x <qty> kg` |

### Snowflake CoCo Data: deficit-day prediction
*Brief: query localized consumer purchasing or census datasets; use CoCo to structure queries predicting which days of the week store neighbourhoods face the highest fresh-food deficits.*

- [`snowflake/coco_queries.sql`](snowflake/coco_queries.sql): the deficit index per area per weekday, plus the worst day per area.
- The query output is stored in [`data/deficit_by_day.csv`](data/deficit_by_day.csv) and used by the matcher and the Tab 2 chart.

### Solana Agent Registry: verifiable identity and reputation
*Brief: give buyer and seller agents verifiable onchain identities; record portable reputation scores and transaction feedback on Solana.*

- Each buyer (store) and seller (farm) agent has its own Solana keypair, which is its identity.
- `register_agent()` writes `FRESHLINK|REGISTER|<id>|<role>|<name>|<pubkey>` onchain on devnet, via the SPL Memo program.
- `record_feedback()` writes `FRESHLINK|FEEDBACK|<from>|<to>|<stars>|<deal>` onchain.
- `reputation_scores()` rebuilds the reputation from the feedback records and feeds it into the match score.

**Note:** The public devnet faucet blocks airdrops to cloud-hosted servers, so on the hosted demo Tab 4 falls back to a clearly labelled **SIMULATED** hash-chained ledger. With a funded devnet wallet (`SOLANA_PAYER_KEY`), the same code sends real devnet transactions and returns Solana Explorer links. All onchain logic is in [`solana_registry.py`](solana_registry.py).

### GitHub Copilot Acceleration
*Brief: spatial map route calculation boilerplate, mock inventory arrays, localized data pipelines.*
- Route calculation: `haversine_km()` and `delivery_route()` in [`matcher.py`](matcher.py)
- Mock inventory: [`data/farms.csv`](data/farms.csv), [`data/stores.csv`](data/stores.csv)
- Data pipeline: `matcher.load()` / `match()`

## GitHub Copilot: exact prompts used
| # | Development blocker | Exact prompt typed into Copilot | Result in code |
|---|---|---|---|
| 1 | Distance between farms and stores without a maps API | `write a python haversine function returning km between two lat/lon points` | `haversine_km()` in matcher.py |

---

## Run locally (optional)
```bash
pip install -r requirements.txt
# put GEMINI_API_KEY = "..." in .streamlit/secrets.toml  (git-ignored)
streamlit run app.py          # web app
python cli_demo.py photo.jpg  # terminal demo
```

## Project structure
```
app.py                  Streamlit app (4 tabs)
gemma_agent.py          Gemma 4 via Gemini API
matcher.py              matching + route calculation
solana_registry.py      onchain identities, feedback, reputation
cli_demo.py             terminal demo
snowflake/coco_queries.sql
data/                   mock inventory + deficit-by-day
```

## License
[MIT](LICENSE)
