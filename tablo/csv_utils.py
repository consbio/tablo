import csv
import datetime
import io
import re

from django.db.models.fields.files import FieldFile

import pandas as pd

POSTGRES_KEYWORDS = [
    'all', 'analyse', 'analyze', 'and', 'any', 'array', 'as', 'asc',
    'asymmetric', 'authorization', 'binary', 'both', 'case', 'cast', 'check', 'collate', 'collation',
    'column', 'concurrently', 'constraint', 'create', 'cross', 'current_catalog', 'current_date',
    'current_role', 'current_schema', 'current_time', 'current_timestamp', 'current_user', 'default',
    'deferrable', 'desc', 'distinct', 'do', 'else', 'end', 'except', 'false', 'fetch', 'for',
    'foreign', 'freeze', 'from', 'full', 'grant', 'group', 'having', 'ilike', 'in', 'initially',
    'inner', 'intersect', 'into', 'is', 'isnull', 'join', 'leading', 'left', 'limit', 'localtime',
    'localtimestamp', 'natural', 'not', 'notnull', 'null', 'offset', 'on', 'only', 'or', 'order',
    'outer', 'over', 'overlaps', 'placing', 'primary', 'references', 'returning', 'right', 'select',
    'session_user', 'similar', 'some', 'symmetric', 'table', 'then', 'to', 'trailing', 'true',
    'union', 'unique', 'user', 'using', 'variadic', 'verbose', 'when', 'where', 'window', 'with'
]

X_AND_Y_FIELDS = (
    ('lon', 'lat'),
    ('utm_e', 'utm_n'),
    ('utme', 'utmn'),
    ('east', 'north'),
    ('x_', 'y_')
)

DATE_FORMATS = (
    '%m/%d/%Y',
    '%m/%d/%y',
    '%d/%m/%Y',
    '%d/%m/%y',
    '%m-%d-%Y',
    '%m-%d-%y',
    '%d-%m-%Y',
    '%d-%m-%y',
    '%Y/%d/%m',
    '%y/%d/%m',
    '%Y/%m/%d',
    '%y/%m/%d',
    '%Y-%d-%m',
    '%y-%d-%m',
    '%Y-%m-%d',
    '%y-%m-%d'
)

def clean_header_row(header):
    # Strip Byte Order Mark from the beginning of the header row
    return header.lstrip('\ufeff')


def prepare_csv_rows(csv_file, csv_info=None):
    if isinstance(csv_file, str):
        with open(csv_file, 'r') as f:
            header_line = [clean_header_row(f.readline())]
    elif isinstance(csv_file, (io.BufferedIOBase, io.StringIO)):
        csv_file.seek(0)
        header_line = [clean_header_row(csv_file.readline())]
        csv_file.seek(0)
    elif isinstance(csv_file, (FieldFile, io.BytesIO)):
        csv_file.seek(0)
        header_line = [clean_header_row(csv_file.readline().decode())]
        csv_file.seek(0)
    else:
        raise TypeError('Invalid csv file')

    reader = csv.reader(header_line)
    headers = [c for c in next(reader) if c]  # remove empty column names

    kwargs = {
        'usecols': headers,
        'skip_blank_lines': True,
        'skipinitialspace': True
    }

    row_set = pd.read_csv(csv_file, dtype='object', **kwargs)

    row_set.rename(columns={c: convert_header_to_column_name(c) for c in row_set.columns}, inplace=True)

    if csv_info:
        date_fields = get_date_fields(csv_info)
        for field in date_fields:
            row_set[field] = row_set[field].astype('datetime64')

    row_set.index += 1
    data_types = infer_data_types(row_set)
    optional_fields = determine_optional_fields(row_set)
    x_field, y_field = determine_x_and_y_fields(row_set.columns)

    return {
        'row_set': row_set,
        'data_types': data_types,
        'optional_fields': optional_fields,
        'coord_fields': (x_field, y_field)
    }


def infer_data_types(row_set):
    data_types = []
    for c in row_set.columns:
        column_series = row_set[c]
        non_empty_rows = column_series[~column_series.isnull()]
        if not len(non_empty_rows):
            data_types.append('Empty')
            continue

        # If csv is loadded with csv_info, then given date columns are already parsed and we can continue
        if column_series.dtype.name.lower().startswith('date'):
            data_types.append('Date')
            continue

        first_value = column_series.loc[1]
        is_date_type = False

        for fmt in DATE_FORMATS:
            try:
                datetime.datetime.strptime(first_value, fmt)
                is_date_type = True
                data_types.append('Date')
                break
            except (ValueError, TypeError):
                pass

        if is_date_type:
            continue

        try:
            data_type = pd.to_numeric(non_empty_rows).dtype.name.lower()
            if 'int' in data_type:
                data_types.append('Integer')
            elif 'float' in data_type:
                data_types.append('Decimal')
        except ValueError:
            data_types.append('String')

    return data_types


def get_date_fields(csv_info):
    fields = csv_info['fieldNames']
    data_types = csv_info['dataTypes']
    return [fields[idx] for idx, dt in enumerate(data_types) if dt.lower() == 'date']


def determine_optional_fields(row_set):
    return list(c for c in row_set.columns if row_set[c].isnull().values.any())


def determine_x_and_y_fields(columns):
    x_field = None
    y_field = None

    for x_guess, y_guess in X_AND_Y_FIELDS:
        for column in columns:
            if column.lower().startswith(x_guess):
                x_field = column
            if column.lower().startswith(y_guess):
                y_field = column
        if x_field and y_field:
            break
        else:
            # Only a valid guess if both the x field and y field are defined
            x_field = None
            y_field = None

    return x_field, y_field


def convert_header_to_column_name(header):
    converted_header = header.lower()
    converted_header = converted_header.replace(' ', '_')
    converted_header = converted_header.replace('-', '_')
    converted_header = re.sub(r'\W', '', converted_header)
    converted_header = converted_header.strip('_')

    # Remove non-ascii characters
    converted_header = re.sub(r'[^\x00-\x7f]', '', converted_header)

    if converted_header[0].isdigit():
        converted_header = 'f_' + converted_header
    if converted_header in POSTGRES_KEYWORDS:
        converted_header += '_a'

    return converted_header


def prepare_row_set_for_import(row_set, csv_info):
    for idx, data_type in enumerate(row_set.dtypes):
        if data_type.name == 'object':
            column = row_set.columns[idx]
            row_set[column] = row_set[column].str.strip()

    for idx, column in enumerate(row_set.columns):
        # We do not need to update date fields, because they are parsed by pandas on import
        csv_data_type = csv_info['dataTypes'][idx].lower()
        if csv_data_type == 'integer':
            # Determine the smallest int type and use the relevant pandas nullable integer type
            non_empty_rows = row_set[column][~row_set[column].isnull()]
            int_type = pd.to_numeric(non_empty_rows, downcast='integer').dtype.name
            row_set[column] = pd.to_numeric(row_set[column]).astype(int_type.capitalize())
        elif csv_data_type == 'decimal':
            row_set[column] = pd.to_numeric(row_set[column], downcast='float')
        elif csv_data_type in ('string', 'empty'):
            row_set[column] = row_set[column].str.strip()

    return row_set
