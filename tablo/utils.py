import json
from collections import OrderedDict

from tastypie.fields import CharField


# code from http://danieljlewis.org/files/2010/06/Jenks.pdf
# described at http://danieljlewis.org/2010/06/07/jenks-natural-breaks-algorithm-in-python/

def get_jenks_breaks(data_list, num_classes):
    data_list.sort()
    mat1 = []
    for i in range(0, len(data_list) + 1):
        temp = []
        for j in range(0, num_classes + 1):
            temp.append(0)
        mat1.append(temp)
    mat2 = []
    for i in range(0, len(data_list) + 1):
        temp = []
        for j in range(0, num_classes + 1):
            temp.append(0)
        mat2.append(temp)
    for i in range(1, num_classes + 1):
        mat1[1][i] = 1
        mat2[1][i] = 0
        for j in range(2, len(data_list) + 1):
            mat2[j][i] = float('inf')
    v = 0.0
    for l in range(2, len(data_list) + 1):
        s1 = 0.0
        s2 = 0.0
        w = 0.0
        for m in range(1, l + 1):
            i3 = l - m + 1
            val = float(data_list[i3 - 1])
            s2 += val * val
            s1 += val
            w += 1
            v = s2 - (s1 * s1) / w
            i4 = i3 - 1
            if i4 != 0:
                for j in range(2, num_classes + 1):
                    if mat2[l][j] >= (v + mat2[i4][j - 1]):
                        mat1[l][j] = i3
                        mat2[l][j] = v + mat2[i4][j - 1]
        mat1[l][1] = 1
        mat2[l][1] = v
    k = len(data_list)
    kclass = []
    for i in range(0, num_classes + 1):
        kclass.append(0)
    kclass[num_classes] = float(data_list[len(data_list) - 1])
    count_num = num_classes
    while count_num >= 2:
        pk = int((mat1[k][count_num]) - 2)
        kclass[count_num - 1] = data_list[pk]
        k = int((mat1[k][count_num] - 1))
        count_num -= 1
    return kclass


def get_gvf(data_list, num_classes):
    """
    The Goodness of Variance Fit (GVF) is found by taking the
    difference between the squared deviations
    from the array mean (SDAM) and the squared deviations from the
    class means (SDCM), and dividing by the SDAM
    """
    breaks = get_jenks_breaks(data_list, num_classes)
    data_list.sort()
    list_mean = sum(data_list) / len(data_list)
    sdam = 0.0
    for i in range(0, len(data_list)):
        sq_dev = (data_list[i] - list_mean) ** 2
        sdam += sq_dev
    sdcm = 0.0
    for i in range(0, num_classes):
        if breaks[i] == 0:
            class_start = 0
        else:
            class_start = data_list.index(breaks[i])
            class_start += 1
        class_end = data_list.index(breaks[i + 1])
        class_list = data_list[class_start:class_end + 1]
        class_mean = sum(class_list) / len(class_list)
        pre_sdcm = 0.0
        for j in range(0, len(class_list)):
            sqDev2 = (class_list[j] - class_mean) ** 2
            pre_sdcm += sqDev2
        sdcm += pre_sdcm
    return (sdam - sdcm) / sdam


def dictfetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [
        OrderedDict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]


def json_date_serializer(obj):
    # Handles date serialization when part of the response object

    if hasattr(obj, 'isoformat'):
        serial = obj.isoformat()
        return serial
    return json.JSONEncoder.default(obj)


def get_file_ops_error_code(e):
    error_msg = ''
    if hasattr(e, 'message'):
        error_msg = e.message
    else:
        error_msg = str(e)

    error_code = 'UNKNOWN_ERROR'
    if 'column' in error_msg and 'specified more than once' in error_msg:
        error_code = 'DUPLICATE_COLUMN'
    elif 'transform' in error_msg:
        error_code = 'TRANSFORM'

    return error_code


class JSONField(CharField):
    def convert(self, value):
        if value is None:
            return None
        return json.loads(value, strict=False)

    def hydrate(self, bundle):
        value = super(JSONField, self).hydrate(bundle)
        if value:
            value = json.dumps(value)

        return value
