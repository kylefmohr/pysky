class APIError(Exception):

    def __init__(self, message, apilog):
        self.message = message
        self.apilog = apilog

class NotAuthenticated(Exception):
    pass

class ExcessiveIteration(Exception):
    pass

class UploadException(Exception):
    pass

class MediaException(Exception):
    pass
