import requests
import roman
import math
import re
import urllib.parse as ur
from flask import current_app, session
from requests_oauthlib import OAuth1Session

metadados = {"P18": "imagem",
             "P989": "audio",
             "P31": "instancia_qid",
             "P170": "criador_qid",
             "P571": "data",
             "P186": "material_qid",
             "P88": "encomendador_qid"}

##############################################################
# QUERIES
##############################################################
def query_wikidata(query):
    url = "https://query.wikidata.org/sparql"
    params = {
        "query": query,
        "format": "json"
    }
    result = requests.get(url=url, params=params, headers={'User-agent': 'WikiMI CQREV 1.0'})
    data = result.json()
    return data


def query_by_type(query, lang="pt-br"):
    new_query = query.replace("LANGUAGE", lang)
    data = query_wikidata(new_query)
    result = data["results"]["bindings"]

    images = []
    for image in result:
        images.append({
            "qid": image["item_qid"]["value"],
            "label": image["item_label"]["value"],
            "imagem": ur.quote(image["imagem"]["value"])
        })

    return images


def query_quantidade(query, lang="pt-br"):
    data = query_wikidata(query)
    try:
        valor = int(data["results"]["bindings"][0]["number_works"]["value"])
    except:
        valor = 0
    return valor


def query_metadata_of_work(query, lang="pt-br"):
    data = query_wikidata(query)
    if "results" in data and "bindings" in data["results"]:
        result = data["results"]["bindings"][0]
        format_dates_in_result(result, lang)
        get_values_lists(result)
        if "obra" in result and len(result["obra"]) > 0:
            result["obra_qid"] = [result["obra"][0].replace("http://www.wikidata.org/entity/", "")]
    if not result or result == [{}]:
        result = ""
    return result


def query_depicts_metadata(query, qid):
    data = query_wikidata(query)
    result = data["results"]["bindings"]
    for depicted_entity in result:
        get_values_lists(depicted_entity, sep=";%;")
        if 'retrata_stat_id' in depicted_entity:
            depicted_entity['retrata_stat_id'][0] = "https://www.wikidata.org/wiki/"+qid+"#"+depicted_entity['retrata_stat_id'][0].replace('-', '$', 1)
        if "retrata_descr" not in depicted_entity:
            depicted_entity["retrata_descr"] = ""
        if "retrata_label" not in depicted_entity:
            depicted_entity["retrata_label"] = ""
    return result


def format_dates_in_result(result, lang="pt-br"):
    if "data" in result:
        datas = result["data"]["value"].split(";")
        novas_datas = []
        for data in datas:
            novas_datas.append(format_dates(data, lang))
        result["data"]["value"] = ";".join(novas_datas)


def format_dates(time, lang="pt-br"):
    year, month, day, precision = list(map(int, re.findall(r'\d+', time)))
    if precision == 7:
        if lang == "en":
            date = "%dth century" % (int(year/100)+1)
        else:
            if year % 100 == 0:
                date = "Século %s" % (roman.toRoman(math.floor(year/100)))
            else:
                date = "Século %s" % (roman.toRoman(math.floor(year / 100) + 1))
    elif precision == 8:
        if lang == "en":
            date = "%ds" % (int(year/10)*10)
        else:
            date = "Década de %d" % (int(year/10)*10)
    elif precision == 9:
        date = "%d" % year
    elif precision == 10:
        date = "%d/%d" % (month, year)
    elif precision == 11:
        if lang == "en":
            date = "%d/%d/%d" % (month, day, year)
        else:
            date = "%d/%d/%d" % (day, month, year)
    else:
        date = ""
    return date


def get_values_lists(result, sep=";"):
    for metadata_key, metadata_dict in result.items():
        result[metadata_key] = list(filter(None, metadata_dict["value"].split(sep)))


def api_get_items_with_labels(item, lang="pt-br"):
    url = 'https://www.wikidata.org/w/api.php'
    params = {
        'action': 'wbgetentities',
        'ids': item,
        'props': "claims",
        'format': 'json',
        'uselang': lang,
    }
    result = requests.get(url=url, params=params, headers={'User-agent': 'WikiMI CQREV 1.0'})
    new_result = {}
    data = result.json()
    properties = data["entities"][item]["claims"]
    if "entities" in data and item in data["entities"] and "claims" in data["entities"][item]:
        for property in properties:
            if property in metadados:
                key = metadados[property]
                values = []
                for value in data["entities"][item]["claims"][property]:
                    values.append(value["mainsnak"]["datavalue"]["value"])
                    if value["rank"] == "preferred":
                        new_result[key] = value["mainsnak"]["datavalue"]["value"]
                        break
                if key not in new_result:
                    new_result[key] = values

    return new_result


def api_post_request(params):
    app = current_app
    url = 'https://www.wikidata.org/w/api.php'
    client_key = app.config['CONSUMER_KEY']
    client_secret = app.config['CONSUMER_SECRET']
    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'])
    return oauth.post(url, data=params, timeout=4)


def post_search_entity(term, lang="pt-br"):
    url = 'https://www.wikidata.org/w/api.php'
    params = {
        'action': 'wbsearchentities',
        'search': term,
        'language': lang,
        'format': 'json',
        'limit': 50,
        'uselang': lang,
    }
    result = requests.get(url=url, params=params, headers={'User-agent': 'WikiMI CQREV 1.0'})
    data = result.json()

    return data


def filter_by_tesauros(qids, lang="pt-br"):
    if lang == "pt-br" or lang == "pt":
        lang = "pt-br,pt"
    data = query_wikidata("SELECT DISTINCT ?item_qid ?item_label ?item_descr WHERE { SERVICE wikibase:label {bd:serviceParam wikibase:language '"+lang+"'. ?item rdfs:label ?item_label. ?item schema:description ?item_descr.} VALUES ?item {"+qids+"} VALUES ?propriedade {wdt:P8514 wdt:P3832 wdt:P1014 wdt:P1256 wdt:P7749} ?item ?propriedade []. BIND(SUBSTR(STR(?item),32) AS ?item_qid) }")
    results = data["results"]["bindings"]
    query = []
    for item in results:
        if "item_qid" in item:
            qid = item["item_qid"]["value"]
        else:
            qid = ""
        if "item_label" in item:
            label = item["item_label"]["value"]
        else:
            label = ""
        if "item_descr" in item:
            descr = item["item_descr"]["value"]
        else:
            descr = ""
        query.append({"qid": qid,
                      "label": label,
                      "descr": descr})
    return query