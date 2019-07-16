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
from xml.dom.minidom import parseString
import json
import traceback
import re
import uuid

from werkzeug.urls import url_parse


# get internal QGIS server URL from ENV
baseUrl = os.environ.get('QGIS_SERVER_URL', 'http://localhost/wms').rstrip('/') + '/'
qwc2_path = os.environ.get("QWC2_PATH", "qwc2").rstrip("/")
themesConfig = os.environ.get("QWC2_THEMES_CONFIG", "themesConfig.json")

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

def getEditConfig(editConfig):
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

def getDirectChildElements(parent, tagname):
    return [node for node in parent.childNodes if node.nodeName.split(':')[-1] == tagname]


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


def getChildElement(parent, path):
    for part in path.split("/"):
        for node in parent.childNodes:
            if node.nodeName.split(':')[-1] == part:
                parent = node
                break
        else:
            return None
    return parent


def getElementValue(element):
    return element.firstChild.nodeValue if element and element.firstChild else ""


def getChildElementValue(parent, path):
    return getElementValue(getChildElement(parent, path))


# recursively get layer tree
def getLayerTree(layer, permissions, resultLayers, visibleLayers, printLayers, level, collapseBelowLevel, titleNameMap, featureReports):
    name = getChildElementValue(layer, "Name")
    title = getChildElementValue(layer, "Title")
    layers = getDirectChildElements(layer, "Layer")
    treeName = getChildElementValue(layer, "TreeName")

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
        if layer.getAttribute("geometryType") == "WKBNoGeometry":
            # skip layers without geometry
            return

        # layer
        layerEntry["visibility"] = layer.getAttribute("visible") == "1"
        if layerEntry["visibility"]:
            # collect visible layers
            visibleLayers.append(name)

        layerEntry["queryable"] = layer.getAttribute("queryable") == "1"
        if layerEntry["queryable"] and layer.getAttribute("displayField"):
            layerEntry["displayField"] = layer.getAttribute("displayField")

        try:
            onlineResource = getChildElement(layer, "Attribution/OnlineResource")
            layerEntry["attribution"] = {
                "Title": getChildElementValue(layer, "Attribution/Title"),
                "OnlineResource": onlineResource.getAttribute("xlink:href") if onlineResource else ""
            }
        except:
            pass
        try:
            layerEntry["abstract"] = getChildElementValue(layer, "Abstract")
        except:
            pass
        try:
            onlineResource = getChildElement(layer, "DataURL/OnlineResource")
            layerEntry["dataUrl"] = onlineResource.getAttribute("xlink:href")
        except:
            pass
        try:
            onlineResource = getChildElement(layer, "MetadataURL/OnlineResource")
            layerEntry["metadataUrl"] = onlineResource.getAttribute("xlink:href")
        except:
            pass
        try:
            keywords = []
            for keyword in getChildElement(layer, "KeywordList").getElementsByTagName("Keyword"):
                keywords.append(getElementValue(keyword))
            layerEntry["keywords"] = ",".join(keywords)
        except:
            pass

        if layer.getAttribute("transparency"):
            layerEntry["opacity"] = 255 - int(float(layer.getAttribute("transparency")) / 100 * 255)
        else:
            layerEntry["opacity"] = 255
        minScale = getChildElementValue(layer, "MinScaleDenominator")
        maxScale = getChildElementValue(layer, "MaxScaleDenominator")
        if minScale and maxScale:
            layerEntry["minScale"] = int(float(minScale))
            layerEntry["maxScale"] = int(float(maxScale))
        # use geographic bounding box, as default CRS may have inverted axis order with WMS 1.3.0
        geoBBox = getChildElement(layer, "EX_GeographicBoundingBox")
        if geoBBox:
            layerEntry["bbox"] = {
                "crs": "EPSG:4326",
                "bounds": [
                    float(getChildElementValue(geoBBox, "westBoundLongitude")),
                    float(getChildElementValue(geoBBox, "southBoundLatitude")),
                    float(getChildElementValue(geoBBox, "eastBoundLongitude")),
                    float(getChildElementValue(geoBBox, "northBoundLatitude"))
                ]
            }
        if name in featureReports:
            layerEntry["featureReport"] = featureReports[name]
    else:
        # group
        layerEntry["mutuallyExclusive"] = layer.getAttribute("mutuallyExclusive") == "1"
        layerEntry["sublayers"] = []
        layerEntry["expanded"] = False if collapseBelowLevel >= 0 and level >= collapseBelowLevel else True
        for sublayer in layers:
            getLayerTree(sublayer, permissions, layerEntry["sublayers"], visibleLayers, printLayers, level + 1, collapseBelowLevel, titleNameMap, featureReports)

        if not layerEntry["sublayers"]:
            # skip empty groups
            return

    resultLayers.append(layerEntry)
    titleNameMap[treeName] = name


