Data Upload
===========

Tablo is built around the idea of being able to upload a CSV file and then consuming that data through
one or more generic interfaces that abstract out the data storage layer. Before you can consume the data,
you must upload it into Tablo. This document details the steps involved in the upload process.

Upload
------

.. automethod:: tablo.views.TemporaryFileUploadUrlView.dispatch

Describe
--------
.. automethod:: tablo.api.TemporaryFileResource.describe
