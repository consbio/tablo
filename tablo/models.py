import calendar
import json
import logging
import re
import uuid
import sqlparse

from django.conf import settings
from django.db import models, DatabaseError, connection
from django.db.models import signals

from sqlparse.tokens import Token, Punctuation, Keyword, Operator

from tablo.utils import get_jenks_breaks, dictfetchall
from tablo.geom_utils import Extent, SpatialReference

TEMPORARY_FILE_LOCATION = getattr(settings, 'TABLO_TEMPORARY_FILE_LOCATION', '/ncdjango/tmp')

POSTGIS_ESRI_FIELD_MAPPING = {
    'BigIntegerField': 'esriFieldTypeInteger',
    'IntegerField': 'esriFieldTypeInteger',
    'TextField': 'esriFieldTypeString',
    'FloatField': 'esriFieldTypeDouble',
    'DateField': 'esriFieldTypeString',
    'Geometry': 'esriFieldTypeGeometry',
    'Unknown': 'esriFieldTypeString',
    'OID': 'esriFieldTypeOID'
}

IMPORT_SUFFIX = '_import'
PRIMARY_KEY_NAME = 'db_id'
TABLE_NAME_PREFIX = 'db_'
POINT_FIELD_NAME = 'dbasin_geom'
SOURCE_DATASET_FIELD_NAME = 'source_dataset'
WEB_MERCATOR_SRID = 3857

# Adjusted global extent -- adjusted to better fit screen layout. Same as mapController.getAdjustedGlobalExtent().
ADJUSTED_GLOBAL_EXTENT = Extent({
    'xmin': -20000000,
    'ymin': -7000000,
    'xmax': 20000000,
    'ymax': 18000000,
    'spatialReference': {'wkid': WEB_MERCATOR_SRID}
})

logger = logging.getLogger(__name__)


class FeatureService(models.Model):
    id = models.AutoField(auto_created=True, primary_key=True)
    description = models.TextField(null=True)
    copyright_text = models.TextField(null=True)
    spatial_reference = models.CharField(max_length=255)
    _initial_extent = models.TextField(db_column='initial_extent', null=True)
    _full_extent = models.TextField(db_column='full_extent', null=True)
    units = models.CharField(max_length=255, null=True)
    allow_geometry_updates = models.BooleanField(default=False)

    @property
    def initial_extent(self):
        if self._initial_extent is None and self.featureservicelayer_set.all():
            self._initial_extent = json.dumps(determine_extent(self.featureservicelayer_set.all()[0].table))
            self.save()
        return self._initial_extent

    @property
    def full_extent(self):
        if self._full_extent is None and self.featureservicelayer_set.all():
            self._full_extent = json.dumps(determine_extent(self.featureservicelayer_set.all()[0].table))
            self.save()
        return self._full_extent

    @property
    def dataset_id(self):
        if self.featureservicelayer_set.all():
            dataset_id = self.featureservicelayer_set.all()[0].table
            return dataset_id.replace(TABLE_NAME_PREFIX, '').replace(IMPORT_SUFFIX, '')
        return 0

    def finalize(self, dataset_id):
        # Renames the table associated with the feature service to remove the IMPORT tag
        fs_layer = self.featureservicelayer_set.first()
        fs_layer.table = TABLE_NAME_PREFIX + dataset_id
        fs_layer.save()

        old_table_name = TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX
        new_table_name = TABLE_NAME_PREFIX + dataset_id

        with connection.cursor() as c:
            c.execute('DROP TABLE IF EXISTS {new_table_name}'.format(
                new_table_name=new_table_name
            ))

            c.execute('ALTER TABLE {old_table_name} RENAME TO {new_table_name}'.format(
                old_table_name=old_table_name,
                new_table_name=new_table_name
            ))

            c.execute('ALTER INDEX {old_table_name}_geom_index RENAME TO {new_table_name}_geom_index'.format(
                old_table_name=old_table_name,
                new_table_name=new_table_name
            ))


