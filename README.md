QWC Config Service
==================

Provide service specific permissions and configs for other QWC services.

**Note:** requires a QGIS server running on `$QGIS_SERVER_URL` for
OGC service permissions, a QWC ConfigDB for permission queries and 
a PostGIS database for GeoDB metadata queries


Setup
-----

The QWC Map Viewer config requires a QWC2 themes config file `themesConfig.json` (see setup of [QWC Map Viewer](https://github.com/qwc-services/qwc-map-viewer)).

Uses PostgreSQL connection service `qwc_configdb` (ConfigDB).

Setup PostgreSQL connection service file `~/.pg_service.conf`:

```
[qwc_configdb]
host=localhost
port=5439
dbname=qwc_demo
user=qwc_admin
password=qwc_admin
sslmode=disable
```

The Data service config requires read access to the corresponding QGIS project files at `QGIS_RESOURCES_PATH`.

Uses PostgreSQL connection service or connection to a PostGIS database (GeoDB) for data layers from QGIS projects.
This connection's user requires read access to the PostgreSQL metadata tables.

E.g. for demo QGIS project `qwc_demo.qgs`:

```
[qwc_geodb]
host=localhost
port=5439
dbname=qwc_demo
user=qwc_service
password=qwc_service
```


Configuration
-------------

Add new themes to your `themesConfig.json` (see [Documentation](https://github.com/qgis/qwc2-demo-app/blob/master/doc/QWC2_Documentation.md#theme-configuration-qgis-projects-and-the-themesconfigjson-file)) and put any theme thumbnails into `qwc2/assets/img/mapthumbs/`.
The `themesConfig.json` file is used by the Config service to collect the full themes configuration using GetProjectSettings.

Copy any QGIS project files required for the Data service to your `QGIS_RESOURCES_PATH`.

Resources like maps and layers can be permitted by default (`DEFAULT_ALLOW=True`) or need explicit permissions (`DEFAULT_ALLOW=False`).


Usage
-----

Set the `QGIS_SERVER_URL` environment variable to the QGIS server URL
when starting this service. (default: `http://localhost:8001/ows/` on
qwc-qgis-server container)

Set the `QGIS_RESOURCES_PATH` environment variable to your QGIS project files path.

Set the `QWC2_PATH` environment variable to your QWC2 files path.
Set the `QWC2_THEMES_CONFIG` environment variable to your QWC2 `themesConfig.json` path if it is not located in `$QWC2_PATH`.

Base URL:

    http://localhost:5010/

Service API:

    http://localhost:5010/api/

Sample requests:

    curl 'http://localhost:5010/ogc?ows_type=WMS&ows_name=qwc_demo'
    curl 'http://localhost:5010/data?dataset=qwc_demo.edit_points'
    curl 'http://localhost:5010/qwc'


Development
-----------

Install Python module for PostgreSQL:

    apt-get install python3-psycopg2

Create a virtual environment:

    virtualenv --python=/usr/bin/python3 --system-site-packages .venv

Without system packages:

    virtualenv --python=/usr/bin/python3 .venv

Activate virtual environment:

    source .venv/bin/activate

Install requirements:

    pip install -r requirements.txt
    pip install flask_cors

Start local service:

    QGIS_SERVER_URL=http://localhost:8001/ows/ QGIS_RESOURCES_PATH=qgs/ QWC2_PATH=qwc2/ python server.py


### Testing

Run all tests:

    python test.py

Run single test module:

    python -m unittest tests.api_tests

Run single test case:

    python -m unittest tests.api_tests.ApiTestCase

Run single test method:

    python -m unittest tests.api_tests.ApiTestCase.test_data_service_permission
