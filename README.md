QWC Config Service
==================

Provide service specific permissions and configs for other QWC services.

**Note:** requires a QGIS server running on `$QGIS_SERVER_URL` for
OGC service permissions and a QWC ConfigDB for permission queries


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


Configuration
-------------

Add new themes to your `themesConfig.json` (see [Documentation](https://github.com/qgis/qwc2-demo-app/blob/master/doc/QWC2_Documentation.md#theme-configuration-qgis-projects-and-the-themesconfigjson-file)) and put any theme thumbnails into `qwc2/assets/img/mapthumbs/`.
The `themesConfig.json` file is used by the Config service to collect the full themes configuration using GetProjectSettings.


Usage
-----

Set the `QGIS_SERVER_URL` environment variable to the QGIS server URL
when starting this service. (default: `http://localhost:8001/ows/` on
qwc-qgis-server container)

Set the `QWC2_PATH` environment variable to your QWC2 files path.
Set the `QWC2_THEMES_CONFIG` environment variable to your QWC2 `themesConfig.json` path if it is not located in `$QWC2_PATH`.

Base URL:

    http://localhost:5010/

Service API:

    http://localhost:5010/api/

Sample requests:

    curl 'http://localhost:5010/ogc?ows_type=WMS&ows_name=qwc_demo'
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

Start local service:

    QGIS_SERVER_URL=http://localhost:8001/ows/ QWC2_PATH=qwc2/ python server.py
