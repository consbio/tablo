from io import BytesIO
from django.test import TestCase
from messytables import StringType, IntegerType, DecimalType

from tablo.csv_utils import prepare_csv_rows, EmptyType, convert_header_to_column_name, determine_x_and_y_fields


class TestCSVUtils(TestCase):

    def test_prepare_csv_rows(self):
        test_csv_file = BytesIO(
            b'header_one,header_two,header_three,header_four\n'
            b'one,1,,1\n'
            b'two,2,,2.1\n'
        )
        row_set = prepare_csv_rows(test_csv_file)
        first_row = list(row_set.sample)[0]
        self.assertEqual(first_row[0].type, StringType())
        self.assertEqual(first_row[1].type, IntegerType())
        self.assertEqual(first_row[2].type, EmptyType())
        self.assertEqual(first_row[3].type, DecimalType())

    def test_prepare_csv_rows_with_config(self):
        # Specifies String for the Empty Type
        csv_info = {
            'fieldNames': ['header_one', 'header_two', 'header_three', 'header_four'],
            'dataTypes': ['String', 'Integer', 'String', 'Decimal']
        }
        test_csv_file = BytesIO(
            b'header_one,header_two,header_three,header_four\n'
            b'one,1,,1\n'
            b'two,2,,2.1\n'
        )
        row_set = prepare_csv_rows(test_csv_file, csv_info)
        first_row = list(row_set.sample)[0]
        self.assertEqual(first_row[0].type, StringType())
        self.assertEqual(first_row[1].type, IntegerType())
        self.assertEqual(first_row[2].type, StringType())
        self.assertEqual(first_row[3].type, DecimalType())

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
        test_csv_file = BytesIO(
            b'lon,lat\n'
            b'123.4,50.2\n'
        )
        row_set = prepare_csv_rows(test_csv_file)
        first_row = list(row_set.sample)[0]
        self.assertEqual(determine_x_and_y_fields(first_row), ('lon', 'lat'))

        test_csv_file = BytesIO(
            b'lon,something_else\n'
            b'123.4,50.2\n'
        )
        row_set = prepare_csv_rows(test_csv_file)
        first_row = list(row_set.sample)[0]
        self.assertEqual(determine_x_and_y_fields(first_row), (None, None))
