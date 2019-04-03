import io

from django.test import TestCase

from tablo.csv_utils import prepare_csv_rows, convert_header_to_column_name, determine_x_and_y_fields


class TestCSVUtils(TestCase):

    def test_data_type_inference(self):
        test_csv_file = io.StringIO(
            'header_one,header_two,header_three,header_four\n'
            'one,1,,1\n'
            'two,2,,2.1\n'
        )
        row_set, dtypes = prepare_csv_rows(test_csv_file)
        self.assertEqual(dtypes[0].lower(), 'string')
        self.assertEqual(dtypes[1].lower(), 'integer')
        self.assertEqual(dtypes[2].lower(), 'empty')
        self.assertEqual(dtypes[3].lower(), 'decimal')

    def test_convert_header_to_column_name(self):
        test_cases = [
            ('header', 'header'),
            ('my header', 'my_header'),
            ('1_field', 'f_1_field'),
            ('freeze', 'freeze_a')
        ]

        for test in test_cases:
            self.assertEqual(convert_header_to_column_name(test[0]), test[1])

    def test_determine_x_and_y_fields(self):
        test_csv_file = io.StringIO(
            'lon,lat\n'
            '123.4,50.2\n'
        )
        row_set, _ = prepare_csv_rows(test_csv_file)
        self.assertEqual(determine_x_and_y_fields(row_set.columns), ('lon', 'lat'))

        test_csv_file = io.StringIO(
            'lon,something_else\n'
            '123.4,50.2\n'
        )
        row_set, _ = prepare_csv_rows(test_csv_file)
        self.assertEqual(determine_x_and_y_fields(row_set.columns), (None, None))
