import calendar
import json
import logging
import re
import uuid
import sqlparse

from datetime import datetime
from django.conf import settings
from django.db import models, DatabaseError, connection
from django.db.models import signals
from django.utils.datastructures import OrderedSet
from sqlparse.tokens import Token

from tablo.utils import get_jenks_breaks, dictfetchall
from tablo.geom_utils import Extent, SpatialReference


TEMPORARY_FILE_LOCATION = getattr(settings, 'TABLO_TEMPORARY_FILE_LOCATION', '/ncdjango/tmp')

POSTGIS_ESRI_FIELD_MAPPING = {
    'bigint': 'esriFieldTypeInteger',
    'boolean': 'esriFieldTypeSmallInteger',
    'integer': 'esriFieldTypeInteger',
    'text': 'esriFieldTypeString',
    'character': 'esriFieldTypeString',
    'character varying': 'esriFieldTypeString',
    'double precision': 'esriFieldTypeDouble',
    'date': 'esriFieldTypeDate',
    'timestamp without time zone': 'esriFieldTypeDate',
    'Geometry': 'esriFieldTypeGeometry',
    'Unknown': 'esriFieldTypeString',
    'OID': 'esriFieldTypeOID'
}

IMPORT_SUFFIX = '_import'
TABLE_NAME_PREFIX = 'db_'
PRIMARY_KEY_NAME = 'db_id'
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


