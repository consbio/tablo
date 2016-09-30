This is the documentation folder for Tablo. In order to manually build the documentation, you will need to
pip install the following libraries (this are not included as dependencies since they are only required for
building the documentation):

sphinx
sphinx-autobuild
sphinx-rtd-theme

You will also need to set your DJANGO_SETTINGS_MODULE to the settings.py file in this directory. Sphinx needs to load
the files in order to process them, so it needs to have the required Django setup in order to do this.

Once that is set, from this directory, run:
make html

This will create the documentation files under the _build directory.
