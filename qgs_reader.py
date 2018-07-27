import os
import re
from xml.etree import ElementTree


class QGSReader:
    """QGSReader class

    Read QGIS 2.18 projects and extract data for QWC config.
    """

    def __init__(self, logger):
        """Constructor

        :param Logger logger: Application logger
        """
        self.logger = logger
        self.root = None

        # get path to QGIS projects from ENV
        self.qgs_resources_path = os.environ.get('QGIS_RESOURCES_PATH', 'qgs/')

    def read(self, qgs_path):
        """Read QGIS project file and return True on success.

        :param str qgs_path: QGS name with optional path relative to
                             QGIS_RESOURCES_PATH
        """
        qgs_file = "%s.qgs" % qgs_path
        qgs_path = os.path.join(self.qgs_resources_path, qgs_file)
        if not os.path.exists(qgs_path):
            self.logger.warn("Could not find QGS file '%s'" % qgs_path)
            return False

        try:
            tree = ElementTree.parse(qgs_path)
            self.root = tree.getroot()
            if self.root.tag != 'qgis':
                self.logger.warn("'%s' is not a QGS file" % qgs_path)
                return False

        except Exception as e:
            self.logger.error(e)
            return False

        return True

    def layer_metadata(self, layer_name):
        """Collect layer metadata from QGS.

        :param str layer_name: Layer shortname
        """
        config = {}

        if self.root is None:
            self.logger.warning("Root element is empty")
            return config

        # find layer by shortname
        for maplayer in self.root.findall('.//maplayer'):
            if maplayer.find('shortname') is not None:
                maplayer_name = maplayer.find('shortname').text
            else:
                maplayer_name = maplayer.find('layername').text
            if maplayer_name == layer_name:
                provider = maplayer.find('provider').text
                if provider != 'postgres':
                    self.logger.info("Not a PostgreSQL layer")
                    continue

                datasource = maplayer.find('datasource').text
                config['database'] = self.db_connection(datasource)
                config.update(self.table_metadata(datasource))
                config.update(self.attributes_metadata(maplayer))

                break

        return config

    def db_connection(self, datasource):
        """Parse QGIS datasource URI and return SQLALchemy DB connection
        string for a PostgreSQL database or connection service.

        :param str datasource: QGIS datasource URI
        """
        connection_string = None

        if 'service=' in datasource:
            # PostgreSQL connection service
            m = re.search(r"service='([\w ]+)'", datasource)
            if m is not None:
                connection_string = 'postgresql:///?service=%s' % m.group(1)

        elif 'dbname=' in datasource:
            # PostgreSQL database
            dbname, host, port, user, password = '', '', '', '', ''

            m = re.search(r"dbname='(.+?)' \w+=", datasource)
            if m is not None:
                dbname = m.group(1)

            m = re.search(r"host=([\w\.]+)", datasource)
            if m is not None:
                host = m.group(1)

            m = re.search(r"port=(\d+)", datasource)
            if m is not None:
                port = m.group(1)

            m = re.search(r"user='(.+?)' \w+=", datasource)
            if m is not None:
                user = m.group(1)
                # unescape \' and \\'
                user = re.sub(r"\\'", "'", user)
                user = re.sub(r"\\\\", r"\\", user)

            m = re.search(r"password='(.+?)' \w+=", datasource)
            if m is not None:
                password = m.group(1)
                # unescape \' and \\'
                password = re.sub(r"\\'", "'", password)
                password = re.sub(r"\\\\", r"\\", password)

            # postgresql://user:password@host:port/dbname
            connection_string = 'postgresql://'
            if user and password:
                connection_string += "%s:%s@" % (user, password)

            connection_string += "%s:%s/%s" % (host, port, dbname)

        return connection_string

    def table_metadata(self, datasource):
        """Parse QGIS datasource URI and return table metadata.

        :param str datasource: QGIS datasource URI
        """
        metadata = {}

        # parse schema, table and geometry column
        m = re.search(r'table="(.+?)" \((\w+)\) \w+=', datasource)
        if m is not None:
            table = m.group(1)
            parts = table.split('"."')
            metadata['schema'] = parts[0]
            metadata['table_name'] = parts[1]

            metadata['geometry_column'] = m.group(2)

        m = re.search(r"key='(.+?)' \w+=", datasource)
        if m is not None:
            metadata['primary_key'] = m.group(1)

        m = re.search(r"type=([\w.]+)", datasource)
        if m is not None:
            metadata['geometry_type'] = m.group(1).upper()

        m = re.search(r"srid=([\d.]+)", datasource)
        if m is not None:
            metadata['srid'] = int(m.group(1))

        return metadata

    def attributes_metadata(self, maplayer):
        """Collect layer attributes.

        :param Element maplayer: QGS mayplayer node
        """
        attributes = []
        fields = {}

        aliases = maplayer.find('aliases')
        for alias in aliases.findall('alias'):
            field = alias.get('field')
            attributes.append(field)

            fields[field] = {}

            # get alias
            name = alias.get('name')
            if name:
                fields[field]['alias'] = name

        return {
            'attributes': attributes,
            'fields': fields
        }
