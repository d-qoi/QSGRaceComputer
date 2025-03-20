class ATCommandError(Exception):
    """Base exception for all AT Command errors."""

    code = None
    message = None

    def __init__(self, message: str = ""):
        self.message = message

    def __str__(self):
        return f"+ERR={self.code}: {self.message or self.__doc__}"

class RecLoopNotRunning(ATCommandError):
    """Rec Loop Not Running"""

    code = -1

class NotReady(ATCommandError):
    """Not Ready"""

    code = -1


class NoTerminatorError(ATCommandError):
    """No 'enter' or \r\n' at the end of the command"""

    code = 1


class InvalidCommandHeadError(ATCommandError):
    """Head of AT command is not 'AT' string"""

    code = 2


class MissingEqualSymbolError(ATCommandError):
    """There is no '=' symbol in the AT command"""

    code = 3


class UnknownCommandError(ATCommandError):
    """Unknown command"""

    code = 4


class TXOverTimesError(ATCommandError):
    """TX is over times"""

    code = 10


class RXOverTimesError(ATCommandError):
    """RX is over times"""

    code = 11


class CRCError(ATCommandError):
    """CRC error"""

    code = 12


class TXDataOverflowError(ATCommandError):
    """TX data is more than 240 bytes"""

    code = 13


class UnknownError(ATCommandError):
    """Unknown error"""

    code = 15


ERROR_MAP = {
    1: NoTerminatorError,
    2: InvalidCommandHeadError,
    3: MissingEqualSymbolError,
    4: UnknownCommandError,
    10: TXOverTimesError,
    11: RXOverTimesError,
    12: CRCError,
    13: TXDataOverflowError,
    15: UnknownError,
}


def get_error_by_code(code: int):
    exception_class = ERROR_MAP.get(code, UnknownError)
    return exception_class()
