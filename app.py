"""FreshLink Multan — Urban Food Desert Supply Chain Matchmaker (Streamlit UI).
Run:  streamlit run app.py
"""
import datetime as dt
import re

import pandas as pd
import pydeck as pdk
import streamlit as st

import gemma_agent as gemma
import matcher
import solana_registry as sol

st.set_page_config(page_title="FreshLink Multan", page_icon="🥬", layout="wide")

with st.sidebar:
    st.header("System status")
    st.write("Gemma 4:", f"🟢 live ({gemma.GEMMA_MODEL})" if gemma.gemma_available() else "🟡 offline mock")
    st.write("Solana:", "devnet")

st.title("🥬 FreshLink Multan")
st.caption("Urban Food Desert Supply Chain Matchmaker: connects urban farms' surplus produce with "
           "corner stores in food deserts. Gemma 4 · Snowflake CoCo · Solana · GitHub Copilot")

tab1, tab2, tab3, tab4 = st.tabs(["1 · Farmer: list produce", "2 · Store: find matches",
                                  "3 · Bargain (Gemma chat)", "4 · Trust: Solana reputation"])

farms, stores, deficit = matcher.load()

# ---------------- TAB 1: Gemma vision grading ----------------
with tab1:
    st.subheader("Upload a photo of your surplus — Gemma 4 verifies quality and writes the listing")
    farm_name = st.selectbox("Your farm", farms.name, key="farm_sel")
    img = st.file_uploader("Produce photo", type=["jpg", "jpeg", "png", "webp"])
    if img and st.button("🔍 Grade with Gemma 4", type="primary"):
        with st.spinner("Gemma 4 is inspecting the produce..."):
            try:
                res = gemma.grade_produce(img.getvalue(), img.type or "image/jpeg")
                st.session_state["grade"] = res
            except Exception as e:
                st.error(f"Gemma call failed: {e}")
    if img:
        st.image(img, width=320)
    if "grade" in st.session_state:
        g = st.session_state["grade"]
        a, b, c = st.columns(3)
        a.metric("Grade", g.get("quality_grade"))
        b.metric("Freshness", f"{g.get('freshness_score')}/100")
        c.metric("Shelf life", f"{g.get('estimated_shelf_life_days')} days")
        st.markdown(f"### {g.get('listing_title')}")
        st.write(g.get("listing_description"))
        st.write("**Defects:**", ", ".join(g.get("defects", [])) or "none")
        st.write(f"**Suggested price:** Rs {g.get('suggested_price_pkr_per_kg')}/kg")
        st.caption(f"source: {g.get('_source')}")

# ---------------- TAB 2: matching + map ----------------
with tab2:
    st.subheader("Hyper-local matches ranked by need, food-deficit day, distance, price and trust")
    today = dt.date.today().strftime("%a")
    day = st.select_slider("Delivery day", matcher.DAYS, value=today if today in matcher.DAYS else "Mon")
    prod = st.selectbox("Produce", ["All"] + sorted(farms.produce.unique()))
    df = matcher.match(day, sol.reputation_scores(), None if prod == "All" else prod)
    if df.empty:
        st.info("No matches for this filter.")
    else:
        st.dataframe(df[["score", "produce", "farm", "store", "store_area", "km", "deficit",
                         "qty_kg", "farm_price", "store_budget"]], width="stretch", hide_index=True)
        top = df.head(8)
        st.pydeck_chart(pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(latitude=30.20, longitude=71.47, zoom=10.5),
            layers=[
                pdk.Layer("ArcLayer", top, get_source_position="[f_lon, f_lat]",
                          get_target_position="[s_lon, s_lat]", get_source_color=[34, 139, 34],
                          get_target_color=[220, 90, 30], get_width=3, pickable=True),
                pdk.Layer("ScatterplotLayer", farms, get_position="[lon, lat]", get_radius=350,
                          get_fill_color=[34, 139, 34], pickable=True),
                pdk.Layer("ScatterplotLayer", stores, get_position="[lon, lat]", get_radius=350,
                          get_fill_color=[220, 90, 30], pickable=True),
            ],
            tooltip={"text": "{name}{farm} → {store}"},
        ))
        st.caption("🟢 farms · 🟠 corner stores · arcs = top matches")

        st.markdown("#### 🚚 Delivery route for one farm")
        fid = st.selectbox("Farm", df.farm_id.unique())
        sids = df[df.farm_id == fid].store_id.tolist()
        for i, (stop, km) in enumerate(matcher.delivery_route(fid, sids), 1):
            st.write(f"{i}. {stop} — {km} km cumulative")

    st.markdown("#### 📈 Fresh-food deficit by weekday (Snowflake CoCo query output)")
    st.bar_chart(deficit.T)
    st.caption("Highest-deficit day per area: " + ", ".join(
        f"{a}: **{deficit.loc[a].idxmax()}**" for a in deficit.index))

