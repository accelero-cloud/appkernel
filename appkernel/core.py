from __future__ import annotations

from enum import Enum


class AppKernelException(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__()

    def __str__(self) -> str:
        return self.message if 'message' in self.__dict__ else self.__class__.__name__


class AppInitialisationError(AppKernelException):

    def __init__(self, message: str) -> None:
        super().__init__(message)


class MessageType(Enum):
    ErrorMessage = 1
