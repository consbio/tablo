from django.test import TestCase
from django.db.utils import InternalError

from tablo.exceptions import BAD_DATA, DUPLICATE_COLUMN, TRANSFORM, UNKNOWN_ERROR
from tablo.exceptions import derive_error_response_data, InvalidFieldsError, InvalidFileError, QueryExecutionError


class PerformUtilsTestCase(TestCase):

    def test_derive_error_response_data_for_custom(self):
        # Invalid Fields

        error_fields = [f for f in 'abcdefg']

        error_except = InvalidFieldsError('Invalid field error')
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], UNKNOWN_ERROR)
        self.assertEqual(error_code['field_info'], [])

        error_except = InvalidFieldsError('Invalid field error', error_fields)
        error_code = derive_error_response_data(error_except, code=BAD_DATA)
        self.assertEqual(error_code['error_code'], BAD_DATA)
        self.assertEqual(error_code['field_info'], error_fields)

        # Invalid File

        error_ext = 'xxx'
        error_line = 0

        error_except = InvalidFileError('Generic file error')
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], UNKNOWN_ERROR)
        self.assertEqual(error_code['file_info'], {'lines': -1, 'extension': None})

        error_except = InvalidFileError('Wrong file extension error', extension=error_ext)
        error_code = derive_error_response_data(error_except, code=BAD_DATA)
        self.assertEqual(error_code['error_code'], BAD_DATA)
        self.assertEqual(error_code['file_info'], {'lines': -1, 'extension': error_ext})

        error_except = InvalidFileError('Empty file error', lines=error_line)
        error_code = derive_error_response_data(error_except, code=DUPLICATE_COLUMN)
        self.assertEqual(error_code['error_code'], DUPLICATE_COLUMN)
        self.assertEqual(error_code['file_info'], {'lines': error_line, 'extension': None})

        # Query Exception

        error_fields = [f for f in 'tuvwxyz']

        error_except = QueryExecutionError('Query exception error')
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], UNKNOWN_ERROR)
        self.assertEqual(error_code['field_info'], [])

        error_except = QueryExecutionError('Query exception error', error_fields)
        error_code = derive_error_response_data(error_except, code=TRANSFORM)
        self.assertEqual(error_code['error_code'], TRANSFORM)
        self.assertEqual(error_code['field_info'], error_fields)

    def test_derive_error_response_data_for_generic(self):
        error_except = InternalError(
            'transform: couldn\'t project point (4.0869e+10 4.53884e+11 0): latitude or longitude exceeded limits (-4)'
        )
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], TRANSFORM)

        error_except = InternalError(
            'column "is_celsius" specified more than once'
        )
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], DUPLICATE_COLUMN)

        error_except = InternalError(
            'invalid input syntax for integer: "x"'
        )
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], BAD_DATA)

        error_except = InternalError(
            'invalid input syntax for integer: "x"\n'
            "LINE 1480: .../2008','Visual Comparison to Call Library','None','x','x','x...\n"
            '                                                                ^\n'
        )
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], BAD_DATA)

        error_except = InternalError(
            'some random error'
        )
        error_code = derive_error_response_data(error_except)
        self.assertEqual(error_code['error_code'], UNKNOWN_ERROR)
