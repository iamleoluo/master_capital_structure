"""MSTR × BTC × mNAV × CEBE 歷史對照系統。

依 MSTR_CEBE_歷史分析_建置規格.md 實作。模組分工見 README.md。

最重要的一條規則(§8.1):**任何 mNAV 數字都必須攜帶 variant 與日期**。
core.mnav() 一律回傳 MNavReading,不回傳裸 float,就是為了讓這件事無法被繞過。
"""
__all__ = ["core", "data", "db", "fetch", "charts", "cli"]
