import csv
import datetime
import io
import re

from django.db.models.fields.files import FieldFile

import numpy as np
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


def prepare_csv_rows(csv_file, csv_info=None):
    if isinstance(csv_file, str):
        with open(csv_file, 'r') as f:
            header_line = [f.readline()]
    elif isinstance(csv_file, io.BufferedIOBase) or isinstance(csv_file, io.StringIO):
        csv_file.seek(0)
        header_line = [csv_file.readline()]
        csv_file.seek(0)
    elif isinstance(csv_file, FieldFile) or isinstance(csv_file, io.BytesIO):
        csv_file.seek(0)
        header_line = [csv_file.readline().decode()]
        csv_file.seek(0)
    else:
        raise TypeError('Invalid csv file')

    reader = csv.reader(header_line)
    headers = list(filter(lambda c: c, next(reader)))  # remove empty column names

    kwargs = {
        'usecols': headers,
        'skip_blank_lines': True,
        'skipinitialspace': True
    }

    if csv_info:
        kwargs['dtype'], kwargs['parse_dates'] = types_from_config(csv_info)
        row_set = pd.read_csv(csv_file, **kwargs)
    else:
        row_set = pd.read_csv(csv_file, **kwargs)
        convert_date_columns(row_set)

    return row_set


def update_row_set_columns(row_set, csv_info, optional_fields=[]):
    converted_headers = map(convert_header_to_column_name, row_set.columns)
    optional_fields = list(map(convert_header_to_column_name, optional_fields))
    csv_info['fieldNames'] = list(map(convert_header_to_column_name, csv_info['fieldNames']))
    csv_info['xColumn'] = convert_header_to_column_name(csv_info['xColumn'])
    csv_info['yColumn'] = convert_header_to_column_name(csv_info['yColumn'])
    return row_set.rename(columns=dict(zip(row_set.columns, converted_headers))), csv_info, optional_fields


def types_from_config(csv_info):
    """
    Determines the type of the columns based on the csvInfo.dataTypes.
    This allows us to keep from guessing when the sender of the file knows more about the types than we do.
    """

    # np.object is used for str type
    convert_type = {
        'int64': np.int64,
        'object': np.object,
        'float64': np.float64,
        'datetime64[ns]': np.datetime64,
        'empty': np.object  # Sender doesn't know type either, default to Object
    }
    fields = csv_info['fieldNames']
    data_types = {}
    date_fields = []
    for idx, data_type in enumerate(csv_info['dataTypes']):
        data_type_lowered = data_type.lower()
        if data_type_lowered.startswith('date'):
            date_fields.append(fields[idx])
        else:
            data_types[fields[idx]] = convert_type[data_type_lowered]
    return data_types, date_fields


def convert_date_columns(df):
    date_columns = []
    for c in df.columns:
        first_valid_index = df[c].first_valid_index()
        if first_valid_index is not None:
            for fmt in DATE_FORMATS:
                try:
                    datetime.datetime.strptime(df[c].loc[first_valid_index], fmt)
                    date_columns.append(c)
                    break
                except ValueError:
                    pass
                except TypeError:
                    pass
    for c in date_columns:
        df[c] = df[c].astype(np.datetime64)


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