class FeatureServiceLayer(models.Model):
    id = models.AutoField(auto_created=True, primary_key=True)
    service = models.ForeignKey(FeatureService)
    layer_order = models.IntegerField()
    table = models.CharField(max_length=255)
    name = models.CharField(max_length=255, null=True)
    description = models.TextField(null=True)
    object_id_field = models.CharField(max_length=255, default=PRIMARY_KEY_NAME)
    global_id_field = models.CharField(max_length=255, default=PRIMARY_KEY_NAME)
    display_field = models.CharField(max_length=255, default=PRIMARY_KEY_NAME)
    geometry_type = models.CharField(max_length=255)
    _extent = models.TextField(db_column='extent', null=True)
    supports_time = models.BooleanField(default=False)
    start_time_field = models.CharField(max_length=255, null=True)
    _time_extent = models.TextField(null=True, db_column='time_extent')
    time_interval = models.TextField(null=True)
    time_interval_units = models.CharField(max_length=255, null=True)
    drawing_info = models.TextField()

    @property
    def extent(self):
        if self._extent is None:
            self._extent = json.dumps(determine_extent(self.table))
            self.save()
        return self._extent

    @property
    def time_extent(self):
        if not self.supports_time:
            return '[]'

        if self._time_extent is None:
            self._time_extent = self._get_time_extent()
        return self._time_extent

    def _get_time_extent(self):
        query = 'SELECT MIN({date_field}), MAX({date_field}) FROM {table_name}'.format(
            date_field=self.start_time_field,
            table_name=self.table
        )

        with get_cursor() as c:
            c.execute(query)
            min_date, max_date = (calendar.timegm(x.timetuple()) * 1000 for x in c.fetchone())

        return json.dumps([min_date, max_date])

    @property
    def fields(self):
        fields = []
        with connection.cursor() as c:
            c.execute('select * from {0} limit 1'.format(self.table))
            # c.description won't be populated without first running the query above
            for field_info in c.description:
                if field_info.name == 'db_id':
                    field_type = 'OID'
                elif field_info.type_code in connection.introspection.data_types_reverse:
                    field_type = connection.introspection.data_types_reverse[field_info.type_code]
                elif field_info.name == POINT_FIELD_NAME:
                    field_type = 'Geometry'
                else:
                    field_type = 'Unknown'

                fields.append({
                    'name': field_info.name,
                    'alias': field_info.name,
                    'type': POSTGIS_ESRI_FIELD_MAPPING[field_type],
                    'nullable': field_info.null_ok,
                    'editable': False
                })

        return fields

    @property
    def time_info(self):
        if self.start_time_field:
            return {
                'startTimeField': self.start_time_field,
                'timeExtent': json.loads(self.time_extent),
                'timeInterval': int(self.time_interval),
                'timeIntervalUnits': self.time_interval_units
            }
        return None

    def perform_query(self, **kwargs):
        additional_where_clause = kwargs.get('additional_where_clause')
        start_time = kwargs.get('start_time')
        end_time = kwargs.get('end_time')
        extent = kwargs.get('extent')
        return_fields = kwargs.get('return_fields', [])
        return_geometry = kwargs.get('return_geometry', True)
        only_return_count = kwargs.get('only_return_count', False)

        # These are the possible points of SQL injection. All other dynamically composed pieces of SQL are
        # constructed using items within the database, or are escaped using the database engine.
        if not self._validate_fields(return_fields) or not self._validate_where_clause(additional_where_clause):
            raise ValueError("Invalid query parameters")

        if only_return_count:
            return_fields = ['count(*)']
        elif return_geometry:
            return_fields.append('ST_AsText(dbasin_geom)')

        params = []   # Collect parameters to the query that we can let the SQL engine escape for us
        where = '1=1'
        if additional_where_clause:
            # Need to escape any % in like clauses so they don't get in the way of query parameters later
            where = additional_where_clause.replace('%', '%%')
        if start_time:
            if start_time == end_time:
                where += " AND {layer_time_field} = %s".format(
                    layer_time_field=self.start_time_field
                )
                params.append(start_time)
            else:
                where += " AND {layer_time_field} BETWEEN %s AND %s".format(
                    layer_time_field=self.start_time_field
                )
                params.append(start_time)
                params.append(end_time)
        elif self.start_time_field and not only_return_count and not additional_where_clause:
            # If layer has a time component, default is to show first time step
            where += " AND {layer_time_field} = (SELECT MIN({layer_time_field}) FROM {table})".format(
                layer_time_field=self.start_time_field,
                table=self.table
            )

        if extent:
            where += ' AND ST_Intersects(dbasin_geom, ST_GeomFromText(%s, 3857)) '
            params.append(extent.as_sql_poly())

        with get_cursor() as c:
            # where clause may contain references to table and fields
            query_clause = 'SELECT {fields} FROM {table} WHERE ' + where
            query_clause = query_clause.format(
                fields=','.join(return_fields),
                table=self.table
            )
            logger.info('Query: %s', query_clause)
            c.execute(query_clause, params)
            response = dictfetchall(c)

        return response

    def _validate_where_clause(self, where):
        if where is None or where == '1=1':
            return True

        parsed_where_clause = sqlparse.parse('WHERE {where_clause}'.format(where_clause=where))
        if len(parsed_where_clause) != 1:
            # Where clause should only contain one statement (the WHERE clause), additional statements would
            # be attempts at SQL injection
            return False
        else:
            flat_clause = parsed_where_clause[0].flatten()
            tokens_no_whitespace = [token for token in flat_clause if not token.is_whitespace() and token.ttype != Punctuation and token.ttype != Token.Literal.Number.Integer]
            query_fields = []
            for index, token in enumerate(tokens_no_whitespace):
                if token.ttype in (Keyword, Operator.Comparison) and token.value not in ('WHERE', 'AND', 'OR', 'IS', 'NOT NULL', 'NULL'):
                    query_fields.append(tokens_no_whitespace[index-1].value.replace('"', ''))

            valid_fields = self._validate_fields(query_fields)
            return valid_fields

    def _validate_fields(self, fields):
        test_fields = [field for field in fields if field != '*']
        return len(test_fields) == 0 or set(test_fields).issubset([field['name'] for field in self.fields])

    def get_unique_values(self, field):

        if not self._validate_fields([field]):
            raise ValueError('Invalid field')

        unique_values = []
        with get_cursor() as c:
            c.execute('SELECT distinct {field_name} FROM {table} ORDER BY {field_name}'.format(
                table=self.table, field_name=field
            ))
            for row in c.fetchall():
                unique_values.append(row[0])
        return unique_values

    def get_equal_breaks(self, field, break_count):

        if not self._validate_fields([field]):
            raise ValueError('Invalid field')

        breaks = []

        with get_cursor() as c:
            c.execute('SELECT MIN({field_name}), MAX({field_name}) FROM {table}'.format(
                table=self.table, field_name=field
            ))
            min_value, max_value = c.fetchone()

        step = (max_value - min_value) / break_count
        low_value = min_value
        for i in range(break_count):
            breaks.append(low_value)
            low_value += step

        breaks.append(max_value)

        return breaks

    def get_quantile_breaks(self, field, break_count):

        if not self._validate_fields([field]):
            raise ValueError('Invalid field')

        sql_statement = """
            SELECT all_data.{field} FROM
                (SELECT ROW_NUMBER() OVER (ORDER BY {field}) AS row_number,
                        {field}
                   FROM {table}
                  WHERE {field} IS NOT NULL
                  ORDER BY {field}) all_data,
                (SELECT ROUND((COUNT(*)/{break_count}),0) AS how_many
                   FROM {table} serviceTable
                  WHERE serviceTable.{field} IS NOT NULL) count_table
            WHERE MOD(row_number,how_many)=0
            ORDER BY all_data.{field}""".format(
            field=field,
            table=self.table,
            break_count=break_count
        )
        values = []

        with get_cursor() as c:
            c.execute('SELECT MIN({field_name}), MAX({field_name}) FROM {table}'.format(
                table=self.table,
                field_name=field
            ))
            minimum, maximum = c.fetchone()

            values.append(minimum)
            c.execute(sql_statement)
            for row in c.fetchall():
                values.append(row[0])
            if values[-1] != maximum:
                values[-1] = maximum

        return values

    def get_natural_breaks(self, field, break_count):

        if not self._validate_fields([field]):
            raise ValueError('Invalid field')

        sql_statement = """SELECT service_table.{field} FROM
                            (SELECT ROW_NUMBER() OVER (ORDER BY {field}) AS row_number,
                            {primary_key}
                                   FROM {table}
                                  WHERE {field} IS NOT NULL
                                  ORDER BY {field}) all_data,
                                (SELECT count(*) AS total,
                                        CASE WHEN COUNT(*) < {num_samples} THEN 1
                                        ELSE ROUND((COUNT(*)/{num_samples}),0)
                                        END AS how_many
                                   FROM {table}
                                  WHERE {field} IS NOT NULL) count_table,
                                {table} service_table
                            WHERE (MOD(row_number,how_many)=0 OR row_number = 1 OR row_number = total)
                              AND service_table.{primary_key}=all_data.{primary_key}
                            ORDER BY service_table.{field}""".format(
            field=field,
            primary_key=self.object_id_field,
            table=self.table,
            num_samples=1000
        )

        values = []
        with get_cursor() as c:
            c.execute(sql_statement)
            values = [row[0] for row in c.fetchall()]

            c.execute('SELECT MIN({field_name}), MAX({field_name}) FROM {table}'.format(
                table=self.table, field_name=field
            ))
            minimum, maximum = c.fetchone()

            values[0] = minimum
            values[-1] = maximum

        return get_jenks_breaks(values, break_count)


