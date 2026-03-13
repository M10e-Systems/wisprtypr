from enum import Enum


class AppState(str, Enum):
    OFF = "off"
    LISTENING = "listening"
    ERROR = "error"
