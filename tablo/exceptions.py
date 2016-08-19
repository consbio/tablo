from django.core.exceptions import ValidationError
from django.db.utils import DatabaseError


class InvalidFieldsError(ValidationError, DatabaseError, ValueError):
    """ A database field error caught before execution: extends ValueError for backwards compatibility. """


class SQLInjectionError(ValidationError, DatabaseError):
    """ A database error that should be caught before execution """