def delete_data_table(sender, instance, **kwargs):
    with get_cursor() as c:
        c.execute('DROP table IF EXISTS {table_name}'.format(table_name=instance.table))


signals.pre_delete.connect(delete_data_table, sender=FeatureServiceLayer)


def copy_data_table_for_import(dataset_id):

    drop_table_command = 'DROP TABLE IF EXISTS {table_name}'.format(
        table_name=TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX
    )
    copy_table_command = 'CREATE TABLE {import_table} AS TABLE {data_table}'.format(
        import_table = TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX,
        data_table = TABLE_NAME_PREFIX + dataset_id
    )

    index_command = 'CREATE INDEX {table_name}_geom_index ON {table_name} USING gist({column_name})'.format(
        table_name=TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX,
        column_name=POINT_FIELD_NAME
    )

    with get_cursor() as c:
        c.execute(drop_table_command)
        c.execute(copy_table_command)
        c.execute(index_command)

    return TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX


def create_database_table(row, dataset_id):
    table_name = TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX
    drop_table_command = 'DROP TABLE IF EXISTS {table_name}'.format(table_name=table_name)
    create_table_command = 'CREATE TABLE {table_name} ({primary_key} serial NOT NULL PRIMARY KEY'.format(
        table_name=table_name,
        primary_key=PRIMARY_KEY_NAME
    )
    type_conversion = {
        'decimal': 'double precision',
        'date': 'date',
        'integer': 'integer',
        'string': 'text',
        'xlocation': 'double precision',
        'ylocation': 'double precision',
        'dropdownEdit': 'text',
        'dropdown': 'text',
        'double': 'double'
    }
    for cell in row:
        create_table_command += ', {field_name} {type}'.format(
            field_name=cell.column,
            type=type_conversion[re.sub(r'\([^)]*\)', '', str(cell.type).lower())]
        )
    create_table_command += ');'

    try:
        with get_cursor() as c:
            c.execute(drop_table_command)
            c.execute(create_table_command)
    except DatabaseError:
        raise

    return table_name


