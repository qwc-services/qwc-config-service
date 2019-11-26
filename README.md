QWC Config Service
==================

Provide service specific permissions and configs for other QWC services.

**Note:** requires a QGIS server running on `$QGIS_SERVER_URL` for
OGC service permissions, a QWC ConfigDB for permission queries and 
a PostGIS database for GeoDB metadata queries


Resources
---------

Permissions and configurations are based on different resources with assigned permissions in the [configuration database](https://github.com/qwc-services/qwc-config-db).
These can be managed in the [QWC configuration backend](https://github.com/qwc-services/qwc-admin-gui).

The following resource types are available:

* `map`: WMS corresponding to a QGIS Project
    * `layer`: layer of a map
        * `attribute`: attribute of a map layer
    * `print_template`: print composer template of a QGIS Project
    * `data`: Data layer for editing
        * `attribute`: attribute of a data layer
    * `data_create`: Data layer for creating features
    * `data_read`: Data layer for reading features
    * `data_update`: Data layer for updating features
    * `data_delete`: Data layer for deleting features
* `viewer`: custom map viewer configuration
* `viewer_task`: permittable viewer tasks

The resource `name` corresponds to the technical name of its resource (e.g. WMS layer name).

The resource types can be extended by inserting new types into the `qwc_config.resource_types` table.
These can be queried, e.g. in a custom service, by using `PermissionClient::resource_permissions()` or 
`PermissionClient::resource_restrictions()` from [QWC Services Core](https://github.com/qwc-services/qwc-services-core).

Available `map`, `layer`, `attribute` and `print_template` resources are collected from WMS `GetProjectSettings` and the QGIS projects.

`data` and their `attribute` resources define a data layer for the [Data service](https://github.com/qwc-services/qwc-data-service).
Database connections and attribute metadata are collected from the QGIS projects.

For more detailed CRUD permissions `data_create`, `data_read`, `data_update` and `data_delete` can be used instead of `data` 
(`data` and `write=False` is equivalent to `data_read`; `data` and `write=True` is equivalent to all CRUD resources combined).

The `viewer` resource defines a custom viewer configuration for the map viewer (see [Custom viewer configurations](https://github.com/qwc-services/qwc-map-viewer#custom-viewer-configurations)).

The `viewer_task` resource defines viewer functionalities (e.g. printing or raster export) that can be restricted or permitted.
Their `name` (e.g. `RasterExport`) corresponds to the `key` in `menuItems` and `toolbarItems` in the QWC2 `config.json`. Restricted viewer task items are then removed from the menu and toolbar in the map viewer. Viewer tasks not explicitly added as resources are kept unchanged from the `config.json`.


Permissions
-----------

Permissions are based on roles. Roles can be assigned to groups or users, and users can be members of groups.
A special role is `public`, which is always included, whether a user is signed in or not.

Each role can be assigned a permission for a resource.
The `write` flag is only used for `data` resources and sets whether a data layer is read-only.

Based on the user's identity (user name and/or group name), all corresponding roles and their permissions and restrictions are collected.
The service configurations are then modified according to these permissions and restrictions.

Using the `DEFAULT_ALLOW` environment variable, some resources can be set to be permitted or restricted by default if no permissions are set (default: `True`). Affected resources are `map`, `layer`, `print_template` and `viewer_task`.

e.g. `DEFAULT_ALLOW=True`: all maps and layers are permitted by default
e.g. `DEFAULT_ALLOW=False`: maps and layers are only available if their resources and permissions are explicitly configured


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
Set the `QWC2_VIEWERS_PATH` environment variable to your QWC2 custom viewers path (default: `$QWC2_PATH/viewers/`) (see [Custom viewer configurations](https://github.com/qwc-services/qwc-map-viewer#custom-viewer-configurations)).

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
