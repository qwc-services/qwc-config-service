#!/bin/python

# Copyright 2017, Sourcepole AG.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import os
try:
    from urllib.request import urlopen
except:
    from urllib2 import urlopen
try:
    from urllib.parse import quote, urljoin, urlsplit, urlunsplit
except:
    from urllib import quote
    from urlparse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree
import requests
import json
import traceback
import re
import uuid

from werkzeug.urls import url_parse


# get internal QGIS server URL from ENV
baseUrl = os.environ.get('QGIS_SERVER_URL', 'http://localhost/wms').rstrip('/') + '/'
qwc2_path = os.environ.get("QWC2_PATH", "qwc2").rstrip("/")

# load thumbnail from file or GetMap
def getThumbnail(configItem, resultItem, layers, crs, extent):
    if "thumbnail" in configItem:
        if os.path.exists(qwc2_path + "/assets/img/mapthumbs/" + configItem["thumbnail"]):
            resultItem["thumbnail"] = "img/mapthumbs/" + configItem["thumbnail"]
            return

    print("Using WMS GetMap to generate thumbnail for " + configItem["url"])

    # WMS GetMap request
    url = urljoin(baseUrl, configItem["url"]) + "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image/png&STYLES=&WIDTH=200&HEIGHT=100&CRS=" + crs
    bboxw = extent[2] - extent[0]
    bboxh = extent[3] - extent[1]
    bboxcx = 0.5 * (extent[0] + extent[2])
    bboxcy = 0.5 * (extent[1] + extent[3])
    imgratio = 200. / 100.
    if bboxw > bboxh:
        bboxratio = bboxw / bboxh
        if bboxratio > imgratio:
            bboxh = bboxw / imgratio
        else:
            bboxw = bboxh * imgratio
    else:
        bboxw = bboxh * imgratio
    adjustedExtent = [bboxcx - 0.5 * bboxw, bboxcy - 0.5 * bboxh,
                      bboxcx + 0.5 * bboxw, bboxcy + 0.5 * bboxh]
    url += "&BBOX=" + (",".join(map(str, adjustedExtent)))
    url += "&LAYERS=" + quote(",".join(layers).encode('utf-8'))

    try:
        request = urlopen(url)
        reply = request.read()
        basename = configItem["url"].rsplit("/")[-1] + ".png"
        try:
            os.makedirs(qwc2_path + "/assets/img/genmapthumbs/")
        except Exception as e:
            if not isinstance(e, FileExistsError): raise e
        thumbnail = qwc2_path + "/assets/img/genmapthumbs/" + basename
        with open(thumbnail, "wb") as fh:
            fh.write(reply)
        resultItem["thumbnail"] = "img/genmapthumbs/" + basename
    except Exception as e:
        print("ERROR generating thumbnail for WMS " + configItem["url"] + ":\n" + str(e))
        resultItem["thumbnail"] = "img/mapthumbs/default.jpg"
        traceback.print_exc()

def getEditConfig(editConfig, themesConfig):
    if not editConfig:
        return None
    elif os.path.isabs(editConfig) and os.path.exists(editConfig):
        with open(editConfig, encoding='utf-8') as fh:
            config = json.load(fh)
        return config
    else:
        dirname = os.path.dirname(themesConfig)
        if not dirname:
            dirname = "."
        filename = os.path.join(dirname, editConfig)
        if os.path.exists(filename):
            with open(filename, encoding='utf-8') as fh:
                config = json.load(fh)
            return config
    return None

def urlPath(url):
    parts = urlsplit(url)
    return urlunsplit(('', '', parts.path, parts.query, parts.fragment))


def wmsName(url):
    # get WMS name as relative path to QGIS server base path
    wms_name = url_parse(url).path
    server_base_path = url_parse(baseUrl).path
    if wms_name.startswith(server_base_path):
        wms_name = wms_name[len(server_base_path):]

    return wms_name


def uniqueThemeId(theme_name, config):
    # generate unique theme id from theme name
    used_theme_ids = config.get('usedThemeIds', [])
    if theme_name in used_theme_ids:
        # add suffix to name
        suffix = 1
        while "%s_%d" % (theme_name, suffix) in used_theme_ids:
            suffix += 1
        theme_name = "%s_%d" % (theme_name, suffix)
    # else keep original name

    used_theme_ids.append(theme_name)
    return theme_name


