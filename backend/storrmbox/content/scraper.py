from logging import getLogger
from os import getenv

from bs4 import BeautifulSoup
from requests import Session

from storrmbox.torrent.scrapers import ContentType


class ContentScraper(object):

    def __init__(self):
        self.log = getLogger("content_scraper")
        self.req = Session()
        self.req.headers.update({
            "accept-language": "en-US,en"
        })
        self.url = ""
        self.api_key = ""

    def get(self, params={}, api_key=False, url=None):
        if api_key:
            params["apiKey"] = self.api_key

        if url is None:
            url = self.url

        resp = self.req.get(url=url, params=params)

        if resp.status_code == 401:
            raise Exception("Invalid OMDB api key! Please set it in the .env file.")

        if resp.status_code != 200:
            self.log.error(f"Error while scraping content ({resp.status_code})")

        return resp

    def search(self, query: str, page=1):
        return []


class OmdbScraper(ContentScraper):

    def __init__(self):
        super().__init__()
        self.url = "https://www.omdbapi.com/"
        self.api_key = getenv('OMDB_API_KEY')

        if not self.api_key:
            raise Exception("Invalid OMDB api key! Please set it in the .env file.")

    def search(self, query: str, page=1):
        resp = self.get({"s": query, "page": page}, True)

        data = resp.json()

        if data["Response"] == "True":
            return data["Search"], int(data['totalResults'])

        self.log.error(f"Error while searching content '{data.get('Error', resp.text)}'")
        return []

    def get_by_imdb_id(self, id: str):
        resp = self.get({"i": id, "plot": "full"}, True)

        data = resp.json()

        if data["Response"] == "True":
            return data

        self.log.error(f"Error while searching content '{data.get('Error', resp.text)}'")
        return None


class ImdbScraper(ContentScraper):

    def __init__(self):
        super().__init__()
        self.url = "https://www.imdb.com/"
        self.omdb = OmdbScraper()

    def _get_page_ids(self, url: str, params={}):
        resp = self.get(params, url=url)
        soup = BeautifulSoup(resp.text, features="html.parser")
        table = soup.find("tbody")

        res = []
        for row in table.find_all("tr"):
            # title = row.find(class_="titleColumn").find("a").text
            # print(title)

            # If the content has no rating skip it
            stars = row.find("td", class_="imdbRating").find("strong")
            if not stars:
                continue

            # If the release year is larger than current year skip it
            # year = row.find(class_="secondaryInfo").text[1:-1]
            # print(year)
            # if datetime.date.today().year < int(year):
            #     continue

            cid = row.find("td", class_="watchlistColumn").find("div").attrs["data-tconst"]
            res.append(cid)

        return res

    def popular(self, ctype: ContentType):
        url = self.url
        if ctype == ContentType.series:
            url += "chart/tvmeter"
        elif ctype == ContentType.movie:
            url += "chart/moviemeter"

        resp = self._get_page_ids(url)

        return resp

    def top(self, ctype: ContentType):
        url = self.url
        if ctype == ContentType.series:
            url += "chart/toptv"
        elif ctype == ContentType.movie:
            url += "chart/top"

        resp = self._get_page_ids(url, {"sort": "us,des"})

        return resp
