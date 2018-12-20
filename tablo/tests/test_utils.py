from django.test import TestCase
from django.db.utils import InternalError

from tablo.exceptions import BAD_DATA, DUPLICATE_COLUMN, TRANSFORM, UNKNOWN_ERROR
from tablo.exceptions import derive_error_response_data


class PerformUtilsTestCase(TestCase):

    def test_derive_error_response_data(self):
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
