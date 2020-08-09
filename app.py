import os
import yaml
import json
from requests_oauthlib import OAuth1Session
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, g
from flask_babel import Babel
from oauth_wikidata import get_username, get_token
from wikidata import query_by_type, query_metadata_of_work, query_depicts_metadata,\
    api_post_request, post_search_entity, filter_by_tesauros

__dir__ = os.path.dirname(__file__)
app = Flask(__name__)
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'config.yaml'))))

BABEL = Babel(app)


##############################################################
# ESTRUTURA
##############################################################
@app.before_request
def init_profile():
    g.profiling = []


@app.before_request
def global_user():
    g.user = get_username()


@app.route('/login')
def login():
    client_key = app.config['CONSUMER_KEY']
    client_secret = app.config['CONSUMER_SECRET']
    base_url = 'https://www.wikidata.org/w/index.php'
    request_token_url = base_url + '?title=Special%3aOAuth%2finitiate'

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          callback_uri='oob')
    fetch_response = oauth.fetch_request_token(request_token_url)

    session['owner_key'] = fetch_response.get('oauth_token')
    session['owner_secret'] = fetch_response.get('oauth_token_secret')

    base_authorization_url = 'https://www.wikidata.org/wiki/Special:OAuth/authorize'
    authorization_url = oauth.authorization_url(base_authorization_url,
                                                oauth_consumer_key=client_key)
    return redirect(authorization_url)


@app.route("/oauth-callback", methods=["GET"])
def oauth_callback():
    base_url = 'https://www.wikidata.org/w/index.php'
    client_key = app.config['CONSUMER_KEY']
    client_secret = app.config['CONSUMER_SECRET']

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'])

    oauth_response = oauth.parse_authorization_response(request.url)
    verifier = oauth_response.get('oauth_verifier')
    access_token_url = base_url + '?title=Special%3aOAuth%2ftoken'
    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'],
                          verifier=verifier)

    oauth_tokens = oauth.fetch_access_token(access_token_url)
    session['owner_key'] = oauth_tokens.get('oauth_token')
    session['owner_secret'] = oauth_tokens.get('oauth_token_secret')

    return redirect(url_for("inicio"))


# Função para pegar a língua de preferência do usuário
@BABEL.localeselector
def get_locale():
    if request.args.get('lang'):
        session['lang'] = request.args.get('lang')

    return session.get('lang', 'pt')


# Função para mudar a língua de exibição do conteúdo
@app.route('/set_locale')
def set_locale():
    next_page = request.args.get('return_to')
    lang = request.args.get('lang')

    session["lang"] = lang
    return redirect(next_page)

##############################################################
# PÁGINAS
##############################################################
# Página inicial
@app.route('/')
@app.route('/home')
@app.route('/inicio')
def inicio():
    username = get_username()
    return render_template('inicio.html',
                           username=username,
                           lang=get_locale())


# Página sobre o aplicativo
@app.route('/about')
@app.route('/sobre')
def sobre():
    username = get_username()
    return render_template('sobre.html',
                           username=username,
                           lang=get_locale())


# Página com tutorial de como contribuir com o jogo
@app.route('/tutorial')
def tutorial():
    username = get_username()
    return render_template('tutorial.html',
                           username=username,
                           lang=get_locale())


# Página de visualização de coleções definidas por descritores
@app.route('/colecao/<type>')
def colecao(type):
    username = get_username()
    with open(os.path.join(app.static_folder, 'queries.json')) as category_queries:
        all_queries = json.load(category_queries)

    try:
        selected_query = all_queries[type]["query"]
        selection = query_by_type(selected_query)
        return render_template("colecao.html",
                               collection=selection,
                               username=username,
                               lang=get_locale())
    except:
        return redirect(url_for('inicio'))


# Página de visualização da obra e inserção de qualificadores
@app.route('/item/<qid>')
def item(qid):
    username = get_username()
    with open(os.path.join(app.static_folder, 'queries.json')) as category_queries:
        all_queries = json.load(category_queries)

    metadata_query = all_queries["Metadados"]["query"].replace("LANGUAGE", get_locale()).replace("QIDDAOBRA", qid)
    depicts_query = all_queries["Retratas"]["query"].replace("LANGUAGE", get_locale()).replace("QIDDAOBRA", qid)
    work_metadata = query_metadata_of_work(metadata_query, lang=get_locale)
    work_depicts = query_depicts_metadata(depicts_query, qid)

    return render_template('item.html',
                           metadata=work_metadata,
                           depicts_metadata=work_depicts,
                           username=username,
                           lang=get_locale())


##############################################################
# CONSULTAS E REQUISIÇÕES
##############################################################
# Requisição de adicionar qualificador à item retratado
@app.route('/add_stat', methods=['GET', 'POST'])
def add_statement():
    if request.method == 'POST':
        data = request.get_json()
        statement = data['statid'].split("#")[-1]  # Identificador da declaração
        pid = data['tipo']  # Tipo de qualificador
        qual = data['qual'].replace("Q", "")  # QID do qualificador a ser adicionado

        token = get_token()
        params = {
            "action": "wbsetqualifier",
            "format": "json",
            "claim": statement,
            "property": pid,
            "value": "{\"entity-type\":\"item\",\"numeric-id\":" + str(qual) + "}",
            "snaktype": "value",
            "token": token
        }

        results = api_post_request(params)

        return jsonify(results=results)
    return render_template('item.html')


@app.route('/search', methods=['GET', 'POST'])
def search_entity():
    if request.method == "POST":
        data = request.get_json()
        term = data['term']
        lang = get_locale()

        data = post_search_entity(term, lang)

        items = []
        for item in data["search"]:
            items.append(item["id"])

        query = filter_by_tesauros("wd:"+" wd:".join(items))

        if query:
            return jsonify(query), 200
        else:
            return jsonify(query), 204


if __name__ == '__main__':
    app.run()
