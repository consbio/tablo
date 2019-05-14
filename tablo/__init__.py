import numpy as np

from tablo.geom_utils import Extent

LARGE_IMAGE_NAME = 'fullsize.jpg'

NO_PK = 'NO_PK'

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

IMPORT_SUFFIX = '_import'
TABLE_NAME_PREFIX = 'db_'
PRIMARY_KEY_NAME = 'db_id'
GEOM_FIELD_NAME = 'dbasin_geom'
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