def create_aggregate_database_table(row, dataset_id):
    row.append(Column(column=SOURCE_DATASET_FIELD_NAME, type='string'))
    table_name = create_database_table(row, dataset_id)
    row.pop() # remove the appended column
    return table_name


def populate_aggregate_table(aggregate_table_name, columns, datasets_ids_to_combine):
    delete_command = 'DELETE FROM {0}'.format(aggregate_table_name)

    all_commands = [delete_command]
    for dataset_id in datasets_ids_to_combine:
        insert_command = (
            'INSERT INTO {table_name} ({definition_fields}, {source_dataset}, {spatial_field}) '
            'SELECT {definition_fields}, {dataset_id}, {spatial_field} FROM {dataset_table_name}'
        ).format(
            table_name=aggregate_table_name,
            definition_fields=','.join([column.column for column in columns]),
            source_dataset=SOURCE_DATASET_FIELD_NAME,
            dataset_id="'{0}'".format(dataset_id),
            dataset_table_name=TABLE_NAME_PREFIX + dataset_id,
            spatial_field=POINT_FIELD_NAME
        )
        logger.info(insert_command)
        all_commands.append(insert_command)

    with get_cursor() as c:
        for command in all_commands:
            c.execute(command)


def populate_data(table_name, row_set):
    first_row = next(row_set.sample)
    insert_command = 'INSERT INTO {table_name} ({field_list}) VALUES '.format(
        table_name=table_name,
        field_list=','.join([cell.column for cell in first_row])
    )

    with get_cursor() as c:
        header_skipped = False
        values_parenthetical = '({values})'.format(values=','.join(['%s' for cell in first_row]))
        values_list = []
        for row in row_set:
            if not header_skipped:
                header_skipped = True
                continue
            individual_insert_command = c.mogrify(values_parenthetical, [cell.value for cell in row]).decode('utf-8')
            values_list.append(individual_insert_command)

        c.execute(insert_command + ','.join(values_list))