# parse GetCapabilities for theme
def getTheme(config, permissions, configItem, result, resultItem):
    url = urljoin(baseUrl, configItem["url"]) + "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetProjectSettings"

    try:
        project_permissions = permissions.get(wmsName(configItem["url"])) if permissions is not None else None
        if not project_permissions:
            # no WMS permissions
            return

        reply = urlopen(url).read()
        capabilities = parseString(reply)
        capabilities = capabilities.getElementsByTagName("WMS_Capabilities")[0]

        topLayer = getChildElement(getChildElement(capabilities, "Capability"), "Layer")

        # use name from config or fallback to WMS title
        wmsTitle = configItem.get("title") or getChildElementValue(capabilities, "Service/Title") or getChildElementValue(topLayer, "Title")

        # keywords
        keywords = []
        keywordList = getChildElement(capabilities, "Service/KeywordList")
        if keywordList:
            for keyword in keywordList.getElementsByTagName("Keyword"):
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
        getLayerTree(topLayer, project_permissions, layerTree, visibleLayers,
                     printLayers, 1, collapseLayerGroupsBelowLevel, titleNameMap, featureReports)
        visibleLayers.reverse()

        # print templates
        printTemplates = []
        composerTemplates = getChildElement(capabilities, "Capability/ComposerTemplates")
        if composerTemplates:
            for composerTemplate in composerTemplates.getElementsByTagName("ComposerTemplate"):
                template_name = composerTemplate.getAttribute("name")
                if template_name not in project_permissions['print_templates']:
                    # skip if print template is not permitted
                    continue

                printTemplate = {
                    "name": template_name
                }
                composerMap = getChildElement(composerTemplate, "ComposerMap")
                if composerMap:
                    printTemplate["map"] = {
                        "name": composerMap.getAttribute("name"),
                        "width": float(composerMap.getAttribute("width")),
                        "height": float(composerMap.getAttribute("height"))
                    }
                composerLabels = composerTemplate.getElementsByTagName("ComposerLabel")
                labels = [composerLabel.getAttribute("name") for composerLabel in composerLabels]
                if "printLabelBlacklist" in configItem:
                    labels = list(filter(lambda label: label not in configItem["printLabelBlacklist"], labels))

                if labels:
                    printTemplate["labels"] = labels
                printTemplates.append(printTemplate)

        # drawing order
        drawingOrder = getChildElementValue(capabilities, "Capability/LayerDrawingOrder").split(",")
        drawingOrder = list(map(lambda title: titleNameMap[title] if title in titleNameMap else title, drawingOrder))
        # filter by permissions
        drawingOrder = [
            title for title in drawingOrder
            if title in project_permissions['public_layers']
        ]

        # getmap formats
        availableFormats = []
        for format in getChildElement(capabilities, "Capability/Request/GetMap").getElementsByTagName("Format"):
          availableFormats.append(getElementValue(format))

        # update theme config
        resultItem["url"] = urlPath(configItem["url"])
        resultItem["id"] = uniqueThemeId(wmsName(configItem["url"]), config)
        resultItem["name"] = getChildElementValue(topLayer, "Name")
        resultItem["title"] = wmsTitle
        resultItem["attribution"] = {
            "Title": configItem["attribution"],
            "OnlineResource": configItem["attributionUrl"]
        }
        resultItem["keywords"] = ", ".join(keywords)
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
        resultItem["infoFormats"] = [getElementValue(format) for format in getChildElement(capabilities, "Capability/Request/GetFeatureInfo").getElementsByTagName("Format")]
        # use geographic bounding box for theme, as default CRS may have inverted axis order with WMS 1.3.0
        bounds = [
            float(getChildElementValue(topLayer, "EX_GeographicBoundingBox/westBoundLongitude")),
            float(getChildElementValue(topLayer, "EX_GeographicBoundingBox/southBoundLatitude")),
            float(getChildElementValue(topLayer, "EX_GeographicBoundingBox/eastBoundLongitude")),
            float(getChildElementValue(topLayer, "EX_GeographicBoundingBox/northBoundLatitude"))
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
        resultItem["legendUrl"] = urlPath(getChildElement(capabilities, "Capability/Request/GetLegendGraphic/DCPType/HTTP/Get/OnlineResource").getAttribute("xlink:href") + extraLegenParams)
        resultItem["featureInfoUrl"] = urlPath(getChildElement(capabilities, "Capability/Request/GetFeatureInfo/DCPType/HTTP/Get/OnlineResource").getAttribute("xlink:href"))
        resultItem["printUrl"] = urlPath(getChildElement(capabilities, "Capability/Request/GetPrint/DCPType/HTTP/Get/OnlineResource").getAttribute("xlink:href"))
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
        else:
            # get edit config from referenced JSON
            resultItem["editConfig"] = getEditConfig(configItem["editConfig"] if "editConfig" in configItem else None);

        # set default theme
        if configItem.get('default', False) or not result["themes"]["defaultTheme"]:
            result["themes"]["defaultTheme"] = resultItem["id"]

        # use first CRS for thumbnail request which is not CRS:84
        for item in topLayer.getElementsByTagName("CRS"):
            crs = getElementValue(item)
            if crs != "CRS:84":
                break
        extent = None
        for bbox in topLayer.getElementsByTagName("BoundingBox"):
            if bbox.getAttribute("CRS") == crs:
                extent = [
                    float(bbox.getAttribute("minx")),
                    float(bbox.getAttribute("miny")),
                    float(bbox.getAttribute("maxx")),
                    float(bbox.getAttribute("maxy"))
                ]
                break
        if extent:
            getThumbnail(configItem, resultItem, visibleLayers, crs, extent)

    except Exception as e:
        print("ERROR reading WMS GetProjectSettings of " + configItem["url"] + ":\n" + str(e))
        resultItem["error"] = "Could not read GetProjectSettings"
        resultItem["title"] = "Error"
        traceback.print_exc()


# recursively get themes for groups
def getGroupThemes(config, permissions, configGroup, result, resultGroup):
    for item in configGroup["items"]:
        itemEntry = {}
        getTheme(config, permissions, item, result, itemEntry)
        if itemEntry:
            resultGroup["items"].append(itemEntry)

    if "groups" in configGroup:
        for group in configGroup["groups"]:
            groupEntry = {
                "title": group["title"],
                "items": [],
                "subdirs": []
            }
            getGroupThemes(config, permissions, group, result, groupEntry)
            resultGroup["subdirs"].append(groupEntry)


def reformatAttribution(entry):
    entry["attribution"] = {
        "Title": entry["attribution"] if "attribution" in entry else None,
        "OnlineResource": entry["attributionUrl"] if "attributionUrl" in entry else None
    }
    entry.pop("attributionUrl", None)
    return entry


def genThemes(themesConfig, permissions=None):
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
            "backgroundLayers": list(map(reformatAttribution, config["themes"]["backgroundLayers"])),
            "defaultWMSVersion": config["defaultWMSVersion"] if "defaultWMSVersion" in config else None
            }
    }

    # store used theme ids
    config['usedThemeIds'] = []

    getGroupThemes(config, permissions, config["themes"], result, result["themes"])

    if "backgroundLayers" in result["themes"]:
        # get thumbnails for background layers
        for backgroundLayer in result["themes"]["backgroundLayers"]:
            imgPath = "img/mapthumbs/" + backgroundLayer.get("thumbnail", "default.jpg")
            if not os.path.isfile(qwc2_path + "/assets/" + imgPath):
                imgPath = "img/mapthumbs/default.jpg"
            backgroundLayer["thumbnail"] = imgPath

    return result


if __name__ == '__main__':
    print("Reading " + themesConfig)
    themes = genThemes(themesConfig)
    # write config file
    with open("./themes.json", "w") as fh:
        json.dump(themes, fh, indent=2, separators=(',', ': '), sort_keys=True)
