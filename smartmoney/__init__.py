"""Smart Money / ICT trading bot — prototype.

Реализация примитивов структуры рынка по методике из обучения (см. ТЗ).
Пакеты:
    models      — датаклассы (Candle, Swing, OrderBlock, FVG, LiquidityPool).
    config      — параметры стратегии (пороги из ТЗ §14).
    structure   — свинги, тренд, слом структуры (BOS).
    liquidity   — пулы ликвидности (BSL/SSL).
    imbalance   — FVG (имбаланс).
    orderblocks — блоки заказов со score силы.
    synth       — генератор синтетических рядов для тестов/демо.
"""

__version__ = "0.1.0"
