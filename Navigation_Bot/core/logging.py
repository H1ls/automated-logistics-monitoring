from __future__ import annotations

from typing import Callable


LogFunc = Callable[..., None]


def noop_log(*_args, **_kwargs) -> None:
    pass


def normalize_log_func(log_func: LogFunc | None = None) -> LogFunc:
    """
    Возвращает callback для логирования, совместимый с GUI и консолью.
    LogController принимает (message, audience, severity).
    Для старых функций и print метаданные игнорируются.
    """
    target = log_func or print

    def _log(message: object = "", *args, **kwargs) -> None:
        try:
            target(message, *args, **kwargs)
        except TypeError:
            target(message)

    return _log
