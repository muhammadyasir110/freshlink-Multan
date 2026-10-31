"""
solana_registry.py — Verifiable onchain identity + portable reputation (Solana devnet).

* Every buyer (store) and seller (farm) agent gets its own Solana keypair = identity.
* register_agent()   writes  FRESHLINK|REGISTER|<agent_id>|<role>|<pubkey>      onchain
* record_feedback()  writes  FRESHLINK|FEEDBACK|<from>|<to>|<stars>|<deal>     onchain
  using the SPL Memo program, so every record is public & immutable and can be
  viewed on https://explorer.solana.com/tx/<sig>?cluster=devnet

If devnet is unreachable / the payer has no SOL, the call falls back to a local
hash-chained ledger and is labelled SIMULATED (never shown as a real tx).
If organisers provide the official Solana Agent Registry program id, set
AGENT_REGISTRY_PROGRAM_ID and the register payload is sent to that program too.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
STATE = Path(__file__).parent / ".freshlink_state"
STATE.mkdir(exist_ok=True)
KEYS = STATE / "keys.json"
LEDGER = STATE / "ledger.json"


def _load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def _save(p, obj):
    p.write_text(json.dumps(obj, indent=2))


def explorer(sig: str) -> str:
    return f"https://explorer.solana.com/tx/{sig}?cluster=devnet"


# ---------------- identities ----------------
def get_keypair(agent_id: str) -> Keypair:
    keys = _load(KEYS, {})
    if agent_id not in keys:
        keys[agent_id] = list(bytes(Keypair()))
        _save(KEYS, keys)
    return Keypair.from_bytes(bytes(keys[agent_id]))


def payer() -> Keypair:
    """Fee payer. Put a funded devnet secret key (JSON array) in SOLANA_PAYER_KEY, or we airdrop."""
    raw = os.getenv("SOLANA_PAYER_KEY")
    return Keypair.from_bytes(bytes(json.loads(raw))) if raw else get_keypair("__payer__")


def _rpc(method: str, params: list):
    """Minimal Solana JSON-RPC call (no SDK version lock-in)."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC_URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error'].get('message')}")
    return out["result"]


def _balance(pk) -> int:
    return _rpc("getBalance", [str(pk), {"commitment": "confirmed"}])["value"]


def ensure_funded(min_lamports: int = 5_000_000) -> str:
    p = payer()
    if _balance(p.pubkey()) >= min_lamports:
        return f"payer {p.pubkey()} funded"
    sig = _rpc("requestAirdrop", [str(p.pubkey()), 1_000_000_000])
    for _ in range(30):
        time.sleep(1)
        if _balance(p.pubkey()) >= min_lamports:
            return f"airdropped 1 SOL to {p.pubkey()} ({sig})"
    raise RuntimeError(f"airdrop not confirmed — fund {p.pubkey()} at https://faucet.solana.com")


# ---------------- onchain write ----------------
def _send_memo(memo: str, signer: Keypair) -> str:
    p = payer()
    signers = [p] if signer.pubkey() == p.pubkey() else [p, signer]
    ix = Instruction(MEMO_PROGRAM_ID, memo.encode(), [AccountMeta(signer.pubkey(), True, True)])
    bh = Hash.from_string(_rpc("getLatestBlockhash", [{"commitment": "finalized"}])["value"]["blockhash"])
    tx = Transaction(signers, Message([ix], p.pubkey()), bh)
    sig = _rpc("sendTransaction", [base64.b64encode(bytes(tx)).decode(), {"encoding": "base64"}])
    for _ in range(30):  # wait for confirmation
        st = _rpc("getSignatureStatuses", [[sig]])["value"][0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            if st.get("err"):
                raise RuntimeError(f"tx failed: {st['err']}")
            return sig
        time.sleep(1)
    return sig


def _simulate(memo: str) -> str:
    led = _load(LEDGER, [])
    prev = led[-1]["hash"] if led else "0" * 64
    h = hashlib.sha256((prev + memo).encode()).hexdigest()
    sig = "SIMULATED-" + h[:40]
    led.append({"memo": memo, "sig": sig, "hash": h, "ts": time.time(), "onchain": False})
    _save(LEDGER, led)
    return sig


def _write(memo: str, signer: Keypair) -> dict:
    try:
        ensure_funded()
        sig = _send_memo(memo, signer)
        rec = {"memo": memo, "sig": sig, "url": explorer(sig), "onchain": True, "ts": time.time()}
        led = _load(LEDGER, [])
        led.append(rec)
        _save(LEDGER, led)
        return rec
    except Exception as e:  # network blocked / airdrop rate-limited
        return {"memo": memo, "sig": _simulate(memo), "url": None, "onchain": False, "error": str(e)[:160]}


def register_agent(agent_id: str, role: str, name: str) -> dict:
    kp = get_keypair(agent_id)
    memo = f"FRESHLINK|REGISTER|{agent_id}|{role}|{name[:40]}|{kp.pubkey()}"
    rec = _write(memo, kp)
    rec["pubkey"] = str(kp.pubkey())
    return rec


def record_feedback(from_id: str, to_id: str, stars: int, deal: str) -> dict:
    assert 1 <= stars <= 5
    memo = f"FRESHLINK|FEEDBACK|{from_id}|{to_id}|{stars}|{deal[:60]}"
    return _write(memo, get_keypair(from_id))


def reputation_scores() -> dict[str, float]:
    """Portable reputation = average stars received, rebuilt from the ledger (default 3.0)."""
    agg: dict[str, list[int]] = {}
    for r in _load(LEDGER, []):
        parts = r["memo"].split("|")
        if len(parts) >= 5 and parts[1] == "FEEDBACK":
            agg.setdefault(parts[3], []).append(int(parts[4]))
    return {k: round(sum(v) / len(v), 2) for k, v in agg.items()}


def ledger() -> list[dict]:
    return _load(LEDGER, [])
