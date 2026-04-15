"""ANSI color helpers for console output."""

# ANSI escape codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
ORANGE = "\033[38;5;208m"
PURPLE = "\033[38;5;141m"
GRAY = "\033[38;5;245m"
BOLD_RED = "\033[1;91m"
BOLD_CYAN = "\033[1;96m"
BOLD_WHITE = "\033[1;97m"


def _safe(text: str) -> str:
    try:
        text.encode("charmap")
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text.encode("ascii", errors="replace").decode("ascii")


def step(text: str):
    """Section headers — bold cyan, structural."""
    print(f"{BOLD_CYAN}{_safe(text)}{RESET}")


def parser(text: str):
    """Prompt parsing — yellow, thinking/processing."""
    print(f"  {YELLOW}[parser]{RESET} {_safe(text)}")


def browser(text: str):
    """Browser navigation — blue, web/internet."""
    print(f"  {BLUE}[browser]{RESET} {_safe(text)}")


def extractor(text: str):
    """Data extraction — cyan, pulling info out."""
    print(f"  {CYAN}[extractor]{RESET} {_safe(text)}")


def images(text: str):
    """Image capture — magenta, visual/media."""
    print(f"  {MAGENTA}[images]{RESET} {_safe(text)}")


def vision(text: str):
    """Vision AI analysis — purple, AI seeing."""
    print(f"  {PURPLE}[vision]{RESET} {_safe(text)}")


def scorer(text: str):
    """Scoring/evaluation — orange, judgment."""
    print(f"  {ORANGE}[scorer]{RESET} {_safe(text)}")


def messenger(text: str):
    """Messaging — green, go/send/action."""
    print(f"  {GREEN}[messenger]{RESET} {_safe(text)}")


def href(index: int, url: str):
    """Listing URLs — gray, reference info."""
    print(f"  {GRAY}[{index}]{RESET} {GRAY}{_safe(url)}{RESET}")


def throttle(text: str):
    """Rate limiting / cooldowns — yellow, caution."""
    print(f"  {YELLOW}[throttle]{RESET} {_safe(text)}")


def error(text: str):
    """Errors — red."""
    print(f"  {RED}[ERROR]{RESET} {_safe(text)}")


def rate_limit(text: str):
    """Rate limit warnings — bold red, serious."""
    print(f"  {BOLD_RED}*** {_safe(text)} ***{RESET}")


def summary(text: str):
    """Final summary lines — bold white."""
    print(f"{BOLD_WHITE}{_safe(text)}{RESET}")
