class ApiError(Exception):
    """A request failed. The message is a plain sentence, which a screen can say as it is."""
    pass

class DataModelError(Exception):
    """Custom exception for data model parsing errors"""
    pass


# For any other exception, whose own text isn't fit for a screen reader: a requests one runs to
# hundreds of characters of host, port and URL.
SOMETHING_WENT_WRONG = "Something went wrong. Try again in a minute."


def plain_message(error):
    """What a screen says about an exception."""
    return (isinstance(error, ApiError) and str(error)) or SOMETHING_WENT_WRONG
