"""Реестр наборов монет для дисциплины против переобучения.

Три НЕПЕРЕСЕКАЮЩИХСЯ набора. Данные всех закэшированы в data/ (1h×4000, 1d×1000).

Протокол честной проверки гипотезы:
  1) разрабатываешь/подбираешь параметры ТОЛЬКО на TUNING (можно смотреть сколько угодно);
  2) при желании — предварительная сверка на OOS_USED (он уже «засвечен» — служит
     как второй тюнинг/санити, НЕ как финальный вердикт);
  3) ФИНАЛЬНАЯ проверка — ОДИН раз, замороженной конфигурацией, на HOLDOUT.

ВАЖНО про HOLDOUT:
  - на нём НЕ подбирают параметры и НЕ прогоняют много гипотез;
  - каждый прогон на HOLDOUT «тратит» его независимость (множественные сравнения);
  - тестируй об него ОДНУ финальную конфигурацию на гипотезу; если нужно проверить
    много идей — заводи новый свежий набор (extend_holdout ниже как образец).
  - по состоянию на момент создания HOLDOUT ещё НЕ использовался ни разу.
"""
from __future__ import annotations

# на этих монетах велась вся разработка/тюнинг (M2–M3.5)
TUNING = ["SOL/USDT", "LINK/USDT", "NEAR/USDT", "FIL/USDT",
          "APE/USDT", "XRP/USDT", "BNB/USDT", "CRV/USDT"]

# первый out-of-sample (M3.6) + проверялась гипотеза фильтра (M3.7) -> УЖЕ засвечен
OOS_USED = ["1INCH/USDT", "GALA/USDT", "CHR/USDT", "ETH/USDT", "ADA/USDT",
            "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LTC/USDT", "ATOM/USDT"]

# СВЕЖИЙ независимый holdout — НЕ использовать до финальной проверки гипотезы.
HOLDOUT = ["BTC/USDT", "TRX/USDT", "UNI/USDT", "AAVE/USDT", "INJ/USDT", "SUI/USDT",
           "APT/USDT", "ARB/USDT", "OP/USDT", "RUNE/USDT", "YFI/USDT", "GRT/USDT"]

LTF, HTF = "1h", "1d"
LTF_BARS, HTF_BARS = 4000, 1000


def _assert_disjoint() -> None:
    a, b, c = set(TUNING), set(OOS_USED), set(HOLDOUT)
    assert a.isdisjoint(b) and a.isdisjoint(c) and b.isdisjoint(c), "наборы должны не пересекаться"


_assert_disjoint()