def get_fields(for_table):
    fields = []
    with connection.cursor() as c:
        c.execute(
            ' '.join((
                'SELECT column_name, is_nullable, data_type',
                'FROM information_schema.columns',
                'WHERE table_name = %s',
                'ORDER BY column_name;'
            )),
            [for_table]
        )
        # c.description won't be populated without first running the query above
        for field_info in c.fetchall():
            field_type = field_info[2]
            fields.append({
                'name': field_info[0],
                'alias': field_info[0],
                'type': POSTGIS_ESRI_FIELD_MAPPING.get(field_type),
                'nullable': True if field_info[1] == 'YES' else False,
                'editable': True
            })

    return fields


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

    _fields = None
    _related_fields = None
    _relations = None

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

        # TODO: Remove fields from database if we really don't want to continue using them
        return self._get_time_extent()

    def get_raw_time_extent(self):
        query = 'SELECT MIN({date_field}), MAX({date_field}) FROM {table_name}'.format(
            date_field=self.start_time_field,
            table_name=self.table
        )

        with get_cursor() as c:
            c.execute(query)
            min_date, max_date = (calendar.timegm(x.timetuple()) * 1000 for x in c.fetchone())

        return [min_date, max_date]

    def _get_time_extent(self):
        return json.dumps(self.get_raw_time_extent())

    @property
    def fields(self):
        if self._fields is None:

            fields = get_fields(self.table)
            for field in fields:
                if field['name'] == 'db_id':
                    field['type'] = 'esriFieldTypeOID'
                elif field['name'] == POINT_FIELD_NAME:
                    field['type'] = 'esriFieldTypeGeometry'
            self._fields = fields

        return self._fields

    @property
    def relations(self):
        if self._relations is None:
            self._relations = self.featureservicelayerrelations_set.all()
        return self._relations

    @property
    def related_fields(self):
        if self._related_fields is None:

            self._related_fields = {}
            for field in (f for r in self.relations for f in r.fields):
                field_key = field['alias']  # Will be related_title.field
                self.related_fields[field_key] = field

        return self._related_fields

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

    def perform_query(self, limit=0, offset=0, **kwargs):
        count_only = kwargs.pop('count_only', False)
        ids_only = kwargs.pop('ids_only', False)
        return_fields = kwargs.get('return_fields', ['*'])
        return_geometry = kwargs.get('return_geometry', True)
        out_sr = kwargs.get('out_sr') or WEB_MERCATOR_SRID

        additional_where_clause = kwargs.get('additional_where_clause')
        additional_where_clause = additional_where_clause.replace('"', '') if additional_where_clause else None

        order_by_fields = kwargs.get('order_by_fields', [])

        # These are the possible points of SQL injection. All other dynamically composed pieces of SQL are
        # constructed using items within the database, or are escaped using the database engine.

        valid_select_fields = ids_only or self._validate_fields(return_fields)
        valid_where_clause = self._validate_where_clause(additional_where_clause)
        valid_order_by_fields = ids_only or self._validate_fields(order_by_fields)

        if not (valid_select_fields and valid_where_clause and valid_order_by_fields):
            raise ValueError('Invalid query parameters')

        if count_only:
            select_fields = 'COUNT(0)'
        elif ids_only:
            return_fields = order_by_fields = [self.object_id_field]
            select_fields = 'DISTINCT {0}'.format(self._alias_fields(return_fields))
        else:
            select_fields = self._expand_fields(return_fields)
            if return_geometry:
                select_fields += ', ST_AsText(ST_Transform("source"."dbasin_geom", {0}))'.format(out_sr)

        join, related_tables = self._build_join_clause(return_fields, additional_where_clause)
        where, query_params = self._build_where_clause(additional_where_clause, count_only, **kwargs)
        order_by = '' if count_only else self._build_order_by_clause(
            fields=order_by_fields, related_tables=(None if ids_only else related_tables)
        )

        with get_cursor() as c:
            query_clause = 'SELECT {fields} FROM "{table}" AS "source" {join} {where} {order_by} {limit_offset}'
            query_clause = query_clause.format(
                fields=select_fields, table=self.table, join=join.strip(), where=where.strip(), order_by=order_by,
                limit_offset='LIMIT {limit} OFFSET {offset}'.format(limit=limit, offset=offset)
            )
            c.execute(query_clause, query_params)
            data = dictfetchall(c)

        return data

    def _alias_fields(self, fields):
        """ Delimit and alias fields for query in double quotes, but ignore '*' """

        if not fields:
            return '"source".*'
        elif isinstance(fields, str):
            fields = [fields]

        aliased_fields = [f if '.' in f else 'source.{0}'.format(f) for f in fields]
        quoted_fields = '", "'.join('"."'.join(f.split('.')) for f in aliased_fields).join('""')

        return quoted_fields.replace('"*"', '*')

    def _expand_fields(self, fields, alias_only=False):
        """ Expand '*' in fields to those that will be queried, and optionally alias them to avoid clashes """

        if not any('.' in f for f in fields):
            return self._alias_fields(fields)

        fields_to_expand = [self.object_id_field]
        fields_to_expand.extend(r.source_column for r in self.relations)

        for field in fields:
            if field == '*':
                fields_to_expand.extend(f['name'] for f in self.fields)
            elif field.endswith('.*'):
                related_prefix = field[:-1]
                fields_to_expand.extend(f for f in self.related_fields if f.startswith(related_prefix))
            else:
                fields_to_expand.append(field)

        field_format = '"{1}"' if alias_only else '{0} AS "{1}"'

        return ', '.join(field_format.format(self._alias_fields(f), f) for f in OrderedSet(fields_to_expand))

    def _build_join_clause(self, fields, where, **kwargs):
        if not fields and where is None:
            return '', []
        elif where is None:
            query_fields = set(fields)
        else:
            query_fields = set(fields).union(self._parse_where_clause(where)[0])

        join_tables = query_fields.intersection(self.related_fields.keys())   # Filter by available related fields
        join_tables = join_tables.union(f for f in query_fields if '*' in f)  # Ensure wildcard fields are included
        join_tables = set(f[:f.index('.')] for f in join_tables if '.' in f)  # Derive distinct table prefixes
        join_clause = ''

        relations = self.relations.filter(related_title__in=join_tables)

        for relation in relations:
            join_clause += ' LEFT OUTER JOIN "{table}" AS "{related_title}"'.format(
                table=relation.table, related_title=relation.related_title
            )
            join_clause += ' ON "source"."{source}" = "{related_title}"."{target}"'.format(
                source=relation.source_column, related_title=relation.related_title, target=relation.target_column
            )

        return join_clause, [r.related_title for r in relations]

    def _build_where_clause(self, where, count_only, **kwargs):
        """ :return: a Python format where clause with corresponding params for the SQL engine to escape """

        start_time = kwargs.get('start_time')
        end_time = kwargs.get('end_time')

        if where is None:
            where_clause = 'WHERE 1=1'
        else:
            where_clause = ''

            for token in sqlparse.parse('WHERE {0}'.format(where.replace('%', '%%')))[0].flatten():
                if token.ttype != Token.Name:
                    where_clause += token.value
                elif token.value != token.parent.value:
                    # Token is aliased: just write the segments as they come
                    where_clause += token.value.strip('"').join('""')
                else:
                    # Token is not aliased if parent doesn't include it: add source alias
                    where_clause += '"source"."{field}"'.format(field=token.value.strip('"'))

        query_params = []

        if self.start_time_field:
            layer_time_field = '"source"."{time_field}"'.format(time_field=self.start_time_field)

            if start_time:
                if start_time == end_time:
                    where_clause += ' AND {time_field} = %s'.format(time_field=layer_time_field)
                    query_params.append(start_time)
                else:
                    where_clause += ' AND {time_field} BETWEEN %s AND %s'.format(time_field=layer_time_field)
                    query_params.append(start_time)
                    query_params.append(end_time)
            elif where is None and not count_only:
                # If layer has a time component, default is to show first time step
                where_clause += ' AND {time_field} = (SELECT MIN({subquery_time_field}) FROM "{table}")'.format(
                    time_field=layer_time_field,
                    subquery_time_field=self.start_time_field,
                    table=self.table
                )

        if kwargs.get('object_ids'):
            object_ids = kwargs['object_ids']

            where_clause += ' AND "source"."{primary_key}" IN ({object_id_list})'.format(
                primary_key=PRIMARY_KEY_NAME,
                object_id_list=','.join(['%s' for obj_id in object_ids]),
            )
            for obj_id in object_ids:
                query_params.append(obj_id)

        if kwargs.get('extent'):
            where_clause += ' AND ST_Intersects("source"."dbasin_geom", ST_GeomFromText(%s, 3857)) '
            query_params.append(kwargs['extent'].as_sql_poly())

        return where_clause, query_params

    def _build_order_by_clause(self, fields, related_tables=None):
        order_by_clause = 'ORDER BY {fields}'

        def insert_field(field_list, field, index):
            if field not in field_list:
                field_list.insert(0, field)
            elif field_list[0] != field:
                field_list.remove(field)
                field_list.insert(0, field)

        order_by_fields = list(fields or '')

        if related_tables is None:
            if not order_by_fields:
                insert_field(order_by_fields, PRIMARY_KEY_NAME, 0)  # Ensure ordering by primary key if nothing else
        else:
            for relation in self.relations.filter(related_title__in=related_tables).order_by('-related_index'):
                insert_field(order_by_fields, relation.source_column, 0)  # Ensure ordering by source table keys

        return order_by_clause.format(fields=self._expand_fields(order_by_fields, alias_only=True))

    def _parse_where_clause(self, where):
        if where is None:
            return None

        parsed = sqlparse.parse('WHERE {where_clause}'.format(where_clause=where))
        fields = set(t.parent.value.replace('"', '') for t in parsed[0].flatten() if t.ttype == Token.Name)

        return fields, parsed[1:]  # Additional statements may occur but are invalid

    def _validate_where_clause(self, where):

        parsed = self._parse_where_clause(where)

        if parsed is None:
            return True
        elif parsed[1]:
            return False  # More than one statement means SQL injection.
        else:
            return self._validate_fields(parsed[0])

    def _validate_fields(self, fields):
        query_fields = {field.replace('"', '') for field in fields if '*' not in field}
        if not query_fields:
            return True
        else:
            valid_fields = set(r for r in self.related_fields).union(f['name'] for f in self.fields)
            return query_fields.issubset(valid_fields)

    def get_distinct_geometries_across_time(self, *kwargs):
        time_query = 'SELECT DISTINCT ST_AsText({geom_field}), count(*) FROM {table} GROUP BY ST_AsText({geom_field})'.format(
            geom_field=POINT_FIELD_NAME,
            table=self.table
        )

        with get_cursor() as c:
            c.execute(time_query)
            response = dictfetchall(c)

        return response

    def get_unique_values(self, field):

        if not self._validate_fields([field]):
            raise ValueError('Invalid field')

        unique_values = []
        field_name = field
        table = self.table
        if '.' in field:
            relationship_name, field_name = field.split('.')
            table = self.relations.filter(related_title=relationship_name).first().table

        with get_cursor() as c:
            c.execute('SELECT distinct {field_name} FROM {table} ORDER BY {field_name}'.format(
                table=table, field_name=field_name
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

    def add_feature(self, feature):

        system_cols = {PRIMARY_KEY_NAME, POINT_FIELD_NAME}
        with get_cursor() as c:
            c.execute('SELECT * from {dataset_table_name} LIMIT 0'.format(
                dataset_table_name=self.table
            ))
            colnames_in_table = [desc[0].lower() for desc in c.description if desc[0] not in system_cols]

        columns_not_present = colnames_in_table[0:]

        columns_in_request = feature['attributes'].copy()
        for field in system_cols:
            if field in columns_in_request:
                columns_in_request.pop(field)

        for key in columns_in_request:
            if key not in colnames_in_table:
                raise Exception('attributes do not match')
            columns_not_present.remove(key)

        if len(columns_not_present):
            raise Exception('Missing attributes {0}'.format(','.join(columns_not_present)))

        insert_command = 'INSERT INTO {dataset_table_name} ({attribute_names}) VALUES ({placeholders}) RETURNING {primary_key}'.format(
            dataset_table_name=self.table,
            attribute_names=','.join(colnames_in_table),
            placeholders=','.join(['%s'] * len(colnames_in_table)),
            primary_key=PRIMARY_KEY_NAME
        )
        set_point_command = 'UPDATE {dataset_table_name} SET {point_column} = ST_Transform(ST_SetSRID(ST_MakePoint({long}, {lat}), {web_srid}),{web_srid}) WHERE {primary_key}=%s'.format(
            dataset_table_name=self.table,
            point_column=POINT_FIELD_NAME,
            long=feature['geometry']['x'],
            lat=feature['geometry']['y'],
            primary_key=PRIMARY_KEY_NAME,
            web_srid=WEB_MERCATOR_SRID
        )

        date_fields = [field['name'] for field in self.fields if field['type'] == 'esriFieldTypeDate']
        values = []
        for attribute_name in colnames_in_table:
            if attribute_name in date_fields and feature['attributes'][attribute_name]:
                if isinstance(feature['attributes'][attribute_name], str):
                    values.append(feature['attributes'][attribute_name])
                else:
                    values.append(datetime.fromtimestamp(feature['attributes'][attribute_name] / 1000))
            else:
                values.append(feature['attributes'][attribute_name])

        with get_cursor() as c:
            c.execute(insert_command, values)
            primary_key = c.fetchone()[0]
            c.execute(set_point_command, [primary_key])

        return primary_key

    def update_feature(self, feature):

        with get_cursor() as c:
            c.execute('SELECT * from {dataset_table_name} LIMIT 0'.format(
                dataset_table_name=self.table
            ))
            colnames_in_table = [desc[0].lower() for desc in c.description]

        if PRIMARY_KEY_NAME not in feature['attributes']:
            raise Exception('Cannot update feature without a primary key')

        primary_key = feature['attributes'][PRIMARY_KEY_NAME]

        date_fields = [field['name'] for field in self.fields if field['type'] == 'esriFieldTypeDate']
        argument_updates = []
        argument_values = []
        for key in feature['attributes']:
            if key == PRIMARY_KEY_NAME:
                continue
            if key not in colnames_in_table:
                raise Exception('attributes do not match')
            if key != POINT_FIELD_NAME:
                argument_updates.append('{0} = %s'.format(key))
                if key in date_fields and feature['attributes'][key]:
                    if isinstance(feature['attributes'][key], str):
                        argument_values.append(feature['attributes'][key])
                    else:
                        argument_values.append(datetime.fromtimestamp(feature['attributes'][key] / 1000))
                else:
                    argument_values.append(feature['attributes'][key])

        if feature['geometry']:
            set_point_command = 'UPDATE {dataset_table_name} SET {point_column} = ST_Transform(ST_SetSRID(ST_MakePoint({long}, {lat}), 3857),{web_srid}) WHERE {primary_key}=%s'.format(
                dataset_table_name=self.table,
                point_column=POINT_FIELD_NAME,
                long=feature['geometry']['x'],
                lat=feature['geometry']['y'],
                primary_key=PRIMARY_KEY_NAME,
                web_srid=WEB_MERCATOR_SRID
            )

        argument_values.append(feature['attributes'][PRIMARY_KEY_NAME])
        update_command = (
            'UPDATE {dataset_table_name}'
            ' SET {set_portion}'
            ' WHERE {primary_key}=%s'
        ).format(
            dataset_table_name=self.table,
            set_portion=','.join(argument_updates),
            primary_key=PRIMARY_KEY_NAME
        )

        with get_cursor() as c:
            c.execute(update_command, argument_values)
            c.execute(set_point_command, [primary_key])

        return primary_key

    def delete_feature(self, primary_key):

        delete_command = 'DELETE FROM {table_name} WHERE {primary_key}=%s'.format(
            table_name=self.table,
            primary_key=PRIMARY_KEY_NAME
        )

        with get_cursor() as c:
            c.execute(delete_command, [primary_key])

        return primary_key


class FeatureServiceLayerRelations(models.Model):
    id = models.AutoField(auto_created=True, primary_key=True)
    layer = models.ForeignKey(FeatureServiceLayer)
    related_index = models.PositiveIntegerField(default=0)
    related_title = models.CharField(max_length=255)
    source_column = models.CharField(max_length=255)
    target_column = models.CharField(max_length=255)

    _fields = None

    @property
    def fields(self):
        if self._fields is None:

            fields = get_fields(self.table)
            for field in fields:
                field['alias'] = '{0}.{1}'.format(self.related_title, field['name'])
            self._fields = fields

        return self._fields

    @property
    def table(self):
        return '{table}_{index}'.format(table=self.layer.table, index=self.related_index)


def delete_data_table(sender, instance, **kwargs):
    with get_cursor() as c:
        c.execute('DROP table IF EXISTS {table_name}'.format(table_name=instance.table))


signals.pre_delete.connect(delete_data_table, sender=FeatureServiceLayer)


def sequence_exists(sequence_name):
    with get_cursor() as c:
        c.execute('SELECT 1 FROM pg_class WHERE relname=%s', (sequence_name,))
        return bool(c.fetchone())


def copy_data_table_for_import(dataset_id):

    import_table_name = TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX
    counter = 0

    # Find the first non-used sequence for this import table
    sequence_name = '{0}_{1}_seq'.format(import_table_name, counter)
    while sequence_exists(sequence_name):
        counter += 1
        sequence_name = '{0}_{1}_seq'.format(import_table_name, counter)

    drop_table_command = 'DROP TABLE IF EXISTS {table_name}'.format(
        table_name=import_table_name
    )
    copy_table_command = 'CREATE TABLE {import_table} AS TABLE {data_table}'.format(
        import_table=import_table_name,
        data_table=TABLE_NAME_PREFIX + dataset_id
    )

    # Creating a table based on another table does not pull over primary key information or indexes, nor does
    # it create a sequence for the primary key. Need to do that by hand.

    create_sequence_command = 'CREATE SEQUENCE {sequence_name}'.format(sequence_name=sequence_name)

    alter_table_command = (
        'ALTER TABLE {import_table} ADD PRIMARY KEY ({primary_key}), '
        'ALTER COLUMN {primary_key} SET DEFAULT nextval(\'{sequence_name}\')'
    ).format(
        import_table=import_table_name,
        primary_key=PRIMARY_KEY_NAME,
        sequence_name=sequence_name
    )

    alter_sequence_command = 'ALTER SEQUENCE {sequence_name} owned by {import_table}.{primary_key}'.format(
        import_table=import_table_name,
        primary_key=PRIMARY_KEY_NAME,
        sequence_name=sequence_name
    )

    alter_sequence_start_command = (
        'SELECT setval(\'{sequence_name}\', (select max({primary_key})+1 '
        'from {import_table}), false)'
    ).format(
        import_table=import_table_name,
        primary_key=PRIMARY_KEY_NAME,
        sequence_name=sequence_name
    )

    index_command = 'CREATE INDEX {table_name}_geom_index ON {table_name} USING gist({column_name})'.format(
        table_name=TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX,
        column_name=POINT_FIELD_NAME
    )

    with get_cursor() as c:
        c.execute(drop_table_command)
        c.execute(copy_table_command)
        c.execute(create_sequence_command)
        c.execute(alter_table_command)
        c.execute(alter_sequence_command)
        c.execute(alter_sequence_start_command)
        c.execute(index_command)

    return TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX


def create_database_table(row, dataset_id, append=False, optional_fields=None):
    optional_fields = optional_fields or []
    table_name = TABLE_NAME_PREFIX + dataset_id + IMPORT_SUFFIX
    if not append:
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
            'dropdownedit': 'text',
            'dropdown': 'text',
            'double': 'double precision'
        }
        for cell in row:
            create_table_command += ', {field_name} {type} {null}'.format(
                field_name=cell.column,
                type=type_conversion[re.sub(r'\([^)]*\)', '', str(cell.type).lower())],
                null='NOT NULL' if cell.column not in optional_fields else ''
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
    row.pop()  # remove the appended column
    return table_name


def populate_aggregate_table(aggregate_table_name, columns, datasets_ids_to_combine):
    delete_command = 'DELETE FROM {0}'.format(aggregate_table_name)

    all_commands = [delete_command]
    for dataset_id in datasets_ids_to_combine:

        with get_cursor() as c:
            c.execute('SELECT * from {dataset_table_name} LIMIT 0'.format(
                dataset_table_name=TABLE_NAME_PREFIX + dataset_id
            ))
            colnames_in_table = [desc[0].lower() for desc in c.description]

        current_columns = [column for column in columns if column.column.lower() in colnames_in_table]

        insert_command = (
            'INSERT INTO {table_name} ({definition_fields}, {source_dataset}, {spatial_field}) '
            'SELECT {definition_fields}, {dataset_id}, {spatial_field} FROM {dataset_table_name}'
        ).format(
            table_name=aggregate_table_name,
            definition_fields=','.join([column.column for column in current_columns]),
            source_dataset=SOURCE_DATASET_FIELD_NAME,
            dataset_id="'{0}'".format(dataset_id),
            dataset_table_name=TABLE_NAME_PREFIX + dataset_id,
            spatial_field=POINT_FIELD_NAME
        )
        logger.debug(insert_command)
        all_commands.append(insert_command)

    with get_cursor() as c:
        for command in all_commands:
            c.execute(command)


def populate_data(table_name, row_set):
    first_row = next(row_set.sample)
    field_list = '{field_list}'.format(
        field_list=','.join([cell.column for cell in first_row])
    )
    insert_command = 'INSERT INTO {table_name} ({field_list}) VALUES '.format(
        table_name=table_name,
        field_list=field_list
    )

    with get_cursor() as c:
        header_skipped = False
        values_parenthetical = '({values})'.format(values=','.join(['%s' for cell in first_row]))
        values_list = []
        for row in row_set:
            if not header_skipped:
                header_skipped = True
                continue
            all_values = [cell.value for cell in row]
            individual_insert_command = c.mogrify(values_parenthetical, all_values).decode('utf-8')
            values_list.append(individual_insert_command)

        c.execute(insert_command + ','.join(values_list))


def add_or_update_database_fields(table_name, fields):

    for field in fields:
        alter_commands = []
        db_type = field.get('type')
        column_name = field.get('name')
        required = field.get('required', False)
        value = field.get('value')

        check_command = (
            'SELECT EXISTS('
            'SELECT column_name FROM information_schema.columns '
            'WHERE table_name=%s and column_name=%s)'
        )
        with get_cursor() as c:
            c.execute(check_command, (table_name, column_name))
            column_exists = c.fetchone()[0]

        if column_exists:
            set_default_command = 'ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT {value}'.format(
                table_name=table_name,
                column_name=column_name,
                value=value if db_type not in ('text', 'timestamp') else "'{0}'".format(value)
            )
            alter_commands.append(set_default_command)

        else:
            alter_command = 'ALTER TABLE {table_name} ADD COLUMN {column_name} {db_type}{not_null} DEFAULT {value}'.format(
                table_name=table_name,
                column_name=column_name,
                db_type=db_type,
                not_null=' NOT NULL' if required else '',
                value=value if db_type not in ('text', 'timestamp') else "'{0}'".format(value)
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


def populate_point_data(pk, csv_info, is_import=True):

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
        table_name=TABLE_NAME_PREFIX + pk + (IMPORT_SUFFIX if is_import else ''),
        field_name=POINT_FIELD_NAME,
        make_point_command=make_point_command
    )

    clear_null_command = 'DELETE FROM {table_name} WHERE {field_name} IS NULL'.format(
        table_name=TABLE_NAME_PREFIX + pk + (IMPORT_SUFFIX if is_import else ''),
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

    except DatabaseError:
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
            return self.filename[self.filename.rfind(".") + 1:]
        else:
            return ""
