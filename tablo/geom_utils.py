import json
import copy
import re

from pyproj import Proj, transform
from math import sqrt, fabs, cos, radians
from itertools import product


GLOBAL_EXTENT_WEB_MERCATOR = (-20037508.342789244, -20037342.166152496, 20037508.342789244, 20037342.16615247)
SQL_BOX_REGEX = re.compile('BOX\((.*) (.*),(.*) (.*)\)')


class SpatialReference(object):
    def __init__(self, spatial_reference=None):
        self.wkid = None  # ESRI WKID
        self.wkt = None  # ESRI WKT
        self.srs = None  # WMS style representation, EPSG: or CRS:
        self.latest_wkid = None  # Used by feature services

        if not spatial_reference:
            return
        if hasattr(spatial_reference, "wkid"):
            for att in ('wkid', 'wkt', 'srs', 'latest_wkid'):
                setattr(self, att, getattr(spatial_reference, att, None))
        elif isinstance(spatial_reference, dict):  # ESRI format
            self.wkid = int(spatial_reference['wkid']) if "wkid" in spatial_reference else None
            self.wkt = spatial_reference.get("wkt", None)
            self.latest_wkid = spatial_reference.get('latestWkid')
        elif isinstance(spatial_reference, (str, bytes)):
            self.srs = spatial_reference

    def __repr__(self):
        if self.wkid:
            return "wkid: %d" % self.wkid
        if self.wkt:
            return "wkt: %s" % self.wkt
        if self.srs:
            return "srs: %s" % self.srs

    def as_dict(self):  # ESRI format
        if self.wkid:
            return {"wkid": self.wkid}
        if self.wkt:
            return {"wkt": self.wkt}
        return None

    def as_json_string(self):  # ESRI format
        return json.dumps(self.as_dict())

    def is_web_mercator(self):
        return (self.wkid in (3857, 102100, 102113) or
               self.srs in ("EPSG:3857", "EPSG:3785", "EPSG:900913", "EPSG:102113"))

    def is_geographic(self):
        return self.wkid == 4326 or self.srs == "EPSG:4326"

    def is_valid_proj4_projection(self):
        """If true, this can be projected using proj4, if false, need to use some external service to project"""

        # only WKIDs < 33000 map to EPSG codes, per http://gis.stackexchange.com/questions/18651/do-arcgis-spatialreference-object-factory-codes-correspond-with-epsg-numbers
        return self.is_web_mercator() or self.srs is not None or (self.wkid and self.wkid < 33000)