def add_definition_fields(table_name, fields):

    alter_commands = []
    for field in fields:
        db_type = field.get('type')
        name = field.get('name')
        required = field.get('required', False)
        value = field.get('value')

        alter_command = 'ALTER TABLE {table_name} ADD COLUMN {field_name} {db_type}{not_null} DEFAULT {value}'.format(
            table_name=table_name,
            field_name=name,
            db_type=db_type,
            not_null=' NOT NULL' if required else '',
            value=value if db_type != 'text' else "'{0}'".format(value)
        )

        alter_commands.append(alter_command)

    with get_cursor() as c:
        for command in alter_commands:
            c.execute(command)


def add_point_column(dataset_id, is_import=True):

    with get_cursor() as c:
        add_command = "SELECT AddGeometryColumn ('{schema}', '{table_name}', '{column_name}', {srid}, '{type}', {dimension})".format(
            schema='public',
            table_name=TABLE_NAME_PREFIX + dataset_id + (IMPORT_SUFFIX if is_import else ''),
            column_name=POINT_FIELD_NAME,
            srid=WEB_MERCATOR_SRID,
            type='POINT',
            dimension=2
        )
        c.execute(add_command)

        index_command = 'CREATE INDEX {table_name}_geom_index ON {table_name} USING gist({column_name})'.format(
            table_name=TABLE_NAME_PREFIX + dataset_id + (IMPORT_SUFFIX if is_import else ''),
            column_name=POINT_FIELD_NAME
        )
        c.execute(index_command)


def populate_point_data(id, csv_info, is_import=True):

    srid = csv_info['srid']

    make_point_command = 'ST_SetSRID(ST_MakePoint({x_column}, {y_column}), {srid})'.format(
        x_column=csv_info['xColumn'],
        y_column=csv_info['yColumn'],
        srid=srid
    )

    if srid != WEB_MERCATOR_SRID:
        make_point_command = 'ST_Transform({original_command}, {geo_srid})'.format(
            original_command=make_point_command,
            geo_srid=WEB_MERCATOR_SRID
        )

    update_command = 'UPDATE {table_name} SET {field_name} = {make_point_command}'.format(
        table_name=TABLE_NAME_PREFIX + id + (IMPORT_SUFFIX if is_import else ''),
        field_name=POINT_FIELD_NAME,
        make_point_command=make_point_command
    )

    clear_null_command = 'DELETE FROM {table_name} WHERE {field_name} IS NULL'.format(
        table_name=TABLE_NAME_PREFIX + id + (IMPORT_SUFFIX if is_import else ''),
        field_name=POINT_FIELD_NAME,
    )

    with get_cursor() as c:
        c.execute(update_command)
        c.execute(clear_null_command)


def determine_extent(table):

        try:
            query = 'SELECT ST_Expand(CAST(ST_Extent({field_name}) AS box2d), 1000) AS box2d FROM {table_name}'.format(
                field_name=POINT_FIELD_NAME,
                table_name=table
            )

            with get_cursor() as c:
                c.execute(query)
                extent_box = c.fetchone()[0]
                if extent_box:
                    extent = Extent.from_sql_box(extent_box, SpatialReference({'wkid': WEB_MERCATOR_SRID}))
                else:
                    extent = ADJUSTED_GLOBAL_EXTENT

        except DatabaseError as error:
            logger.excdeption('Error generating extent for table {0}, returning adjusted global extent'.format(table))
            # Default to adjusted global extent if there is an error, similar to the one we present on the map page
            extent = ADJUSTED_GLOBAL_EXTENT

        return extent.as_dict()


def get_cursor():
    return connection.cursor()


class Column(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)


class TemporaryFile(models.Model):
    """A temporary file upload"""

    uuid = models.CharField(max_length=36, default=uuid.uuid4)
    date = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=100)
    filesize = models.BigIntegerField()
    file = models.FileField(upload_to=TEMPORARY_FILE_LOCATION, max_length=1024)

    @property
    def extension(self):
        if self.filename.find(".") != -1:
            return self.filename[self.filename.rfind(".")+1:]
        else:
            return ""
