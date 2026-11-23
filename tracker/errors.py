"""One error type for "the caller did something wrong"."""


# An error we want to show to the caller. It carries the HTTP code to send
# (400, 404, 409...) and a short message. The server turns it into JSON.
class ApiError(Exception):
    # Remember the code and the message so the server can read them later.
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message
