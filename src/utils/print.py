import math
import shutil
import sys
from typing import Any, Iterable, Literal

import tqdm


def load_print(
    text: str,
    symbol: str = "*",
    indent: int = 0,
    echo: bool = True,
    end: str = "\r",
) -> None:
    symbol = f"\033[1m[{symbol}]\033[0m"
    if echo:
        print(
            f"\r{' ' * indent}{symbol} {text}".ljust(
                shutil.get_terminal_size().columns
            ),
            end=end,
        )


def done_print(
    text: str,
    symbol: str = "+",
    indent: int = 0,
    echo: bool = True,
    overwrite_n_extra_lines: int = 0,
) -> None:
    symbol = f"\033[1m\033[92m[{symbol}]\033[0m"
    if echo:
        if overwrite_n_extra_lines:
            cursor_up(overwrite_n_extra_lines + 1)
            for _ in range(overwrite_n_extra_lines):
                print(" ".ljust(shutil.get_terminal_size().columns))
            cursor_up(overwrite_n_extra_lines + 1)
        print(
            f"\r{' ' * indent}{symbol} {text}".ljust(
                shutil.get_terminal_size().columns
            )
        )


def load_progress(
    iter_: Iterable[Any],
    text: str,
    symbol: str = "*",
    indent: int = 0,
    echo: bool = True,
    *args: Any,
    **kwargs: Any,
) -> Iterable[Any]:
    if echo:
        return tqdm.asyncio.tqdm(
            iter_,
            f"{' ' * indent}[{symbol}] {text}",
            *args,
            leave=False,
            position=0,
            file=sys.stdout,
            **kwargs,
        )
    else:
        return iter_


def format_list(
    list_: list[str] | tuple[str, ...],
    surround: str = "",
    word: Literal["and", "or"] = "and",
) -> str:
    if surround:
        list_ = [f"{surround}{x}{surround}" for x in list_]
    if len(list_) == 0:
        return ""
    elif len(list_) == 1:
        return list_[0]
    else:
        return f"{', '.join(list_[:-1])} {word} {list_[-1]}"


def format_time(time: float) -> str:
    time = round(time)
    seconds = time % 60
    time = time // 60
    minutes = time % 60
    time = time // 60
    hours = time % 60
    time_ = ""
    if hours:
        time_ = f"{time_}{hours}h"
    if minutes or hours:
        time_ = f"{time_}{minutes}m"
    time_ = f"{time_}{seconds}s"
    return time_


def format_number(n: float, min_digits: int = 1) -> str:
    if n == 0:
        return "{{:.{}f}}".format(min_digits).format(0)
    else:
        if n < 0:
            sign = "-"
            n = abs(n)
        else:
            sign = ""
        digits = max(int(-math.floor(math.log10(n))), min_digits)
        return "{}{{:.{}f}}".format(sign, digits).format(n)


def cursor_up(n: int) -> None:
    print(f"\x1b[{n}A")
