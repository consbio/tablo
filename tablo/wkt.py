# All the functions here are translations of ESRI Terraformer library from JS and are used for converting
# ESRI geometry JSON to GeoJSON
# TODO look for optimization possibilities
import json
import re

WKT_GEOM_REGEX = re.compile('((?:-?\d+(?:.\d+(?:[eE][-+]?\d+)?)?) (?:-?\d+(?:.\d+(?:[eE][-+]?\d+)?)?))')
ESRI_GEOM_REGEX = re.compile('(\[)(?:-?\d+(?:.\d+)?)(, ?)(?:-?\d+(?:.\d+)?)(\])')


def to_esri_feature(wkt):
    geom_type = wkt[:wkt.find('(')]

    def _geom_repl():
        bracket_multiplier = 1
        if geom_type == 'LINESTRING':
            bracket_multiplier = 2
        return json.loads(WKT_GEOM_REGEX.sub(
            lambda m: '[{}]'.format(m.group().replace(' ', ',')),
            wkt.replace(geom_type, '')
        ).replace('(', '[' * bracket_multiplier).replace(')', ']' * bracket_multiplier))

    if geom_type == 'POINT' or geom_type == 'MULTIPOINT':
        match = WKT_GEOM_REGEX.findall(wkt)
        if len(match) != 1:
            raise ValueError('Invalid Point Geometry: {0}'.format(wkt))
        try:
            x, y = map(float, match[0].split())
        except ValueError:
            raise ValueError('Invalid Point Geometry: {0}'.format(wkt))
        return {'x': x, 'y': y}
    elif geom_type in ['LINESTRING', 'MULTILINESTRING']:
        return {'paths': _geom_repl()}
    elif geom_type == 'POLYGON':
        return {'rings': _geom_repl()}
    elif geom_type == 'MULTIPOLYGON':
        return {'rings': _geom_repl()[0]}


def from_esri_feature(feature, geom_type):

    def _get_geom_text(geom_text):
        return ESRI_GEOM_REGEX.sub(
            lambda m: m.group().replace('[', '').replace(']', '').replace(',', ' '),
            geom_text
        ).replace('[', '(').replace(']', ')')

    srid = 'SRID={0};'.format(feature.get('spatialReference', {}).get('wkid', 3857))
    if geom_type == 'esriGeometryPoint':
        return '{srid}POINT({x} {y})'.format(srid=srid, x=feature['x'], y=feature['y'])
    elif geom_type == 'esriGeometryPolyline':
        paths_text = json.dumps(feature['paths'])
        return '{srid}MULTILINESTRING{lines}'.format(srid=srid, lines=_get_geom_text(paths_text.replace(' ', '')))
    elif geom_type == 'esriGeometryPolygon':
        rings_text = json.dumps(from_rings(feature['rings'])['coordinates'])
        return '{srid}MULTIPOLYGON{polygons}'.format(srid=srid, polygons=_get_geom_text(rings_text.replace(' ', '')))
    raise ValueError('Unsupported geometry type')


def from_rings(rings):
    """
    Converts an ESRI polygon to GeoJSON.
    :param rings: a collection of rings from an ESRI geometry JSON similar to the following:
        .. code-block:: json

            {
                geometry: {
                    rings: [
                        [[5, 2], [6, 5], [2, 9], [-2, 5], [1, 2], [2, 3], [5, 2]],
                        [[0, 0], [-5, 5], [0, 10], [5, 10], [10, 5], [5, 0], [0, 0]],
                        [[1, 7], [3, 7], [3, 4], [1, 4], [1, 7]]
                    ],
                    'spatialReference': {'wkid': 4326}
                }
            }
        see here for more info: http://help.arcgis.com/en/arcgisserver/10.0/apis/rest/geometry.html
    :return: A GeoJSON object
    """
    outer_rings = []
    holes = []

    for r in rings:
        ring = close_ring(r)
        if len(ring) < 4:
            # A ring with length of less than 4 is not a polygon and can be ignored.
            # close_ring makes sure the first and the last points are the same; that's why minimum length is 4 and not 3
            continue

        if is_clockwise(ring):
            # a clockwise ring means its an outer ring
            outer_rings.append([ring])
        else:
            # otherwise it's a hole!
            holes.append(ring)

    uncontained_holes = []
    reversed_outer_rings = reversed(outer_rings)  # TODO why esri loops over a reversed rings?

    while holes:
        hole = holes.pop()

        # loop over all outer rings and see if they contain our hole.
        contained = False
        for r in reversed_outer_rings:
            outer_ring = r[0]
            if coordinates_contain_coordinates(outer_ring, hole):
                r.append(hole)
                contained = True
                break

        # sometimes a ring may not be contained in any outer ring (https://github.com/Esri/esri-leaflet/issues/320)
        if not contained:
            uncontained_holes.append(hole)

    # check and see if uncontained holes intersect with any outer rings
    while uncontained_holes:
        hole = uncontained_holes.pop()

        intersects = False
        for r in reversed_outer_rings:
            outer_ring = r[0]
            if arrays_intersect(outer_ring, hole):
                outer_rings[r].append(hole)
                intersects = True
                break

        # hole does not intersect ANY outer ring at this point; make it an outer ring.
        if not intersects:
            hole.reverse()
            outer_rings.append([hole])

    return {
        'type': 'MultiPolygon',
        'coordinates': outer_rings
    }


