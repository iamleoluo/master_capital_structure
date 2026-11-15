"""data.py 裡的觀測表與參照表。正本是 data/obs 與 data/ref 的 CSV。

金額是美元，股數是股，持幣是顆。空欄是 None。
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .records import (
    PolicyBreak,
    PreferredBalance,
    PreferredIPO,
    ShareCount,
)

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "data" / "obs"
REF = ROOT / "data" / "ref"


def _f(v: Optional[float]) -> str:
    if v is None:
        return ""
    return repr(float(v))


def _p(s: str) -> Optional[float]:
    s = s.strip()
    return None if s == "" else float(s)


def _b(s: str) -> bool:
    return s.strip() in ("1", "true", "True")


def _date(s: str) -> date:
    return date.fromisoformat(s)


def _write(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow(row)


def _read(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def dump_pairs(path: Path, rows: Sequence[Tuple[date, float]], value_header: str = "value") -> None:
    _write(path, ("as_of", value_header), ((d.isoformat(), _f(v)) for d, v in rows))


def load_pairs(path: Path, value_header: str = "value") -> Tuple[Tuple[date, float], ...]:
    return tuple((_date(r["as_of"]), float(r[value_header])) for r in _read(path))


def dump_weekly(rows: Sequence[Tuple[date, int]]) -> None:
    dump_pairs(OBS / "weekly_btc_held.csv", rows, "btc")


def load_weekly_btc_held() -> Tuple[Tuple[date, int], ...]:
    return tuple((_date(r["as_of"]), int(float(r["btc"]))) for r in _read(OBS / "weekly_btc_held.csv"))


def dump_xbrl_btc(rows: Sequence[Tuple[date, float]]) -> None:
    dump_pairs(OBS / "xbrl_btc_held.csv", rows, "btc")


def load_xbrl_btc_held() -> Tuple[Tuple[date, float], ...]:
    return load_pairs(OBS / "xbrl_btc_held.csv", "btc")


def dump_xbrl_debt(rows: Sequence[Tuple[date, float]]) -> None:
    dump_pairs(OBS / "xbrl_debt.csv", rows, "usd")


def load_xbrl_debt() -> Tuple[Tuple[date, float], ...]:
    return load_pairs(OBS / "xbrl_debt.csv", "usd")


def dump_xbrl_cash(rows: Sequence[Tuple[date, float]]) -> None:
    dump_pairs(OBS / "xbrl_cash.csv", rows, "usd")


def load_xbrl_cash() -> Tuple[Tuple[date, float], ...]:
    return load_pairs(OBS / "xbrl_cash.csv", "usd")


def dump_xbrl_wavg(rows: Sequence[Tuple[date, float]]) -> None:
    dump_pairs(OBS / "xbrl_wavg_shares.csv", rows, "shares")


def load_xbrl_wavg_shares() -> Tuple[Tuple[date, float], ...]:
    return load_pairs(OBS / "xbrl_wavg_shares.csv", "shares")


def dump_convertible_totals(rows: Sequence[Tuple[date, float, str]]) -> None:
    _write(OBS / "convertible_totals.csv", ("as_of", "usd", "note"),
           ((d.isoformat(), _f(v), note) for d, v, note in rows))


def load_convertible_totals() -> Tuple[Tuple[date, float, str], ...]:
    return tuple((_date(r["as_of"]), float(r["usd"]), r["note"])
                 for r in _read(OBS / "convertible_totals.csv"))


def dump_strc_dividend(rows: Sequence[Tuple[date, float]]) -> None:
    dump_pairs(OBS / "strc_dividend_schedule.csv", rows, "rate_pct")


def load_strc_dividend_schedule() -> Tuple[Tuple[date, float], ...]:
    return load_pairs(OBS / "strc_dividend_schedule.csv", "rate_pct")


_SHARE_HEADER = ("as_of", "class_a", "class_b", "basic", "fdso", "source", "is_estimated")


def dump_share_counts(rows: Sequence[ShareCount]) -> None:
    _write(OBS / "share_counts.csv", _SHARE_HEADER, (
        (r.as_of.isoformat(), _f(r.class_a), _f(r.class_b), _f(r.basic), _f(r.fdso),
         r.source, "1" if r.is_estimated else "0")
        for r in rows
    ))


def load_share_counts() -> Tuple[ShareCount, ...]:
    out = []
    for r in _read(OBS / "share_counts.csv"):
        out.append(ShareCount(
            _date(r["as_of"]), _p(r["class_a"]), _p(r["class_b"]), _p(r["basic"]),
            _p(r["fdso"]), r["source"], _b(r["is_estimated"]),
        ))
    return tuple(out)


_BAL_HEADER = (
    "as_of", "strk", "strf", "strd", "strc", "stre_usd", "total", "total_shares",
    "source", "is_estimated", "stre_eur", "fx_eur_usd", "shares_json",
)


def dump_preferred_balances(rows: Sequence[PreferredBalance]) -> None:
    _write(OBS / "preferred_balances.csv", _BAL_HEADER, (
        (r.as_of.isoformat(), _f(r.strk), _f(r.strf), _f(r.strd), _f(r.strc),
         _f(r.stre_usd), _f(r.total), _f(r.total_shares), r.source,
         "1" if r.is_estimated else "0", _f(r.stre_eur), _f(r.fx_eur_usd),
         "" if not r.shares_by_ticker else json.dumps(r.shares_by_ticker, sort_keys=True))
        for r in rows
    ))


def load_preferred_balances() -> Tuple[PreferredBalance, ...]:
    out = []
    for r in _read(OBS / "preferred_balances.csv"):
        shares = json.loads(r["shares_json"]) if r["shares_json"] else None
        out.append(PreferredBalance(
            _date(r["as_of"]), _p(r["strk"]), _p(r["strf"]), _p(r["strd"]), _p(r["strc"]),
            _p(r["stre_usd"]), _p(r["total"]), _p(r["total_shares"]), r["source"],
            _b(r["is_estimated"]), _p(r["stre_eur"]), _p(r["fx_eur_usd"]), shares,
        ))
    return tuple(out)


_IPO_HEADER = (
    "ticker", "name", "pricing_date", "ipo_shares", "offer_price", "stated_amount",
    "currency", "ipo_liquidation_pref", "net_proceeds", "dividend_rate_pct",
    "rank", "convertible", "note",
)


def dump_ipos(rows: Sequence[PreferredIPO]) -> None:
    _write(REF / "preferred_ipos.csv", _IPO_HEADER, (
        (r.ticker, r.name, r.pricing_date.isoformat(), _f(r.ipo_shares), _f(r.offer_price),
         _f(r.stated_amount), r.currency, _f(r.ipo_liquidation_pref), _f(r.net_proceeds),
         _f(r.dividend_rate_pct), r.rank, "1" if r.convertible else "0", r.note)
        for r in rows
    ))


def load_preferred_ipos() -> Tuple[PreferredIPO, ...]:
    out = []
    for r in _read(REF / "preferred_ipos.csv"):
        out.append(PreferredIPO(
            r["ticker"], r["name"], _date(r["pricing_date"]), float(r["ipo_shares"]),
            float(r["offer_price"]), float(r["stated_amount"]), r["currency"],
            float(r["ipo_liquidation_pref"]), float(r["net_proceeds"]),
            _p(r["dividend_rate_pct"]), int(r["rank"]), _b(r["convertible"]), r["note"],
        ))
    return tuple(out)


def dump_policy_breaks(rows: Sequence[PolicyBreak]) -> None:
    _write(REF / "policy_breaks.csv", ("as_of", "title", "detail", "breaks_timeseries"), (
        (r.as_of.isoformat(), r.title, r.detail, "1" if r.breaks_timeseries else "0")
        for r in rows
    ))


def load_policy_breaks() -> Tuple[PolicyBreak, ...]:
    return tuple(
        PolicyBreak(_date(r["as_of"]), r["title"], r["detail"], _b(r["breaks_timeseries"]))
        for r in _read(REF / "policy_breaks.csv")
    )


_FWP_HEADER = (
    "id", "btc_held", "usd_reserve", "debt_otm_notional", "pref_otm_notional", "fdso",
    "accession", "mstr_price", "btc_price", "shares_assumed_diluted",
    "usd_reserve_stated", "usd_cash", "annual_obligations",
)


def dump_fwp(rows: Sequence[Dict[str, object]]) -> None:
    out = []
    for row in rows:
        cells = []
        for k in _FWP_HEADER:
            v = row.get(k, "")
            if isinstance(v, float):
                cells.append(_f(v))
            elif v is None or v == "":
                cells.append("")
            else:
                cells.append(v)
        out.append(cells)
    _write(REF / "fwp_params.csv", _FWP_HEADER, out)


def load_fwp_row(scenario_id: str) -> Dict[str, str]:
    for r in _read(REF / "fwp_params.csv"):
        if r["id"] == scenario_id:
            return r
    raise KeyError(scenario_id)


def fwp_params(scenario_id: str) -> Dict[str, float]:
    r = load_fwp_row(scenario_id)
    return {
        "btc_held": float(r["btc_held"]),
        "usd_reserve": float(r["usd_reserve"]),
        "debt_otm_notional": float(r["debt_otm_notional"]),
        "pref_otm_notional": float(r["pref_otm_notional"]),
        "fdso": float(r["fdso"]),
    }