# ---------------- TAB 3: Gemma bargaining ----------------
with tab3:
    st.subheader("Store ⇄ Farm negotiation agent (Gemma 4)")
    df_all = matcher.match(day, sol.reputation_scores())
    if df_all.empty:
        st.info("No matches available.")
    else:
        opts = [f"{r.farm} → {r.store} ({r.produce})" for r in df_all.itertuples()]
        pick = st.selectbox("Deal", opts)
        r = df_all.iloc[opts.index(pick)]
        grade = st.session_state.get("grade", {}).get("quality_grade", "A")
        ctx = dict(farm=r.farm, produce=r.produce, qty=r.qty_kg, grade=grade,
                   shelf=int(farms.set_index("farm_id").loc[r.farm_id].shelf_life_days),
                   ask=r.farm_price, floor=int(r.farm_price * 0.85))
        key = f"chat_{r.farm_id}_{r.store_id}"
        st.session_state.setdefault(key, [])
        for t in st.session_state[key]:
            st.chat_message("user" if t["role"] == "user" else "assistant").write(t["text"])
        msg = st.chat_input("Store owner: e.g. 'Bhai 75 rupay kilo de do, 40 kg chahiye'")
        if msg:
            st.session_state[key].append({"role": "user", "text": msg})
            with st.spinner("Gemma 4 negotiating..."):
                reply = gemma.bargain(st.session_state[key], ctx)
            st.session_state[key].append({"role": "model", "text": reply})
            st.rerun()
        deal = next((re.search(r"DEAL:.*", t["text"]).group(0) for t in reversed(st.session_state[key])
                     if t["role"] == "model" and "DEAL:" in t["text"]), None)
        if deal:
            st.success(f"✅ {deal}")
            st.session_state["last_deal"] = (r.store_id, r.farm_id, deal)

# ---------------- TAB 4: Solana trust ----------------
with tab4:
    st.subheader("Verifiable onchain identities & portable reputation")
    a, b = st.columns(2)
    with a:
        who = st.selectbox("Agent", [f"{x.farm_id} · {x.name} (seller)" for x in farms.itertuples()] +
                           [f"{x.store_id} · {x.name} (buyer)" for x in stores.itertuples()])
        if st.button("🪪 Register agent on Solana"):
            aid, rest = who.split(" · ")
            role = "seller" if "seller" in rest else "buyer"
            with st.spinner("Writing identity onchain..."):
                rec = sol.register_agent(aid, role, rest.split(" (")[0])
            (st.success if rec["onchain"] else st.warning)(rec["url"] or f"{rec['sig']} — {rec.get('error','')}")
            st.code(f"pubkey: {rec['pubkey']}")
    with b:
        ld = st.session_state.get("last_deal")
        st.write("Last deal:", ld[2] if ld else "— close a deal in tab 3 —")
        stars = st.slider("Rate the farm", 1, 5, 5)
        if ld and st.button("⭐ Record feedback onchain"):
            with st.spinner("Writing feedback onchain..."):
                rec = sol.record_feedback(ld[0], ld[1], stars, ld[2])
            (st.success if rec["onchain"] else st.warning)(rec["url"] or rec["sig"])
    st.markdown("#### Reputation (rebuilt from onchain feedback)")
    st.json(sol.reputation_scores() or {"info": "no feedback yet (default 3.0)"})
    st.markdown("#### Ledger")
    led = sol.ledger()
    if led:
        st.dataframe(pd.DataFrame(led)[["onchain", "memo", "sig"]], width="stretch", hide_index=True)
