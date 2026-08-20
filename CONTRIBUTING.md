# Contributing

Ветка `main` защищена: прямой push запрещён, влить можно только через Pull Request
с зелёными тестами.

## Рабочий процесс
```bash
git checkout -b feature/<название>
# ...правки...
git add -A && git commit -m "..."
git push -u origin feature/<название>
# открыть Pull Request в main на GitHub
```
Мердж доступен, только когда прошли все проверки CI:
`pytest (3.11)`, `pytest (3.12)`, `pytest (3.13)` (см. `.github/workflows/tests.yml`).

## Тесты локально
```bash
python -m pytest -q
```
Кодовая база — чистый Python (нужен только `pytest`). Тесты, читающие кэш `data/`
(вне git), пропускаются, если данных нет; данные тянутся через
`smartmoney.data.get_cached`.

## Требования к правилу защиты main
- Require a pull request before merging
- Require status checks to pass: `pytest (3.11/3.12/3.13)`
- Require branches to be up to date before merging
- Включая администраторов (без обхода)
