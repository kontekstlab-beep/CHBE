import os
import sys

# Добавляем корень проекта в sys.path, чтобы `import smartmoney` работал без установки пакета.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
