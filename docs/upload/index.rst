Data Upload
===========

Tablo is built around the idea of being able to upload a CSV file and then consuming that data through
one or more generic interfaces that abstract out the data storage layer. Before you can consume the data,
you must upload it into Tablo. This document details the steps involved in the upload process.

There are multiple steps to the process, allowing for minor changes in data along the way. The minimum set of steps
is as follows:

1. :ref:`Upload CSV File <upload>`
2. :ref:`Describe the CSV File <describe>`
3. :ref:`Deploy the CSV File <deploy>`
4. :ref:`Create the Feature Service <create>`
5. :ref:`Finalize the Feature Service <finalize>`

.. _upload:

Upload
------
.. automethod:: tablo.views.TemporaryFileUploadUrlView.dispatch


.. _describe:

Describe
--------
.. automethod:: tablo.api.TemporaryFileResource.describe


.. _deploy:

Deploy
------
.. automethod:: tablo.api.TemporaryFileResource.deploy


.. _create:

Create a Feature Service
------------------------
.. autoclass:: tablo.api.FeatureServiceResource


.. _finalize:

Finalize the Service
--------------------
.. automethod:: tablo.api.FeatureServiceResource.finalize