def close_ring(coordinates):
    """
    Makes sure the ring is closed; if it is not, then closes the ring.
    :param coordinates: a collection of coordinates representing a polygon
    :return: a closed ring
    """
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])

    return coordinates


def is_clockwise(ring_to_test):
    """
    A clockwise ring means it is an outer ring; counter-clockwise means the opposite.
    For determining the direction of a ring, we need to calculate the sum of the areas under each side.
    A positive sum indicates a clockwise polygon. See here for more info:
    http://stackoverflow.com/questions/1165647/how-to-determine-if-a-list-of-polygon-points-are-in-clockwise-order
    :param ring_to_test:
    :return: a boolean
    """
    total = 0
    r_length = len(ring_to_test)
    for idx, pt1 in enumerate(ring_to_test):
        # pt1 and pt1 are arrays in form of [x, y] representing the beginning and end points of sides of the ring.
        if idx + 1 != r_length:
            pt2 = ring_to_test[idx + 1]
            total += (pt2[0] - pt1[0]) * (pt2[1] + pt1[1])
    return total >= 0


def edges_intersect(a1, a2, b1, b2):
    """
    The algorithm for determining whether two lines intersect or not:
    https://www.geometrictools.com/Documentation/IntersectionLine2Circle2.pdf
    This one is the same, with visualization: http://geomalgorithms.com/a05-_intersect-1.html
    a and b are vector representation of the received edges and u is the vector from point a1 to point b1
    """

    a = {'x': a2[0] - a1[0], 'y': a2[1] - a1[1]}
    b = {'x': b2[0] - b1[0], 'y': b2[1] - b1[1]}
    u = {'x': a1[0] - b1[0], 'y': a1[1] - b1[1]}
    a_dot_b = (b['y'] * a['x']) - (b['x'] * a['y'])

    if a_dot_b == 0:
        return False

    b_dot_u = (b['x'] * u['y']) - (b['y'] * u['x'])
    a_dot_u = (a['x'] * u['y']) - (a['y'] * u['x'])

    ua = b_dot_u / a_dot_b
    ub = a_dot_u / a_dot_b

    return 0 <= ua <= 1 and 0 <= ub <= 1


def arrays_intersect(a, b):
    try:
        # test for numbers
        int(a[0][0])
        try:
            int(b[0][0])
            for i, _ in enumerate(a[:-1]):
                for j, __ in enumerate(b[:-1]):
                    if edges_intersect(a[i], a[i + 1], b[j], b[j + 1]):
                        return True
        except TypeError:
            return any(arrays_intersect(a, k) for k in b)
    except TypeError:
        return any(arrays_intersect(l, b) for l in a)
    return False


def coordinates_contain_point(coordinates, point):
    """
    This function uses `Crossing number method` (http:#geomalgorithms.com/a03-_inclusion.html) to check whether
    a polygon contains a point or not.
    For each segment with the coordinates `pt1` and `pt2`, we check to see if y coordinate of `point` is
    between y of `pt1` and `pt2`.
    If so, then we check to see if `point` is to the left of the edge; i.e. a line drawn from `point` to the right
    will intersect the edge. If the line intersects the polygon an odd number of times, it is inside.
    """

    contains = False
    j = - 1
    for i, pt1 in enumerate(coordinates):
        pt2 = coordinates[j]
        check_y = lambda: (pt1[1] <= point[1] < pt2[1]) or (pt2[1] <= point[1] < pt1[1])
        # The following checks if `point` is to the left of the current segment
        check_x = lambda: point[0] < (point[1] - pt1[1]) * (pt2[0] - pt1[0]) / (pt2[1] - pt1[1]) + pt1[0]

        if check_y() and check_x():
            contains = not contains
        j = i

    return contains


def coordinates_contain_coordinates(outer, inner):
    intersects = arrays_intersect(outer, inner)
    contains = coordinates_contain_point(outer, inner[0])
    return not intersects and contains
