Tablo
===========

.. image:: https://travis-ci.org/consbio/tablo.svg?branch=master
    :target: https://travis-ci.org/consbio/tablo

.. image:: https://readthedocs.org/projects/tablo/badge/?version=latest
    :target: http://tablo.readthedocs.io/en/latest/?badge=latest

What is Tablo?
--------------

Tablo is a lightweight Django application that creates a interface layer for interacting with spatial data
stored within a PostGIS database.

Goals
-----

The main goal of Tablo is to allow us to store data in a PostGIS database and be able to access it
in the same way we access ArcGIS feature services.

We wanted to be able to query the data in the PostGIS database using a REST endpoint similar to this:

    .. code-block:: none

        localhost:8383/tablo/arcgis/rest/services/905/FeatureServer/0/query?f=json
        &returnGeometry=true&spatialRel=esriSpatialRelIntersects
        &geometry={"xmin":-13697515.468700845,"ymin":5662246.477956772,
        "xmax":-13619243.951736793,"ymax":5740517.994920822,
        "spatialReference":{"wkid":3857}}
        &geometryType=esriGeometryEnvelope&inSR=3857&outFields=*&outSR=3857

This allows us to take a CSV file like this:

    ===========   ==================  =========  ========  ===================
    Team Name     Name of the Stream  Longitude  Latitude  Temperature Reading
    -----------   ------------------  ---------  --------  -------------------
    Fun Team      Columbia 'D' River  -122.2345  45.5483   60
    Fun Team 2    Columbia River      -122.2869  45.5429   60
    Fun Team      Columbia River      -122.4224  45.5655   65
    Portlandias   Johnson Creek       -122.5849  45.4606   59
    Portlandias   Johnson Creek       -122.5986  45.4551   61
    ===========   ==================  =========  ========  ===================

And turn it into a map like this:

    .. figure:: _static/images/sample_map.png


Notes
-----

Currently, Tablo only supports point geometry data. We hope to add other types of geometry in the near future.

Tablo, out of the box, does not offer authentication. It can be added in the form of API key authentication as
described in the :ref:`Add API Key Authentication <api_key>` install section.


Documentation
-------------

Full documentation available `here <http://tablo.readthedocs.io/en/latest/>`_.
