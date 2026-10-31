"""
matcher.py — Farm-to-store matching engine (hyper-local logistics).

Score for each (farm, store) pair:
    score = 0.35*need_match + 0.25*deficit(store_area, day)
          + 0.20*proximity  + 0.10*price_fit + 0.10*reputation
Hard filters: store must need the produce; farm's shelf life must cover delivery.
Route ordering for one farm truck uses a nearest-neighbour heuristic.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MAX_KM = 40.0


def load():
    farms = pd.read_csv(DATA / "farms.csv")
    stores = pd.read_csv(DATA / "stores.csv")
    deficit = pd.read_csv(DATA / "deficit_by_day.csv").set_index("area")
    return farms, stores, deficit


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def match(day: str, reputation: dict[str, float] | None = None, produce_filter=None) -> pd.DataFrame:
    farms, stores, deficit = load()
    reputation = reputation or {}
    rows = []
    for _, f in farms.iterrows():
        if produce_filter and f.produce.lower() != produce_filter.lower():
            continue
        for _, s in stores.iterrows():
            needs = [n.strip().lower() for n in s.needs.split(";")]
            if f.produce.lower() not in needs:
                continue
            km = haversine_km(f.lat, f.lon, s.lat, s.lon)
            if km > MAX_KM:
                continue
            travel_days = 0 if km < 25 else 1
            if f.shelf_life_days <= travel_days:
                continue
            d = float(deficit.loc[s.area, day]) if s.area in deficit.index else 0.5
            proximity = 1 - km / MAX_KM
            price_fit = max(0.0, min(1.0, 1 - (f.price_pkr_per_kg - s.budget_pkr_per_kg) / max(s.budget_pkr_per_kg, 1)))
            rep = (reputation.get(f.farm_id, 3.0) + reputation.get(s.store_id, 3.0)) / 10.0
            qty_fit = min(f.surplus_kg, s.demand_kg) / s.demand_kg
            score = 0.35 * qty_fit + 0.25 * d + 0.20 * proximity + 0.10 * price_fit + 0.10 * rep
            rows.append(
                dict(
                    farm_id=f.farm_id, farm=f["name"], produce=f.produce,
                    store_id=s.store_id, store=s["name"], store_area=s.area,
                    km=round(km, 1), deficit=d,
                    qty_kg=int(min(f.surplus_kg, s.demand_kg)),
                    farm_price=int(f.price_pkr_per_kg), store_budget=int(s.budget_pkr_per_kg),
                    score=round(score * 100, 1),
                    f_lat=f.lat, f_lon=f.lon, s_lat=s.lat, s_lon=s.lon,
                )
            )
    df = pd.DataFrame(rows)
    return df.sort_values("score", ascending=False).reset_index(drop=True) if len(df) else df


def worst_deficit_day(area: str) -> str:
    _, _, deficit = load()
    return deficit.loc[area].idxmax()


def delivery_route(farm_id: str, store_ids: list[str]) -> list[tuple[str, float]]:
    """Nearest-neighbour route for one farm's delivery run. Returns [(stop, cumulative_km)]."""
    farms, stores, _ = load()
    f = farms.set_index("farm_id").loc[farm_id]
    st = stores.set_index("store_id")
    cur, total, route, left = (f.lat, f.lon), 0.0, [], list(store_ids)
    while left:
        nxt = min(left, key=lambda s: haversine_km(*cur, st.loc[s].lat, st.loc[s].lon))
        total += haversine_km(*cur, st.loc[nxt].lat, st.loc[nxt].lon)
        route.append((st.loc[nxt]["name"], round(total, 1)))
        cur = (st.loc[nxt].lat, st.loc[nxt].lon)
        left.remove(nxt)
    return route
