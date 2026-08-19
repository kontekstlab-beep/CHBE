import os

import pytest

from smartmoney.datasets import HOLDOUT, LTF, LTF_BARS, OOS_USED, TUNING


def test_sets_disjoint():
    a, b, c = set(TUNING), set(OOS_USED), set(HOLDOUT)
    assert a.isdisjoint(b)
    assert a.isdisjoint(c)
    assert b.isdisjoint(c)
    assert len(HOLDOUT) >= 8


def test_holdout_data_cached():
    # проверяем НАЛИЧИЕ кэша (не запускаем стратегии — чтобы не «засветить» holdout).
    # data/ в git не хранится (регенерируется get_cached) -> пропускаем, если пусто.
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    if not os.path.isdir(root):
        pytest.skip("кэш data/ отсутствует (получить: smartmoney.data.get_cached)")
    for s in HOLDOUT:
        fname = s.replace("/", "") + f"_{LTF}_{LTF_BARS}.csv"
        if not os.path.exists(os.path.join(root, fname)):
            pytest.skip(f"нет кэша {fname} — регенерируется get_cached")