def getChildElement(parent, path, ns):
    for part in path:
        nodes = parent.findall(part, ns)
        if not nodes:
            return None
        parent = nodes[0]
    return parent


def getElementValue(element):
    try:
        return element.text
    except:
        return ""


def getChildElementValue(parent, path, ns):
    return getElementValue(getChildElement(parent, path, ns))

def getAttributeNS(element, name, np, ns):
    if element is None:
        return ""
    if np:
        return element.get("{%s}%s" % (ns[np], name))
    else:
        return element.get(name)


# recursively get layer tree
def getLayerTree(layer, permissions, resultLayers, visibleLayers, printLayers, level, collapseBelowLevel, titleNameMap, featureReports, searchLayers, np, ns):
    name = getChildElementValue(layer, [np['ns'] + "Name"], ns)
    title = getChildElementValue(layer, [np['ns'] + "Title"], ns)
    layers = layer.findall(np['ns'] + "Layer", ns)
    treeName = getChildElementValue(layer, [np['ns'] + "TreeName"], ns)

    # print("getLayerTree from root layer '%s' (devel %d) with permissions %s" % (name, level, permissions))
    if permissions is not None and level > 1 and name not in permissions['public_layers']:
        return  # omit layer

    # skip print layers
    for printLayer in printLayers:
        if type(printLayer) is list:
            for entry in printLayer:
                if entry["name"] == name:
                    return
        elif printLayer == name:
            return

    layerEntry = {"name": name, "title": title}

    if not layers:
        if layer.get("geometryType") == "WKBNoGeometry" or layer.get("geometryType") == "NoGeometry":
            # skip layers without geometry
            return

        # layer
        layerEntry["visibility"] = layer.get("visible") == "1"
        if layerEntry["visibility"]:
            # collect visible layers
            visibleLayers.append(name)

        layerEntry["queryable"] = layer.get("queryable") == "1"
        if layerEntry["queryable"] and layer.get("displayField"):
            layerEntry["displayField"] = layer.get("displayField")
        if name in searchLayers:
            layerEntry["searchterms"] = [searchLayers[name]]

        try:
            onlineResource = getChildElement(layer, [np['ns'] + "Attribution", np['ns'] + "OnlineResource"], ns)
            layerEntry["attribution"] = {
                "Title": getChildElementValue(layer, [np['ns'] + "Attribution", np['ns'] + "Title"], ns),
                "OnlineResource": getAttributeNS(onlineResource, 'href', 'xlink', ns)
            }
        except:
            pass
        try:
            layerEntry["abstract"] = getChildElementValue(layer, [np['ns'] + "Abstract"], ns)
        except:
            pass
        try:
            onlineResource = getChildElement(layer, [np['ns'] + "DataURL", np['ns'] + "OnlineResource"], ns)
            layerEntry["dataUrl"] = onlineResource.get(np['xlink'] + "href", ns)
        except:
            pass
        try:
            onlineResource = getChildElement(layer, [np['ns'] + "MetadataURL", np['ns'] + "OnlineResource"], ns)
            layerEntry["metadataUrl"] = onlineResource.get(np['xlink'] + "href", ns)
        except:
            pass
        try:
            keywords = []
            for keyword in getChildElement(layer, [np['ns'] + "KeywordList"], ns).findall(np['ns'] + "Keyword", ns):
                keywords.append(getElementValue(keyword))
            layerEntry["keywords"] = ",".join(keywords)
        except:
            pass

        if layer.get("transparency"):
            layerEntry["opacity"] = 255 - int(float(layer.get("transparency")) / 100 * 255)
        elif layer.get("opacity"):
            layerEntry["opacity"] = int(float(layer.get("opacity")) * 255)
        else:
            layerEntry["opacity"] = 255
        minScale = getChildElementValue(layer, [np['ns'] + "MinScaleDenominator"], ns)
        maxScale = getChildElementValue(layer, [np['ns'] + "MaxScaleDenominator"], ns)
        if minScale and maxScale:
            layerEntry["minScale"] = int(float(minScale))
            layerEntry["maxScale"] = int(float(maxScale))
        # use geographic bounding box, as default CRS may have inverted axis order with WMS 1.3.0
        geoBBox = getChildElement(layer, [np['ns'] + "EX_GeographicBoundingBox"], ns)
        if geoBBox:
            layerEntry["bbox"] = {
                "crs": "EPSG:4326",
                "bounds": [
                    float(getChildElementValue(geoBBox, [np['ns'] + "westBoundLongitude"], ns)),
                    float(getChildElementValue(geoBBox, [np['ns'] + "southBoundLatitude"], ns)),
                    float(getChildElementValue(geoBBox, [np['ns'] + "eastBoundLongitude"], ns)),
                    float(getChildElementValue(geoBBox, [np['ns'] + "northBoundLatitude"], ns))
                ]
            }
        if name in featureReports:
            layerEntry["featureReport"] = featureReports[name]
    else:
        # group
        layerEntry["mutuallyExclusive"] = layer.get("mutuallyExclusive") == "1"
        layerEntry["sublayers"] = []
        if layer.get("expanded") == "0":
            layerEntry["expanded"] = False
        else:
            layerEntry["expanded"] = False if collapseBelowLevel >= 0 and level >= collapseBelowLevel else True
        for sublayer in layers:
            getLayerTree(sublayer, permissions, layerEntry["sublayers"], visibleLayers, printLayers, level + 1, collapseBelowLevel, titleNameMap, featureReports, searchLayers, np, ns)

        if not layerEntry["sublayers"]:
            # skip empty groups
            return

    resultLayers.append(layerEntry)
    titleNameMap[treeName] = name

