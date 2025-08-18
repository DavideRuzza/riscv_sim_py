import logging

class ColoredFormatter(logging.Formatter):
    # ANSI escape codes for colors
    COLORS = {
        'DEBUG': "\033[94m",   # Blue
        'INFO': "\033[92m",    # Green
        'WARNING': "\033[93m", # Yellow
        'ERROR': "\033[91m",   # Red
        'CRITICAL': "\033[95m" # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"

def setup_logging(level=logging.INFO):
    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[handler])
