import numpy as np

from .geom_utils import Extent


__VERSION__ = '2.0'

GEOM_FIELD_NAME = 'dbasin_geom'
IMPORT_SUFFIX = '_import'
LARGE_IMAGE_NAME = 'fullsize.jpg'
NO_PK = 'NO_PK'
PRIMARY_KEY_NAME = 'db_id'
SOURCE_DATASET_FIELD_NAME = 'source_dataset'
TABLE_NAME_PREFIX = 'db_'
WEB_MERCATOR_SRID = 3857

PANDAS_TYPE_CONVERSION = {
    'decimal': np.float64,
    'date': np.datetime64,
    'integer': np.int64,
    'string': np.str,
    'xlocation': np.float64,
    'ylocation': np.float64,
    'dropdownedit': np.str,
    'dropdown': np.str,
    'double': np.float64,
    'image': np.str,
    'text': np.str,
    'timestamp': np.datetime64
}
POSTGIS_ESRI_FIELD_MAPPING = {
    'bigint': 'esriFieldTypeInteger',
    'smallint': 'esriFieldTypeSmallInteger',
    'boolean': 'esriFieldTypeSmallInteger',
    'integer': 'esriFieldTypeInteger',
    'text': 'esriFieldTypeString',
    'character': 'esriFieldTypeString',
    'character varying': 'esriFieldTypeBlob',
    'double precision': 'esriFieldTypeDouble',
    'real': 'esriFieldTypeDouble',
    'date': 'esriFieldTypeDate',
    'timestamp without time zone': 'esriFieldTypeDate',
    'Geometry': 'esriFieldTypeGeometry',
    'Unknown': 'esriFieldTypeString',
    'OID': 'esriFieldTypeOID',
}

# Adjusted global extent -- adjusted to better fit screen layout. Same as mapController.getAdjustedGlobalExtent().
ADJUSTED_GLOBAL_EXTENT = Extent({
    'xmin': -20000000,
    'ymin': -7000000,
    'xmax': 20000000,
    'ymax': 18000000,
    'spatialReference': {'wkid': WEB_MERCATOR_SRID}
})
