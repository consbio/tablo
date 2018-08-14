from django.test import TestCase
from django.db.utils import InternalError

from tablo.utils import get_file_ops_error_code


class PerformUtilsTestCase(TestCase):

    def test_get_file_ops_error_code(self):
        error_except = InternalError(
            'transform: couldn\'t project point (4.0869e+10 4.53884e+11 0): latitude or longitude exceeded limits (-14)'
        )
        error_code = get_file_ops_error_code(error_except)
        self.assertEqual(error_code, 'TRANSFORM')

        error_except = InternalError(
            'column "is_celsius" specified more than once'
        )
        error_code = get_file_ops_error_code(error_except)
        self.assertEqual(error_code, 'DUPLICATE_COLUMN')

        error_except = InternalError(
            'some random error'
        )
        error_code = get_file_ops_error_code(error_except)
        self.assertEqual(error_code, 'UNKNOWN_ERROR')
