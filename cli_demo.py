"""Terminal demo for judges: python cli_demo.py [path/to/produce.jpg]

Shows the full flow end-to-end: Gemma 4 grading -> matching -> Gemma bargaining
-> Solana identity registration -> onchain feedback -> reputation.
"""
import sys

import gemma_agent as gemma
import matcher
import solana_registry as sol


def hr(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


hr("1) GEMMA 4 — produce quality check")
if len(sys.argv) > 1:
    path = sys.argv[1]
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    g = gemma.grade_produce(open(path, "rb").read(), mime)
else:
    print("(no image given -> using offline sample)")
    g = gemma._offline_grade()
for k, v in g.items():
    print(f"  {k:28s} {v}")

hr("2) MATCHING — Friday (highest food-deficit day)")
df = matcher.match("Fri", sol.reputation_scores())
print(df[["score", "produce", "farm", "store", "km", "qty_kg"]].head(6).to_string(index=False))
best = df.iloc[0]

hr(f"3) GEMMA 4 — bargaining: {best.store} ⇄ {best.farm}")
ctx = dict(farm=best.farm, produce=best.produce, qty=best.qty_kg, grade=g["quality_grade"],
           shelf=g["estimated_shelf_life_days"], ask=best.farm_price, floor=int(best.farm_price * 0.85))
hist = [{"role": "user", "text": f"Assalam o alaikum, {best.qty_kg} kg {best.produce} chahiye, "
                                 f"Rs {int(best.farm_price*0.8)} kilo de do?"}]
print("  Store:", hist[0]["text"])
reply = gemma.bargain(hist, ctx)
print("  Farm agent:", reply)
hist += [{"role": "model", "text": reply},
         {"role": "user", "text": f"Chalo Rs {int(best.farm_price*0.9)} final karo."}]
print("  Store:", hist[-1]["text"])
reply = gemma.bargain(hist, ctx)
print("  Farm agent:", reply)

hr("4) SOLANA — register buyer & seller agents (devnet)")
for aid, role, name in [(best.farm_id, "seller", best.farm), (best.store_id, "buyer", best.store)]:
    rec = sol.register_agent(aid, role, name)
    print(f"  {aid} pubkey={rec['pubkey']}")
    print(f"     tx: {rec['url'] or rec['sig']}  onchain={rec['onchain']}")
    if not rec["onchain"]:
        print(f"     (fallback reason: {rec.get('error')})")

hr("5) SOLANA — store leaves 5★ feedback for farm")
rec = sol.record_feedback(best.store_id, best.farm_id, 5, f"{best.produce} {best.qty_kg}kg")
print(f"  tx: {rec['url'] or rec['sig']}  onchain={rec['onchain']}")

hr("6) PORTABLE REPUTATION (rebuilt from ledger)")
print(" ", sol.reputation_scores())