def themesConfigMTime():
    qwc2_path = os.environ.get('QWC2_PATH', 'qwc2/')
    themes_config_path = os.environ.get(
        'QWC2_THEMES_CONFIG', os.path.join(qwc2_path, 'themesConfig.json')
    )

    if os.path.isfile(themes_config_path):
        return os.path.getmtime(themes_config_path)
    return -1

# parse GetCapabilities for theme
def getTheme(config, permissions, configItem, result, resultItem, project_settings_cache, themesConfig):

    project_permissions = permissions.get(wmsName(configItem["url"])) if permissions is not None else None
    if not project_permissions:
        # no WMS permissions
        return

    cache = os.environ.get("__QWC_CONFIG_SERVICE_PROJECT_SETTINGS_CACHE", "0") == "1"
    ows_url = urljoin(baseUrl, configItem["url"])

    if cache and \
        ows_url in project_settings_cache and \
        project_settings_cache[ows_url]["timestamp"] != -1 and \
        project_settings_cache[ows_url]["timestamp"] >= themesConfigMTime():
        root = project_settings_cache[ows_url]["document"]
        print("getTheme: Using cached project settings for %s" % ows_url)
    else:
        # get GetProjectSettings
        response = requests.get(
            ows_url,
            params={
                'SERVICE': 'WMS',
                'VERSION': '1.3.0',
                'REQUEST': 'GetProjectSettings'
            },
            timeout=30
        )

        if response.status_code != requests.codes.ok:
            print("Could not get GetProjectSettings from %s:\n%s" % (ows_url, response.content))
            return None

        document = response.content

        # parse GetProjectSettings XML
        ElementTree.register_namespace('', 'http://www.opengis.net/wms')
        ElementTree.register_namespace('qgs', 'http://www.qgis.org/wms')
        ElementTree.register_namespace('sld', 'http://www.opengis.net/sld')
        ElementTree.register_namespace(
            'xlink', 'http://www.w3.org/1999/xlink'
        )
        root = ElementTree.fromstring(document)

        if cache:
            self.project_settings_cache[ows_url] = {
                "document": root,
                "timestamp": self.themesConfigMTime()
            }

    # use default namespace for XML search
    # namespace dict
    ns = {
        'ns': 'http://www.opengis.net/wms',
        'qgs': 'http://www.qgis.org/wms',
        'sld': 'http://www.opengis.net/sld',
        'xlink': 'http://www.w3.org/1999/xlink'
    }
    # namespace prefix
    np = {
        'ns': 'ns:',
        'qgs': 'qgs:',
        'sld': 'sld:',
        'xlink': 'xlink:'
    }
    if not root.tag.startswith('{http://'):
        # do not use namespace
        ns = {}
        np = {
            'ns': '',
            'qgs': '',
            'sld': '',
            'xlink': ''
        }

    topLayer = root.find('%sCapability/%sLayer' % (np['ns'], np['ns']), ns)

    # use name from config or fallback to WMS title
    wmsTitle = configItem.get("title") or getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "Title"], ns) or getChildElementValue(topLayer, [np['ns'] + "Title"], ns)

    # keywords
    keywords = []
    keywordList = getChildElement(root, [np['ns'] + "Service", np['ns'] + "KeywordList"], ns)
    if keywordList:
        for keyword in keywordList.findall("%sKeyword" % np['ns'], ns):
            value = getElementValue(keyword)
            if value != "infoMapAccessService":
                keywords.append(value)

    # collect WMS layers for printing
    printLayers = []
    if "backgroundLayers" in configItem:
        printLayers = [entry["printLayer"] for entry in configItem["backgroundLayers"] if "printLayer" in entry]

    # layer tree and visible layers
    collapseLayerGroupsBelowLevel = -1
    if "collapseLayerGroupsBelowLevel" in configItem:
        collapseLayerGroupsBelowLevel = configItem["collapseLayerGroupsBelowLevel"]

    layerTree = []
    visibleLayers = []
    titleNameMap = {}
    featureReports = configItem["featureReport"] if "featureReport" in configItem else {}
    searchLayers = {}
    if "searchProviders" in configItem:
        solr = [p for p in configItem["searchProviders"] if
                "provider" in p and p["provider"] == "solr"]
        if len(solr) == 1:
            searchLayers = solr[0].get("layers", {})
    getLayerTree(topLayer, project_permissions, layerTree, visibleLayers,
                 printLayers, 1, collapseLayerGroupsBelowLevel, titleNameMap, featureReports, searchLayers, np, ns)
    visibleLayers.reverse()

    # print templates
    printTemplates = []
    composerTemplates = getChildElement(root, [np['ns'] + "Capability", np['ns'] + "ComposerTemplates"], ns)
    if composerTemplates:
        for composerTemplate in composerTemplates.findall("%sComposerTemplate" % np['ns'], ns):
            template_name = composerTemplate.get("name")
            if template_name not in project_permissions['print_templates']:
                # skip if print template is not permitted
                continue

            printTemplate = {
                "name": template_name
            }
            composerMap = getChildElement(composerTemplate, [np['ns'] + "ComposerMap"], ns)
            if composerMap is not None:
                printTemplate["map"] = {
                    "name": composerMap.get("name"),
                    "width": float(composerMap.get("width")),
                    "height": float(composerMap.get("height"))
                }
            composerLabels = composerTemplate.findall("%sComposerLabel" % np['ns'], ns)
            labels = [composerLabel.get("name") for composerLabel in composerLabels]
            if "printLabelBlacklist" in configItem:
                labels = list(filter(lambda label: label not in configItem["printLabelBlacklist"], labels))

            if labels:
                printTemplate["labels"] = labels
            printTemplates.append(printTemplate)

    # drawing order
    drawingOrder = getChildElementValue(root, [np['ns'] + "Capability", np['ns'] + "LayerDrawingOrder"], ns).split(",")
    drawingOrder = list(map(lambda title: titleNameMap[title] if title in titleNameMap else title, drawingOrder))
    # filter by permissions
    drawingOrder = [
        title for title in drawingOrder
        if title in project_permissions['public_layers']
    ]

    # getmap formats
    availableFormats = []
    for format in getChildElement(root, [np['ns'] + "Capability", np['ns'] + "Request", np['ns'] + "GetMap"], ns).findall("%sFormat" % np['ns'], ns):
        availableFormats.append(getElementValue(format))

    # update theme config
    resultItem["url"] = urlPath(configItem["url"])
    resultItem["id"] = uniqueThemeId(wmsName(configItem["url"]), config)
    resultItem["name"] = getChildElementValue(topLayer, [np['ns'] + "Name"], ns)
    resultItem["title"] = wmsTitle
    resultItem["description"] = configItem["description"] if "description" in configItem else ""
    resultItem["attribution"] = {
        "Title": configItem["attribution"],
        "OnlineResource": configItem["attributionUrl"]
    }
    resultItem["abstract"] = getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "Abstract"], ns)
    resultItem["keywords"] = ", ".join(keywords)
    resultItem["onlineResource"] = getAttributeNS(getChildElement(root, [np['ns'] + "Service", np['ns'] + "OnlineResource"], ns), 'href', 'xlink', ns)
    resultItem["contact"] = {
        "person": getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "ContactInformation", np['ns'] + "ContactPersonPrimary", np['ns'] + "ContactPerson"], ns),
        "organization": getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "ContactInformation", np['ns'] + "ContactPersonPrimary", np['ns'] + "ContactOrganization"], ns),
        "position": getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "ContactInformation", np['ns'] + "ContactPosition"], ns),
        "phone": getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "ContactInformation", np['ns'] + "ContactVoiceTelephone"], ns),
        "email": getChildElementValue(root, [np['ns'] + "Service", np['ns'] + "ContactInformation", np['ns'] + "ContactElectronicMailAddress"], ns)
    }

    resultItem["wms_name"] = wmsName(configItem["url"])
    if "format" in configItem:
        resultItem["format"] = configItem["format"]
    resultItem["availableFormats"] = availableFormats
    if "tiled" in configItem:
        resultItem["tiled"] = configItem["tiled"]
    if "version" in configItem:
        resultItem["version"] = configItem["version"]
    elif "defaultWMSVersion" in config:
        resultItem["version"] = config["defaultWMSVersion"]
    resultItem["infoFormats"] = [getElementValue(format) for format in getChildElement(root, [np['ns'] + "Capability", np['ns'] + "Request", np['ns'] + "GetFeatureInfo"], ns).findall(np['ns'] + "Format", ns)]
    # use geographic bounding box for theme, as default CRS may have inverted axis order with WMS 1.3.0
    bounds = [
        float(getChildElementValue(topLayer, [np['ns'] + "EX_GeographicBoundingBox", np['ns'] + "westBoundLongitude"], ns)),
        float(getChildElementValue(topLayer, [np['ns'] + "EX_GeographicBoundingBox", np['ns'] + "southBoundLatitude"], ns)),
        float(getChildElementValue(topLayer, [np['ns'] + "EX_GeographicBoundingBox", np['ns'] + "eastBoundLongitude"], ns)),
        float(getChildElementValue(topLayer, [np['ns'] + "EX_GeographicBoundingBox", np['ns'] + "northBoundLatitude"], ns))
    ]
    resultItem["bbox"] = {
        "crs": "EPSG:4326",
        "bounds": bounds
    }
    if "extent" in configItem:
        resultItem["initialBbox"] = {
            "crs": configItem["mapCrs"] if "mapCrs" in configItem else "EPSG:4326",
            "bounds": configItem["extent"]
        }
    else:
        resultItem["initialBbox"] = resultItem["bbox"]
    if "scales" in configItem:
        resultItem["scales"] = configItem["scales"]
    if "printScales" in configItem:
        resultItem["printScales"] = configItem["printScales"]
    if "printResolutions" in configItem:
        resultItem["printResolutions"] = configItem["printResolutions"]
    if "printGrid" in configItem:
        resultItem["printGrid"] = configItem["printGrid"]
    # NOTE: skip root WMS layer
    resultItem["sublayers"] = layerTree[0]["sublayers"] if len(layerTree) > 0 and "sublayers" in layerTree[0] else []
    resultItem["expanded"] = True

    # external layers
    if "externalLayers" in configItem:
        # filter by permissions
        resultItem["externalLayers"] = [
            externalLayer for externalLayer in configItem["externalLayers"]
            if externalLayer.get('internalLayer')
            in project_permissions['public_layers']
        ]

    if "pluginData" in configItem:
        resultItem["pluginData"] = configItem["pluginData"]
    if "minSearchScaleDenom" in configItem:
            resultItem["minSearchScaleDenom"] = configItem["minSearchScaleDenom"]
    elif "minSearchScale" in configItem: # Legacy name
        resultItem["minSearchScaleDenom"] = configItem["minSearchScale"]
    if "themeInfoLinks" in configItem:
            resultItem["themeInfoLinks"] = configItem["themeInfoLinks"]
    if "backgroundLayers" in configItem:
        resultItem["backgroundLayers"] = configItem["backgroundLayers"]
    resultItem["searchProviders"] = configItem["searchProviders"] if "searchProviders" in configItem else []
    if "additionalMouseCrs" in configItem:
        resultItem["additionalMouseCrs"] = configItem["additionalMouseCrs"]
    if "mapCrs" in configItem:
        resultItem["mapCrs"] = configItem["mapCrs"]
    else:
        resultItem["mapCrs"] = "EPSG:3857"
    if printTemplates:
        resultItem["print"] = printTemplates
    resultItem["drawingOrder"] = drawingOrder
    extraLegenParams = configItem["extraLegendParameters"] if "extraLegendParameters" in configItem else ""
    resultItem["legendUrl"] = urlPath(getAttributeNS(getChildElement(root, [np['ns'] + "Capability", np['ns'] + "Request", np['sld'] + "GetLegendGraphic", np['ns'] + "DCPType", np['ns'] + "HTTP", np['ns'] + "Get", np['ns'] + "OnlineResource"], ns), 'href', 'xlink', ns) + extraLegenParams)
    resultItem["featureInfoUrl"] = urlPath(getAttributeNS(getChildElement(root, [np['ns'] + "Capability", np['ns'] + "Request", np['ns'] + "GetFeatureInfo", np['ns'] + "DCPType", np['ns'] + "HTTP", np['ns'] + "Get", np['ns'] + "OnlineResource"], ns), 'href', 'xlink', ns))
    resultItem["printUrl"] = urlPath(getAttributeNS(getChildElement(root, [np['ns'] + "Capability", np['ns'] + "Request", np['ns'] + "GetPrint", np['ns'] + "DCPType", np['ns'] + "HTTP", np['ns'] + "Get", np['ns'] + "OnlineResource"],  ns), 'href', 'xlink', ns))
    if "printLabelForSearchResult" in configItem:
        resultItem["printLabelForSearchResult"] = configItem["printLabelForSearchResult"]
    if "printLabelConfig" in configItem:
        resultItem["printLabelConfig"] = configItem["printLabelConfig"]

    if "watermark" in configItem:
        resultItem["watermark"] = configItem["watermark"]

    if "skipEmptyFeatureAttributes" in configItem:
        resultItem["skipEmptyFeatureAttributes"] = configItem["skipEmptyFeatureAttributes"]

    if "config" in configItem:
        resultItem["config"] = configItem["config"]

    if "mapTips" in configItem:
        resultItem["mapTips"] = configItem["mapTips"]

    if "userMap" in configItem:
        resultItem["userMap"] = configItem["userMap"]

    if project_permissions.get('edit_config'):
        # edit config from permissions
        resultItem["editConfig"] = project_permissions.get('edit_config')
        externalConfig = getEditConfig(configItem.get("editConfig", None), themesConfig)
        if externalConfig:
            for layer in externalConfig:
                form = externalConfig[layer].get("form", None)
                if form:
                    # Replace autogenerated config with external config if a form is specified
                    resultItem["editConfig"][layer] = externalConfig[layer]
    else:
        # get edit config from referenced JSON
        resultItem["editConfig"] = getEditConfig(configItem["editConfig"] if "editConfig" in configItem else None, themesConfig)

    # set default theme
    if configItem.get('default', False) or not result["themes"]["defaultTheme"]:
        result["themes"]["defaultTheme"] = resultItem["id"]

    # use first CRS for thumbnail request which is not CRS:84
    for item in topLayer.findall(np['ns'] + "CRS", ns):
        crs = getElementValue(item)
        if crs != "CRS:84":
            break
    extent = None
    for bbox in topLayer.findall(np['ns'] + "BoundingBox", ns):
        if bbox.get("CRS") == crs:
            extent = [
                float(bbox.get("minx")),
                float(bbox.get("miny")),
                float(bbox.get("maxx")),
                float(bbox.get("maxy"))
            ]
            break
    if extent:
        getThumbnail(configItem, resultItem, visibleLayers, crs, extent)


