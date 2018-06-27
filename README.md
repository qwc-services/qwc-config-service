QWC Config Service
==================

Provide service specific permissions and configs for other QWC services.

**Note:** requires a QGIS server running on `$QGIS_SERVER_URL` for
OGC service permissions


Usage
-----

Set the `QGIS_SERVER_URL` environment variable to the QGIS server URL
when starting this service. (default: `http://localhost:8001/ows/` on
qwc-qgis-server container)

Base URL:

    http://localhost:5010/

Service API:

    http://localhost:5010/api/

Sample requests:

    curl 'http://localhost:5010/ogc?ows_type=WMS&ows_name=qwc_demo'


Development
-----------

Create a virtual environment:

    virtualenv --python=/usr/bin/python3 --system-site-packages .venv

Without system packages:

    virtualenv --python=/usr/bin/python3 .venv

Activate virtual environment:

    source .venv/bin/activate

Install requirements:

    pip install -r requirements.txt

Start local service:

    QGIS_SERVER_URL=http://localhost:8001/ows/ python server.py
