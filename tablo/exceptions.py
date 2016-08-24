from django.core.exceptions import ValidationError


class InvalidSQLError(ValidationError):
    """ A database error that should be caught before execution """


class InvalidFieldsError(ValidationError, ValueError):
    """ A database field error caught before execution: extends ValueError for backwards compatibility. """

    def __init__(self, message, fields=None, **kwargs):
        super(InvalidFieldsError, self).__init__(message, **kwargs)
        self.fields = fields if fields is not None else []


class RelatedFieldsError(InvalidFieldsError):
    """ A database field error caught before execution: raised when fields from related tables are invalid. """
