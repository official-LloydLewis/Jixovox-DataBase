from colorama import Fore, Back, Style, init

# Initialize colorama (especially for Windows)
init(autoreset=True)

# Foreground colors
RED = Fore.RED
LRED = Fore.LIGHTRED_EX
GREEN = Fore.GREEN
BLUE = Fore.BLUE
CYAN = Fore.CYAN
MAGENTA = Fore.MAGENTA
YELLOW = Fore.YELLOW
WHITE = Fore.WHITE
BLACK = Fore.BLACK
RESET = Fore.RESET

# Background colors
BG_RED = Back.RED
BG_GREEN = Back.GREEN
BG_BLUE = Back.BLUE
BG_CYAN = Back.CYAN
BG_MAGENTA = Back.MAGENTA
BG_YELLOW = Back.YELLOW
BG_WHITE = Back.WHITE
BG_BLACK = Back.BLACK
BG_RESET = Back.RESET

# Styles
BRIGHT = Style.BRIGHT
DIM = Style.DIM
NORMAL = Style.NORMAL
STYLE_RESET = Style.RESET_ALL
