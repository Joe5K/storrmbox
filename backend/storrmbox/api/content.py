from threading import Thread

from flask import g
from flask_restplus import Resource, Namespace, fields
from searchyt import searchyt
from sqlalchemy.orm import load_only

from storrmbox.content.scraper import OmdbScraper, ImdbScraper
from storrmbox.exceptions import NotFoundException, InternalException
from storrmbox.extensions import auth, db
from storrmbox.models.content import Content, ContentType
from storrmbox.models.popular import Popular
from storrmbox.models.search import Search
from storrmbox.models.top import Top
from storrmbox.torrent.providers.eztv_provider import EztvProvider
from storrmbox.torrent.providers.leetx_provider import LeetxProvider
from storrmbox.torrent.scrapers import MovieTorrentScraper

api = Namespace('content', description='Content serving')

torrent_scraper = MovieTorrentScraper()
torrent_scraper.add_provider(LeetxProvider)
torrent_scraper.add_provider(EztvProvider)

yt_search = searchyt()

content_scraper = OmdbScraper()
imdb_scraper = ImdbScraper()

# API Model definitions
content_fields = api.model("Content", {
    "uid": fields.String,
    "type": fields.Integer,
    "title": fields.String,
    "year_released": fields.Integer,
    "year_end": fields.Integer,
    "runtime": fields.Integer,
    "rating": fields.Float,
    "plot": fields.String,
    "genres": fields.String,
    "poster": fields.String,
    "trailer_youtube_id": fields.String,
    "episode": fields.Integer,
    "season": fields.Integer,
    "parent": fields.String(attribute='parent_uid')
})

content_list_fields = api.model("ContentUidList", {
    "uids": fields.List(fields.String)
    # "type": fields.String
})

content_episode = api.model("ContentEpisode", {
    "uid": fields.String,
    "title": fields.String,
    "rating": fields.Float,
    "episode": fields.Integer
})

content_season = api.model("ContentSeason", {
    "season": fields.Integer,
    "episodes": fields.List(fields.Nested(content_episode))
})

content_season_list = api.model("ContentSeasonList", {
    "seasons": fields.List(fields.Nested(content_season))
})


@api.route("/<string:uid>")
class ContentResource(Resource):

    @auth.login_required
    @api.marshal_with(content_fields)
    def get(self, uid):
        if len(uid) > Content.uid.type.length:
            raise NotFoundException(f"Invalid UID '{uid}'")

        content = Content.get_by_uid(uid)

        if not content:
            raise NotFoundException(f"UID '{uid}' was not found")

        # Fetch poster and plot from omdb
        if not content.fetched:
            print(f"Fetching content {uid} ({content.imdb_id})")
            data = content_scraper.get_by_imdb_id(content.imdb_id)
            fetched = True  # Fix for omdb being too slow

            # Fix no data/poster/plot
            if not data.get('Poster'):
                fetched = False
                data['Poster'] = "https://lblzr.com/img/nopreview.png"

            if not data.get('Plot'):
                fetched = False
                data['Plot'] = ""

            # Fetch the yt trailer
            trailer_result = None
            if content.type != ContentType.episode:
                trailer_query = ("{} first season" if data['Type'] == "series" else "{} movie") + " official trailer"
                trailer_result = yt_search.search(trailer_query.format(data['Title']))[0]["id"]
                # if len(trailer_result) == 0:
                #    raise InternalException("Unable to fetch trailer from yt")

            # Update the content with new data and set the fetched field to true if fetched correctly
            content.update(True,
                           plot=data['Plot'],
                           poster=data['Poster'],
                           trailer_youtube_id=trailer_result,
                           fetched=fetched
                           )

        return content


@api.route("/<string:uid>/episodes")
class EpisodesContentResource(Resource):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @auth.login_required
    @api.marshal_with(content_season_list)
    def get(self, uid):
        content = Content.get_by_uid(uid)

        if not content:
            raise NotFoundException(f"Invalid uid '{uid}'")

        if content.type != ContentType.series:
            raise InternalException("Invalid content type")

        episodes = Content.query.options(
            load_only(Content.uid, Content.title, Content.rating, Content.episode, Content.season)) \
            .filter(Content.parent_uid == content.uid).all()

        if episodes:
            season_amount = max(episodes, key=lambda e: e.season).season
            result = [{"season": s, "episodes": [e for e in episodes if e.season == s]} for s in
                      range(1, season_amount + 1)]
        else:
            result = []

        return {"seasons": result}


@api.route("/<string:uid>/download")
class DownloadContentResource(Resource):

    @auth.login_required
    @api.marshal_with(content_fields)
    # @api.expect(parser)
    def post(self, uid):
        pass
        # ctype = 0
        # for t in args['type']:
        #    ctype |= ContentType[t.upper()]
        # torrents = []
        # if ctype & ContentType.MOVIE:
        #     torrents = torrent_scraper.search_movie(args['query'])
        # elif ctype & ContentType.SHOW:
        #     torrents = torrent_scraper.search_series(args['query'], 1, 1, VideoQuality.HD)
        #
        # for i, t in enumerate(torrents):
        #     res.append({
        #         'id': i,
        #         'name': 'test search content ' + str(i),
        #         'year': 2019,
        #         'year_end': None,
        #         'description': 'Name: {}, Seeders: {}, Leechers: {}'.format(t.name, t.seeders, t.leechers),
        #         'rating': i % 5,
        #         'type': ctype,
        #         'thumbnail': 'https://picsum.photos/200/300'
        #     })
        # return []


