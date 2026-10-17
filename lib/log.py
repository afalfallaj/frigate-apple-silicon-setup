import sys

_IS_TTY = sys.stdout.isatty()
_RESET  = "\033[0m"  if _IS_TTY else ""
_BOLD   = "\033[1m"  if _IS_TTY else ""
_GREEN  = "\033[32m" if _IS_TTY else ""
_YELLOW = "\033[33m" if _IS_TTY else ""
_RED    = "\033[31m" if _IS_TTY else ""
_CYAN   = "\033[36m" if _IS_TTY else ""

def _c(colour: str, text: str) -> str:
    return f"{colour}{text}{_RESET}"

def log_info(msg: str)    -> None: print(_c(_CYAN,   f"[INFO]  {msg}"))
def log_ok(msg: str)      -> None: print(_c(_GREEN,  f"[ OK ]  {msg}"))
def log_warn(msg: str)    -> None: print(_c(_YELLOW, f"[WARN]  {msg}"))
def log_error(msg: str)   -> None: print(_c(_RED,    f"[ERR ]  {msg}"), file=sys.stderr)
def log_section(msg: str) -> None: print(f"\n{_BOLD}{_CYAN}{'='*60}{_RESET}\n{_BOLD}  {msg}{_RESET}\n{'='*60}")