# recursively get themes for groups
def getGroupThemes(config, permissions, configGroup, result, resultGroup, project_settings_cache, groupCounter, themesConfig):
    for item in configGroup["items"]:
        itemEntry = {}
        getTheme(config, permissions, item, result, itemEntry, project_settings_cache, themesConfig)
        if itemEntry:
            resultGroup["items"].append(itemEntry)

    if "groups" in configGroup:
        for group in configGroup["groups"]:
            groupCounter += 1
            groupEntry = {
                "id": "g%d" % groupCounter,
                "title": group["title"],
                "items": [],
                "subdirs": []
            }
            getGroupThemes(config, permissions, group, result, groupEntry, project_settings_cache, groupCounter, themesConfig)
            resultGroup["subdirs"].append(groupEntry)


def collectExternalLayers(itemsGroup):
    """Recursively collect used external layer names.

    :param obj itemsGroup: Theme items group (themes|subdirs)
    """
    external_layers = []
    for item in itemsGroup["items"]:
        for layer in item.get('externalLayers', []):
            external_layers.append(layer.get('name'))

    if "subdirs" in itemsGroup:
        for group in itemsGroup["subdirs"]:
            external_layers += collectExternalLayers(group)

    return external_layers


def reformatAttribution(entry):
    entry["attribution"] = {
        "Title": entry["attribution"] if "attribution" in entry else None,
        "OnlineResource": entry["attributionUrl"] if "attributionUrl" in entry else None
    }
    entry.pop("attributionUrl", None)
    return entry