@api.route("/popular")
class PopularContentResource(Resource):
    popular_parser = api.parser()
    popular_parser.add_argument('type', type=str, choices=tuple(t.name for t in ContentType),
                                help='Type of the content', required=True)

    def _get_popular(self, ctype):
        # Fetch popular content
        cache = []
        for iid in imdb_scraper.get_popular(ctype):
            content = Content.get_by_imdb_id(iid)

            # If the content is not already in db skip it
            if content:
                cache.append(Popular(
                    content_id=content.uid,
                    type=ctype.value
                ))

        return cache

    @auth.login_required
    @api.marshal_with(content_list_fields)
    @api.expect(popular_parser)
    def get(self):
        args = PopularContentResource.popular_parser.parse_args()
        ctype = ContentType[args['type']]

        return {"uids": [c.content_id for c in Popular.fetch(Popular.type, ctype, self._get_popular, ctype)]}


@api.route("/top")
class TopContentResource(Resource):
    top_parser = api.parser()
    top_parser.add_argument('type', type=str, choices=tuple(t.name for t in ContentType),
                            help='Type of the content', required=True)

    def _get_top(self, ctype):
        # Fetch top content
        cache = []
        for iid in imdb_scraper.get_top(ctype):
            content = Content.get_by_imdb_id(iid)

            # If the content is not already in db skip it
            if content:
                cache.append(Top(
                    content_id=content.uid,
                    type=ctype.value
                ))

        return cache

    @auth.login_required
    @api.marshal_with(content_list_fields)
    @api.expect(top_parser)
    def get(self):
        args = TopContentResource.top_parser.parse_args()
        ctype = ContentType[args['type']]

        return {"uids": [c.content_id for c in Top.fetch(Top.type, ctype, self._get_top, ctype)]}


@api.route("/search")
class SearchContentResource(Resource):
    search_parser = api.parser()
    search_parser.add_argument('query', type=str, help='Search query', required=True)
    search_parser.add_argument('type', type=str, choices=tuple(t.name for t in ContentType),
                               help='Type of the content', required=False)
    search_parser.add_argument('amount', type=int, default=6,
                               help='Minimum amount of the content returned', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @auth.login_required
    @api.marshal_with(content_list_fields, as_list=True)
    @api.expect(search_parser)
    def get(self):
        args = SearchContentResource.search_parser.parse_args()

        # Store the search in db
        db.session.add(Search(
            user=g.user,
            query=args['query']
        ))

        # Search the query in db first
        results = Content.query.options(load_only("uid"))\
            .filter(Content.title.ilike(f"%{args['query']}%"), Content.votes.isnot(None))\
            .order_by(Content.votes.desc()).all()

        # Filter content if type is specified
        uids = []
        for r in results:
            if not args['type'] or r.type.name == args['type']:
                uids.append(r.uid)

        # We have enough data, return already
        if len(uids) >= int(args['amount']):
            return {"uids": uids}

        # Query the api until we have enough results, maximum up to page 5
        continue_search = True
        current_page = 1
        while continue_search and current_page <= 5:
            content = content_scraper.search(args['query'], current_page)
            # Break if no content was found
            if not content:
                break

            content, total_results = content
            for c in content:
                # Skip games ( why are they even there?? )
                if c['Type'] == "game":
                    continue

                # Skip content with different type
                if args['type'] and args['type'] != c['Type']:
                    continue

                # Check if the object is not already in the db/result and skip it
                cm = Content.get_by_imdb_id(c['imdbID'])
                if cm:
                    if cm.uid not in uids:
                        uids.append(cm.uid)
                    continue

                # Only add content with poster
                if c['Poster'] != "N/A":
                    # Add the content
                    cm = Content(
                        imdb_id=c['imdbID'],
                        type=ContentType[c['Type']].value,
                        title=c['Title']
                    )
                    db.session.add(cm)
                    uids.append(cm.uid)

            # If we are on the last page or we have enough results exit the loop
            current_page += 1
            if (current_page * 10) > total_results or len(uids) >= int(args['amount']):
                continue_search = False

        # Commit all new data
        db.session.commit()

        return {"uids": uids}


@api.route("/reload")
class ReloadContentResource(Resource):

    # TODO: make this admin-only
    @auth.login_required
    def get(self):
        thread = Thread(target=self.update_data)
        thread.start()

    @staticmethod
    def update_data():
        chunk = 0
        objects = []
        try:
            # TODO: Only update existing content
            # Temporarily drop the whole DB each time
            # Content.__table__.drop(db.engine)

            for c in imdb_scraper.get_content():

                c["uid"] = Content.generate_uid(c["imdb_id"])
                objects.append(c)
                chunk += 1

                if chunk >= 100000:
                    db.session.bulk_insert_mappings(Content, objects)
                    db.session.commit()
                    objects = []
                    chunk = 0

            db.session.bulk_insert_mappings(Content, objects)
            db.session.commit()

        finally:
            pass
