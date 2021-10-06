from django.core.exceptions import ValidationError
from django.db.utils import DataError


BAD_DATA = 'BAD_DATA'
DUPLICATE_COLUMN = 'DUPLICATE_COLUMN'
TRANSFORM = 'TRANSFORM'
UNKNOWN_ERROR = 'UNKNOWN_ERROR'


class InvalidFileError(ValidationError):
    """ An error with a CSV that can be handled before database operations """

    def __init__(self, message, lines=-1, extension=None, **kwargs):
        super(InvalidFileError, self).__init__(message, **kwargs)
        self.file_info = {'lines': lines, 'extension': extension}


class InvalidFieldsError(ValidationError, ValueError):
    """ A database field error caught before execution: extends ValueError for backwards compatibility """

    def __init__(self, message, fields=None, **kwargs):
        super(InvalidFieldsError, self).__init__(message, **kwargs)
        self.fields = [] if fields is None else fields


class InvalidSQLError(ValidationError):
    """ A database error that should be caught before execution """


class RelatedFieldsError(InvalidFieldsError):
    """ A database field error caught before execution: raised when fields from related tables are invalid """


class QueryExecutionError(DataError, ValueError):
    """ A database error caught during query execution """

    def __init__(self, underlying, fields=None):
        self.message = error_to_string(underlying)
        self.fields = [] if fields is None else fields

        super(QueryExecutionError, self).__init__(self.message)


def derive_error_response_data(e, code=UNKNOWN_ERROR):
    """ Inspects error message to derive error codes and info """

    error_msg = error_to_string(e)
    error_text = error_msg.lower()
    error_json = {'error_code': code, 'underlying': error_msg}

    if getattr(e, 'fields', None) is not None:
        error_json['field_info'] = e.fields
    if getattr(e, 'file_info', None) is not None:
        error_json['file_info'] = e.file_info

    if 'transform' in error_text:
        error_json['error_code'] = TRANSFORM
    elif 'column' in error_text and 'specified more than once' in error_text:
        error_json['error_code'] = DUPLICATE_COLUMN
    elif 'out of range' in error_text:
        error_json['error_code'] = BAD_DATA
    elif 'invalid input syntax' in error_text:
        error_json['error_code'] = BAD_DATA

        try:
            line_marker = '\nLINE '

            line = error_msg
            line = line[line.index(line_marker) + len(line_marker):]
            line = line[:line.index(':')].strip()

            error_json['error_line'] = line
        except ValueError:
            pass

    return error_json


def error_to_string(error):
    """ Helper to derive information from an error even if blank """
    return getattr(error, 'message', str(error) or type(error).__name__)