# Helper class to provide easy handling of extent through various functions below, and abstract out ESRI / WMS differences
class Extent(object):
    def __init__(self, extent=None, spatial_reference=None):
        self.xmin = None
        self.ymin = None
        self.xmax = None
        self.ymin = None
        self.spatial_reference = SpatialReference(spatial_reference)
        self._original_format = None

        if not extent:
            return
        if hasattr(extent, "xmin"):  # instance of self or similar object
            self.xmin = extent.xmin
            self.ymin = extent.ymin
            self.xmax = extent.xmax
            self.ymax = extent.ymax
            self.spatial_reference = SpatialReference(extent.spatial_reference)
        elif isinstance(extent, dict):  # ESRI format
            self._original_format = "dict"
            self.xmin = extent["xmin"]
            self.ymin = extent["ymin"]
            self.xmax = extent["xmax"]
            self.ymax = extent["ymax"]
            assert extent.has_key("spatialReference")
            self.spatial_reference = SpatialReference(extent["spatialReference"])
        elif isinstance(extent, (list, tuple)):  # WMS format, spatial reference parameter must be provided
            self._original_format = "list"
            self.xmin = extent[0]
            self.ymin = extent[1]
            self.xmax = extent[2]
            self.ymax = extent[3]
            assert self.spatial_reference is not None

    def __unicode__(self):
        return str(self.as_dict())

    def __repr__(self):
        return str(self)

    def clone(self):
        return copy.deepcopy(self)

    def as_dict(self, precision=None, include_spatial_reference=True):
        extent = dict()
        for key in ("xmin", "ymin", "xmax", "ymax"):
            extent[key] = getattr(self, key)
            if precision is not None:
                extent[key] = round(extent[key], precision)
        if self.spatial_reference and include_spatial_reference:
            extent["spatialReference"] = self.spatial_reference.as_dict()
        return extent

    def as_list(self):
        return [getattr(self, key) for key in ("xmin", "ymin", "xmax", "ymax")]

    def as_original(self):
        if self._original_format == "dict":
            return self.as_dict()
        elif self._original_format == "list":
            return self.as_list()
        else:
            return self

    def as_bbox_string(self, precision=4):
        format_str = "%%.%df" % precision
        return ",".join([format_str % x for x in self.as_list()])

    def as_json_string(self, precision=4):
        json_dict = self.as_dict()
        for key in ("xmin", "ymin", "xmax", "ymax"):
            json_dict[key]=round(json_dict[key], precision)
        return json.dumps(json_dict)

    def as_sql_poly(self):
        return 'POLYGON(({xmin} {ymin}, {xmax} {ymin}, {xmax} {ymax}, {xmin} {ymax}, {xmin} {ymin}))'.format(
            **self.as_dict()
        )

    def limit_to_global_extent(self):
        """Note: self must be in Web Mercator!"""
        assert self.spatial_reference.is_web_mercator()
        new_extent = self.clone()
        new_extent.xmin = max(GLOBAL_EXTENT_WEB_MERCATOR[0], new_extent.xmin)
        new_extent.ymin = max(GLOBAL_EXTENT_WEB_MERCATOR[1], new_extent.ymin)
        new_extent.xmax = min(GLOBAL_EXTENT_WEB_MERCATOR[2], new_extent.xmax)
        new_extent.ymax = min(GLOBAL_EXTENT_WEB_MERCATOR[3], new_extent.ymax)
        return new_extent

    def limit_to_global_width(self):
        """Note: self must be in Web Mercator!"""
        assert self.spatial_reference.is_web_mercator()
        new_extent = self.clone()
        new_extent.xmin = max(GLOBAL_EXTENT_WEB_MERCATOR[0], new_extent.xmin)
        new_extent.xmax = min(GLOBAL_EXTENT_WEB_MERCATOR[2], new_extent.xmax)
        return new_extent

    def crosses_anti_meridian(self):
        """Note: self must be in Web Mercator!"""
        assert self.spatial_reference.is_web_mercator()
        return self.xmin < GLOBAL_EXTENT_WEB_MERCATOR[0] or self.xmax > GLOBAL_EXTENT_WEB_MERCATOR[2]

    def has_negative_extent(self):
        if not self.spatial_reference.is_web_mercator():
            raise ValueError('Extent must be web mercator in order to test for negative extent')
        return self.xmin < GLOBAL_EXTENT_WEB_MERCATOR[0]

    def get_negative_extent(self):
        """
        Extents normalized by ArcGIS on the front end may have a negative extent for the area to the left of the
        meridian. This method returns that component as an extent that can be sent to image retrieval routines.
        The negative_extent will have the same height and same width as the original extent, but the xmin and
        xmax will be different.
        """
        if self.has_negative_extent():
            new_extent = self.clone()
            new_extent.xmin = GLOBAL_EXTENT_WEB_MERCATOR[2] - (GLOBAL_EXTENT_WEB_MERCATOR[0] - self.xmin)
            new_extent.xmax = new_extent.xmin + self.get_dimensions()[0]
            return new_extent

    def fit_to_dimensions(self, width, height):
        """
        Expand self as necessary to fit dimensions of image
        """

        new_extent = self.clone()
        img_aspect_ratio = float(height) / float(width)
        xrange, yrange = new_extent.get_dimensions()
        if xrange == 0:  # Can happen for a single point
            extent_aspect_ratio = 1
        else:
            extent_aspect_ratio = yrange / xrange
        if img_aspect_ratio > extent_aspect_ratio:
            #img is taller than extent
            diff_extent_units = ((img_aspect_ratio * xrange) - yrange) / 2.0
            new_extent.ymin -= diff_extent_units
            new_extent.ymax += diff_extent_units
        elif img_aspect_ratio < extent_aspect_ratio:
            #img is wider than extent
            diff_extent_units = ((yrange / img_aspect_ratio) - xrange) / 2.0
            new_extent.xmin -= diff_extent_units
            new_extent.xmax += diff_extent_units
        return new_extent

    def get_image_resolution(self, width, height):
        x_diff, y_diff = self.get_dimensions()
        return sqrt((x_diff * y_diff) / (width * height))

    def fit_image_dimensions_to_extent(self, width, height, target_resolution=None):
        """
        Return image dimensions that fit the extent's aspect ratio.
        If target_resolution is provided, use that for calculating dimensions instead (useful for WMS client)
        """

        resolution = target_resolution or self.get_image_resolution(width, height)
        imgAspectRatio = float(height) / float(width)
        xrange, yrange = self.get_dimensions()
        extentAspectRatio = yrange / xrange
        if imgAspectRatio > extentAspectRatio:
            #img is taller than extent
            diffExtentUnits = ((imgAspectRatio * xrange) - yrange) / 2.0
            offsetPixels = int(round(diffExtentUnits / resolution, 0))
            height = height - 2 * offsetPixels
        elif imgAspectRatio < extentAspectRatio:
            #img is wider than extent
            diffExtentUnits = ((yrange / imgAspectRatio) - xrange) / 2.0
            offsetPixels = int(round(diffExtentUnits / resolution, 0))
            width = width - 2 * offsetPixels
        return width, height

    def set_to_center_and_scale(self, scale, width_in_pixels, height_in_pixels):
        """
            Modifies the extent by centering on the current extent, the changing to the given scale and viewport's
            width and height.
        """

        # This is the ratio from the LODS that we use
        resolution = scale / 3779.52

        merc_extent = self.project_to_web_mercator()
        x_center, y_center = merc_extent.get_center()

        x_units_from_center = (width_in_pixels / 2.0) * resolution
        y_units_from_center = (height_in_pixels / 2.0) * resolution

        merc_extent.xmax = x_center + x_units_from_center
        merc_extent.xmin = x_center - x_units_from_center
        merc_extent.ymax = y_center + y_units_from_center
        merc_extent.ymin = y_center - y_units_from_center

        return merc_extent

    def project_to_web_mercator(self):
        """
        Project self to web mercator (only some ESRI extents are valid here)
        """

        new_extent = self.clone()
        if self.spatial_reference.is_web_mercator():
            return new_extent

        if not self.spatial_reference.is_valid_proj4_projection():
            raise ValueError("Spatial reference is not valid for proj4, must use a different service to project")

        src_srs = None
        if self.spatial_reference.wkid:
            src_srs = "EPSG:%i" % (self.spatial_reference.wkid)
        elif self.spatial_reference.wkt:
            raise NotImplementedError("WKT Projection support not built yet!")
        elif self.spatial_reference.srs:
            src_srs = self.spatial_reference.srs.replace("CRS:84",
                                                         "EPSG:4326")  # pypoj doesn't seem to be aware of CRS entry
        else:
            raise ValueError("Projection must be defined for extent to reproject it")

        #apply some corrections to avoid singularities in projection at latitude -90 or 90
        if src_srs == "EPSG:4326":
            if self.ymin <= -90:
                self.ymin = -85.0511  # Per openlayers convention
            if self.ymax >= 90:
                self.ymax = 85.0511

        new_extent.xmin, new_extent.ymin, new_extent.xmax, new_extent.ymax = self._get_projected_extent(src_srs,
                                                                                                        "EPSG:3857")
        new_extent.spatial_reference.wkid = 3857
        new_extent.spatial_reference.srs = "EPSG:3857"
        return new_extent


    def project_to_geographic(self):
        """
        Project self to geographic (only some ESRI extents are valid here)
        """

        new_extent = self.clone()
        if self.spatial_reference.is_geographic():
            return new_extent

        if not self.spatial_reference.is_valid_proj4_projection():
            raise ValueError("Spatial reference is not valid for proj4, must use a different service to project")

        src_srs = None
        if self.spatial_reference.is_web_mercator():
            src_srs = "EPSG:3857"
        elif self.spatial_reference.wkid:
            src_srs = "EPSG:%i" % (self.spatial_reference.wkid)
        elif self.spatial_reference.wkt:
            raise NotImplementedError("WKT Projection support not built yet!")
        elif self.spatial_reference.srs:
            src_srs = self.spatial_reference.srs
        else:
            raise ValueError("Projection must be defined for extent to reproject it")

        new_extent.xmin, new_extent.ymin, new_extent.xmax, new_extent.ymax = self._get_projected_extent(src_srs,
                                                                                                        "EPSG:4326")
        new_extent.spatial_reference.wkid = 4326
        new_extent.spatial_reference.srs = "EPSG:4326"
        return new_extent


    def _get_projected_extent(self, src_srs, target_srs, edge_points=9):
        """
        Densifies the edges with edge_points points between corners, and projects all of them.
        Returns the outer bounds of the projected coords.
        Geographic latitudes must be bounded to  -85.0511 <= y <= 85.0511 prior to calling this or things will fail!
        """

        srcProj = Proj(init=src_srs) if src_srs.strip().lower().startswith('epsg:') else Proj(str(src_srs))
        targetProj = Proj(init=target_srs) if ':' in target_srs else Proj(str(target_srs))
        if edge_points < 2:  # cannot densify (calculations below will fail), just use corners
            x_values, y_values = transform(srcProj, targetProj, [self.xmin, self.xmax], [self.ymin, self.ymax])
            return x_values[0], y_values[0], x_values[1], y_values[1]

        samples = range(0, edge_points)
        x_diff, y_diff = self.get_dimensions()
        xstep = x_diff/(edge_points-1)
        ystep = y_diff/(edge_points-1)
        x_values = []
        y_values = []
        for i, j in product(samples, samples):
            x_values.append(self.xmin + xstep * i)
            y_values.append(self.ymin + ystep * j)
        # TODO: check for bidrectional consistency, as is done in ncserve BoundingBox.project() method
        x_values, y_values = transform(srcProj, targetProj, x_values, y_values)
        return min(x_values), min(y_values), max(x_values), max(y_values)

    def _calc_scale_factor(self, lat_degrees):
        # Based on http://en.wikipedia.org/wiki/Mercator_projection#Scale_factor
        return 1 / cos(radians(lat_degrees))

    def get_scale_string(self, image_width):
        """
            Method for returning a string of text showing the current extent's scale. This is modified to use
            the extent's southern latitude to mimic what ArcGIS does with the front end scale display.
        """

        pixels_per_inch = 96

        web_mercator_extent = self.project_to_web_mercator()
        geo_extent = self.project_to_geographic()

        x_diff = web_mercator_extent.get_dimensions()[0]
        resolution = abs(x_diff / image_width)
        meters_per_inch = resolution * pixels_per_inch
        kilometers_per_inch = meters_per_inch / 1000
        southern_latitude = geo_extent.ymin

        scale_in_kilometers = extract_significant_digits(kilometers_per_inch / self._calc_scale_factor(southern_latitude))
        scale_in_miles = extract_significant_digits(scale_in_kilometers * 0.621371192237)

        return '%s km (%s miles)' % (str(scale_in_kilometers), str(scale_in_miles))

    def get_center(self):
        x_diff , y_diff = self.get_dimensions()
        return self.xmax - (x_diff / 2), self.ymax - (y_diff / 2)

    def get_dimensions(self):
        """ Returns the width, height of the extent """

        return float(self.xmax - self.xmin), float(self.ymax - self.ymin)

    def get_geographic_labels(self):
        geo_extent = self.project_to_geographic()
        label = u"{0:0.2f}\u00B0{1}"
        xmin_label = label.format(fabs(geo_extent.xmin), "W" if geo_extent.xmin < 0 else "E")
        xmax_label = label.format(fabs(geo_extent.xmax), "W" if geo_extent.xmax < 0 else "E")
        ymin_label = label.format(fabs(geo_extent.ymin), "S" if geo_extent.ymin < 0 else "N")
        ymax_label = label.format(fabs(geo_extent.ymax), "S" if geo_extent.ymax < 0 else "N")
        return xmin_label, ymin_label, xmax_label, ymax_label

    @classmethod
    def from_sql_box(cls, box, spatial_reference):
        match = SQL_BOX_REGEX.match(box)
        if not match:
            raise ValueError('Invalid SQL Box: {0}'.format(box))
        return cls([float(x) for x in match.groups()], spatial_reference=spatial_reference)


# Helper functions
def union_extent(extents):
    extents = filter(lambda x: x is not None, extents)
    if not extents:
        return None
    assert isinstance(extents[0], Extent)
    extent = extents[0].clone()
    for next_extent in extents[1:]:
        assert isinstance(next_extent, Extent)
        extent.xmin = min(extent.xmin, next_extent.xmin)
        extent.ymin = min(extent.ymin, next_extent.ymin)
        extent.xmax = max(extent.xmax, next_extent.xmax)
        extent.ymax = max(extent.ymax, next_extent.ymax)
    return extent

def extract_significant_digits(number):
    is_negative = False
    dijits = 0
    if number < 0:
        is_negative = True
        number = 0 - number

    if 0.1 <= number < 10:
        dijits = 1
    elif 10 <= number < 100:
        dijits = 0
    elif number >= 100:
        dijits = -1

    rounded = round(number, dijits)
    if dijits < 1:
        # In this case, we have a whole number, so return that
        rounded = int(rounded)

    if is_negative:
        rounded = 0 - rounded

    return rounded