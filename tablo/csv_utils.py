import re

from collections import defaultdict
from messytables import CSVTableSet, headers_guess, offset_processor, types_processor
from messytables import StringType, DecimalType, IntegerType, DateType, Cell
from messytables.compat23 import unicode_string
from messytables.dateparser import create_date_formats
from messytables.types import CellType

from itertools import zip_longest


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


def prepare_csv_rows(csv_file, csv_info=None):
    row_set = CSVTableSet(csv_file).tables[0]

    offset, headers = headers_guess(row_set.sample)
    headers = [convert_header_to_column_name(header) for header in (h for h in headers if h)]

    row_set.register_processor(headers_processor_remove_blank(headers))
    row_set.register_processor(offset_processor(offset + 1))

    DateType.formats = create_date_formats(day_first=False)

    if csv_info:
        types = types_from_config(row_set.sample, csv_info)
    else:
        types = type_guess(row_set.sample, strict=True)

    row_set.register_processor(types_processor(types))

    return row_set


def types_from_config(rows, csv_info):
    """
    Determines the type of the columns based on the csvInfo.dataTypes.
    This allows us to keep from guessing when the sender of the file knows more about the types than we do.
    """

    columns = []
    convert_type = {
        'integer': IntegerType,
        'string': StringType,
        'decimal': DecimalType,
        'date': DateType,
        'empty': StringType  # Sender doesn't know type either, default to String
    }

    for row in rows:
        for cell in row:
            name_index = csv_info['fieldNames'].index(cell.column.lower())
            data_type = convert_type[csv_info['dataTypes'][name_index].lower()]
            if data_type == DateType:
                columns.append(data_type(None))
            else:
                columns.append(data_type())

    return columns


def convert_header_to_column_name(header):
    converted_header = header.lower()
    converted_header = converted_header.replace(' ', '_')
    converted_header = converted_header.replace('-', '_')
    converted_header = re.sub('\W', '', converted_header)
    converted_header = converted_header.strip('_')

    # Remove non-ascii characters
    converted_header = re.sub('[^\x00-\x7f]', '', converted_header)

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
    """
    Removes any blank columns from the CSV file.
    Essentially, if the header is blank, don't add the column value.
    This prevents issues with blank columns in XLS and XLSX files.
    """

    def apply_headers(row_set, row):
        _row = []
        pairs = zip_longest(row, headers)
        for _, (cell, header) in enumerate(pairs):
            if cell is None:
                cell = Cell(None)
            cell.column = header
            if cell.column:
                _row.append(cell)
        return _row

    return apply_headers


class EmptyType(CellType):
    """ An empty cell """

    result_type = unicode_string
    guessing_weight = 0

    def cast(self, value):
        if value is None:
            return None
        if isinstance(value, self.result_type):
            return value
        try:
            return unicode_string(value)
        except UnicodeEncodeError:
            return str(value)


# We never want Boolean types, so exclude it from the defaults
TYPES = (EmptyType, StringType, DecimalType, IntegerType, DateType)


def type_guess(rows, types=TYPES, strict=False):
    """
    This is a modified version of the messyTables type_guess function.
    The modified version uses the EmptyType to signify that the field itself is empty.
    This allows us to differentitate between a field that had some String values and a field that had no values.

    The type guesser aggregates the number of successful conversions of each column to each type,
    weights them by a fixed type priority and selects the most probable type for each column based on that figure.
    It returns a list of ``CellType``. Empty cells are ignored.

    Strict means that a type will not be guessed if parsing fails for a single cell in the column.
    """

    type_instances = [i for t in types for i in t.instances()]
    guesses = []

    if strict:
        at_least_one_value = []
        for _, row in enumerate(rows):
            diff = len(row) - len(guesses)
            for _ in range(diff):
                typesdict = {}
                for data_type in type_instances:
                    typesdict[data_type] = 0
                guesses.append(typesdict)
                at_least_one_value.append(False)
            for ci, cell in enumerate(row):
                if not cell.value:
                    continue
                at_least_one_value[ci] = True
                for data_type in list(guesses[ci].keys()):
                    if not data_type.test(cell.value):
                        guesses[ci].pop(data_type)
        # no need to set guessing weights before this
        # because we only accept a data_type if it never fails
        for i, guess in enumerate(guesses):
            for data_type in guess:
                guesses[i][data_type] = data_type.guessing_weight
        # in case there were no values at all in the column,
        # we set the guessed data_type to empty
        for i, v in enumerate(at_least_one_value):
            if not v:
                guesses[i] = {EmptyType(): 0}
    else:
        for i, row in enumerate(rows):
            diff = len(row) - len(guesses)
            for _ in range(diff):
                guesses.append(defaultdict(int))
            for i, cell in enumerate(row):
                # add empty guess so that we have at least one guess
                guesses[i][EmptyType()] = guesses[i].get(EmptyType(), 0)
                if not cell.value:
                    continue
                for data_type in type_instances:
                    if data_type.test(cell.value):
                        guesses[i][data_type] += data_type.guessing_weight
    columns = []
    for guess in guesses:
        # this first creates an array of tuples because we want the types to be
        # sorted. Even though it is not specified, python chooses the first
        # element in case of a tie
        # See: http://stackoverflow.com/a/6783101/214950
        guesses_tuples = [(t, guess[t]) for t in type_instances if t in guess]
        columns.append(max(guesses_tuples, key=lambda t_n: t_n[1])[0])

    return columns