def genThemes(themesConfig, permissions=None, project_settings_cache=None):
    # load themesConfig.json
    try:
        with open(themesConfig, encoding='utf-8') as fh:
            config = json.load(fh)
    except:
        return {"error": "Failed to read themesConfig.json"}

    result = {
        "themes": {
            "title": "root",
            "subdirs": [],
            "items": [],
            "defaultTheme": None,
            "defaultScales": config["defaultScales"],
            "defaultPrintScales": config["defaultPrintScales"] if "defaultPrintScales" in config else None,
            "defaultPrintResolutions": config["defaultPrintResolutions"] if "defaultPrintResolutions" in config else None,
            "defaultPrintGrid": config["defaultPrintGrid"] if "defaultPrintGrid" in config else None,
            "pluginData": config["themes"]["pluginData"] if "pluginData" in config["themes"] else [],
            "themeInfoLinks": config["themes"]["themeInfoLinks"] if "themeInfoLinks" in config["themes"] else [],
            "externalLayers": config["themes"]["externalLayers"] if "externalLayers" in config["themes"] else [],
            "backgroundLayers": list(map(reformatAttribution, config["themes"]["backgroundLayers"])),
            "defaultWMSVersion": config["defaultWMSVersion"] if "defaultWMSVersion" in config else None
            }
    }

    # store used theme ids
    config['usedThemeIds'] = []

    groupCounter = 0
    getGroupThemes(config, permissions, config["themes"], result, result["themes"], project_settings_cache, groupCounter, themesConfig)

    if "backgroundLayers" in result["themes"]:
        # get thumbnails for background layers
        for backgroundLayer in result["themes"]["backgroundLayers"]:
            imgPath = "img/mapthumbs/" + backgroundLayer.get("thumbnail", "default.jpg")
            if not os.path.isfile(qwc2_path + "/assets/" + imgPath):
                imgPath = "img/mapthumbs/default.jpg"
            backgroundLayer["thumbnail"] = imgPath

    if "externalLayers" in result["themes"]:
        # collect used external layer names
        external_layers = collectExternalLayers(result["themes"])
        # unique external layer names
        external_layers = set(external_layers)

        # filter unused and restricted external layers
        result["themes"]["externalLayers"] = [
            layer for layer in result["themes"]["externalLayers"]
            if layer.get('name') in external_layers
        ]

    return result


if __name__ == '__main__':
    print("Reading " + themesConfig)
    themes = genThemes(themesConfig, perm)
    # write config file
    with open("./themes.json", "w") as fh:
        json.dump(themes, fh, indent=2, separators=(',', ': '), sort_keys=True)
