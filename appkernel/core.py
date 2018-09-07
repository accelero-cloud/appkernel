from enum import Enum


class AppKernelException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__()

    def __str__(self):
        return self.message if 'message' in self.__dict__ else self.__class__.__name__


class MessageType(Enum):
    ErrorMessage = 1
