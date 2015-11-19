import re

from messytables import CSVTableSet, headers_guess, offset_processor, types_processor, type_guess
from messytables import StringType, DecimalType, IntegerType, DateType, Cell
from messytables.dateparser import create_date_formats

from itertools import zip_longest


POSTGRES_KEYWORDS = ['all', 'analyse', 'analyze', 'and', 'any', 'array', 'as', 'asc',
                     'asymmetric', 'authorization', 'binary', 'both', 'case', 'cast', 'check', 'collate', 'collation',
                     'column', 'concurrently', 'constraint', 'create', 'cross', 'current_catalog', 'current_date',
                     'current_role', 'current_schema', 'current_time', 'current_timestamp', 'current_user', 'default',
                     'deferrable', 'desc', 'distinct', 'do', 'else', 'end', 'except', 'false', 'fetch', 'for',
                     'foreign', 'freeze', 'from', 'full', 'grant', 'group', 'having', 'ilike', 'in', 'initially',
                     'inner', 'intersect', 'into', 'is', 'isnull', 'join', 'leading', 'left', 'limit', 'localtime',
                     'localtimestamp', 'natural', 'not', 'notnull', 'null', 'offset', 'on', 'only', 'or', 'order',
                     'outer', 'over', 'overlaps', 'placing', 'primary', 'references', 'returning', 'right', 'select',
                     'session_user', 'similar', 'some', 'symmetric', 'table', 'then', 'to', 'trailing', 'true',
                     'union', 'unique', 'user', 'using', 'variadic', 'verbose', 'when', 'where', 'window', 'with']

X_AND_Y_FIELDS = (
    ('lon', 'lat'),
    ('utm_e', 'utm_n'),
    ('utme', 'utmn'),
    ('east', 'north'),
    ('x_', 'y_')
)

def prepare_csv_rows(csv_file):
    row_set = CSVTableSet(csv_file).tables[0]

    offset, headers = headers_guess(row_set.sample)
    headers = [convert_header_to_column_name(header) for header in (h for h in headers if h)]

    row_set.register_processor(headers_processor_remove_blank(headers))
    row_set.register_processor(offset_processor(offset + 1))

    DateType.formats = create_date_formats(day_first=False)

    # We are never wanting boolean types, so remove that from the default list
    eligible_types = [StringType, DecimalType, IntegerType, DateType]
    types = type_guess(row_set.sample, types=eligible_types, strict=True)

    row_set.register_processor(types_processor(types))

    return row_set


def convert_header_to_column_name(header):
    converted_header = header.lower()
    converted_header = converted_header.replace(' ', '_')
    converted_header = converted_header.replace('-', '_')
    converted_header = re.sub('\W', '', converted_header)
    converted_header.strip('_')
    if converted_header[0].isdigit():
        converted_header = 'f_' + converted_header
    if converted_header in POSTGRES_KEYWORDS:
        converted_header += '_a'
    return converted_header


def determine_x_and_y_fields(row):
    x_field = None
    y_field = None

    for x_guess, y_guess in X_AND_Y_FIELDS:
        for cell in row:
            if cell.column.startswith(x_guess):
                x_field = cell.column
            if cell.column.startswith(y_guess):
                y_field = cell.column
        if x_field and y_field:
            break
        else:
            # Only a valid guess if both the x field and y field are defined
            x_field = None
            y_field = None

    return x_field, y_field

def headers_processor_remove_blank(headers):
    """ Removes any blank columns from the CSV file. Essentially, if the header is blank, don't add the column
        value. This prevents issues with blank columns in XLS and XLSX files."""

    def apply_headers(row_set, row):
        _row = []
        pairs = zip_longest(row, headers)
        for i, (cell, header) in enumerate(pairs):
            if cell is None:
                cell = Cell(None)
            cell.column = header
            if cell.column:
                _row.append(cell)
        return _row
    return apply_headers