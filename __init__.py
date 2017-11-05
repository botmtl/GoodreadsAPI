#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

import re

from calibre.utils.config_base import Option
from calibre.utils.logging import ThreadSafeLog
from calibre.utils.titlecase import titlecase
import traceback

__license__ = 'GPL v3'
__copyright__ = '2017, botmtl@gmail.com'
__docformat__ = 'restructuredtext en'

from urllib2 import urlopen
from lxml import objectify, etree
from calibre.ebooks.metadata.book.base import Metadata
import datetime
import sys
# noinspection PyUnresolvedReferences
from lxml.etree import Element
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import Source, fixcase, fixauthors


class _ISBNConvert(object):

    @staticmethod
    def isbn_strip(isbn):
        """Strip whitespace, hyphens, etc. from an ISBN number and return
    the result."""
        short = re.sub("\W", "", isbn)
        return re.sub("\D", "X", short)

    @staticmethod
    def convert(isbn):
        """Convert an ISBN-10 to ISBN-13 or vice-versa."""
        short = _ISBNConvert.isbn_strip(isbn)
        if not _ISBNConvert.isValid(short):
            raise Exception("Invalid ISBN")
        if len(short) == 10:
            stem = "978" + short[:-1]
            return stem + _ISBNConvert.check(stem)
        else:
            if short[:3] == "978":
                stem = short[3:-1]
                return stem + _ISBNConvert.check(stem)
            else:
                raise Exception("ISBN not convertible")

    @staticmethod
    def isValid(isbn):
        """Check the validity of an ISBN. Works for either ISBN-10 or ISBN-13."""
        short = _ISBNConvert.isbn_strip(isbn)
        if len(short) == 10:
            return _ISBNConvert.isI10(short)
        elif len(short) == 13:
            return _ISBNConvert.isI13(short)
        else:
            return False

    @staticmethod
    def check(stem):
        """Compute the check digit for the stem of an ISBN. Works with either
        the first 9 digits of an ISBN-10 or the first 12 digits of an ISBN-13."""
        short = _ISBNConvert.isbn_strip(stem)
        if len(short) == 9:
            return _ISBNConvert.checkI10(short)
        elif len(short) == 12:
            return _ISBNConvert.checkI13(short)
        else:
            return False

    @staticmethod
    def checkI10(stem):
        """Computes the ISBN-10 check digit based on the first 9 digits of a stripped ISBN-10 number."""
        chars = list(stem)
        sum = 0
        digit = 10
        for char in chars:
            sum += digit * int(char)
            digit -= 1
        check = 11 - (sum % 11)
        if check == 10:
            return "X"
        elif check == 11:
            return "0"
        else:
            return str(check)

    @staticmethod
    def isI10(isbn):
        """Checks the validity of an ISBN-10 number."""
        short = _ISBNConvert.isbn_strip(isbn)
        if len(short) != 10:
            return False
        chars = list(short)
        sum = 0
        digit = 10
        for char in chars:
            if char == 'X' or char == 'x':
                char = "10"
            sum += digit * int(char)
            digit -= 1
        remainder = sum % 11
        if remainder == 0:
            return True
        else:
            return False

    @staticmethod
    def checkI13(stem):
        """Compute the ISBN-13 check digit based on the first 12 digits of a stripped ISBN-13 number. """
        chars = list(stem)
        sum = 0
        count = 0
        for char in chars:
            if count % 2 == 0:
                sum += int(char)
            else:
                sum += 3 * int(char)
            count += 1
        check = 10 - (sum % 10)
        if check == 10:
            return "0"
        else:
            return str(check)

    @staticmethod
    def isI13(isbn):
        """Checks the validity of an ISBN-13 number."""
        short = _ISBNConvert.isbn_strip(isbn)
        if len(short) != 13:
            return False
        chars = list(short)
        sum = 0
        count = 0
        for char in chars:
            if count % 2 == 0:
                sum += int(char)
            else:
                sum += 3 * int(char)
            count += 1
        remainder = sum % 10
        if remainder == 0:
            return True
        else:
            return False

    @staticmethod
    def toI10(isbn):
        """Converts supplied ISBN (either ISBN-10 or ISBN-13) to a stripped ISBN-10."""
        if not isbn:
            raise Exception('Invalid ISBN')
        if not _ISBNConvert.isValid(isbn):
            raise Exception("Invalid ISBN")
        if _ISBNConvert.isI10(isbn):
            return _ISBNConvert.isbn_strip(isbn)
        else:
            return _ISBNConvert.convert(isbn)

    @staticmethod
    def toI13(isbn):
        """Converts supplied ISBN (either ISBN-10 or ISBN-13) to a stripped ISBN-13.
        :param isbn: unicode
        :return: unicode
        """
        if not isbn:
            raise Exception('Invalid ISBN')
        if not _ISBNConvert.isValid(isbn):
            raise Exception("Invalid ISBN")
        if _ISBNConvert.isI13(isbn):
            return _ISBNConvert.isbn_strip(isbn)
        else:
            return _ISBNConvert.convert(isbn)



class _LXMLWrapper(object):
    def __init__(self, response):
        self.parsed_response = objectify.fromstring(response)

    def to_string(self):
        """Convert Item XML to string.

        :return:
            A string representation of the Item xml.
        """
        return etree.tostring(self.parsed_response, pretty_print=True)

    def _safe_get_element(self, path, root=None):
        """Safe Get Element.

        Get a child element of root (multiple levels deep) failing silently
        if any descendant does not exist.

        :param root:
            Lxml element.
        :param path:
            String path (i.e. u'Items.Item.Offers.Offer').
        :return:
            Element or None.
        """
        elements = path.split(u'.')
        parent = root if root is not None else self.parsed_response
        for element in elements[:-1]:
            parent = getattr(parent, element, None)
            if parent is None:
                return None
        return getattr(parent, elements[-1], None)

    def _safe_get_element_text(self, path, root=None):
        # type: (Element, (unicode or None)) -> unicode or None
        """Safe get element text.

        Get element as string or None,
        :rtype: Text or None
        :param root: Lxml element.
        :param path: String path (i.e. u'Items.Item.Offers.Offer').
        :return: unicode or None
        """
        element = self._safe_get_element(path, root)
        if element is not None and hasattr(element, 'text') and element.text is not None:
            if isinstance(element.text, str) or isinstance(element.text, unicode):
                return element.text.strip()
        else:
            return None

    def _safe_get_element_date(self, path, root=None):
        """Safe get elemnent date.

        Get element as datetime.date or None,
        :param root:
            Lxml element.
        :param path:
            String path (i.e. u'Items.Item.Offers.Offer').
        :return:
            datetime.date or None.
        """
        value = self._safe_get_element_text(path=path, root=root)
        if value is not None:
            try:
                from datetime import datetime
                value = datetime.strptime(value, u'%Y-%m-%d')
                if value:
                    value = value.date()
            except ValueError:
                value = None

        return value


class _GoodreadsBook(_LXMLWrapper):
    """A wrapper class for an BottlenoseAmazon product.
    """

    def __init__(self, item, tags_threshold):
        self.tags_threshold = tags_threshold
        super(_GoodreadsBook, self).__init__(item)

    @property
    def title(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.title')

    @property
    def authors(self):
        """
        :return: list(unicode) or list(str): book authors
        """
        # type: () -> list(unicode) or list(str)
        return [author.name.text for author in self._safe_get_element('book.authors.author')]

    @property
    def asin(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.kindle_asin') or self._safe_get_element_text('book.asin')

    @property
    def isbn(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.isbn13') or self._safe_get_element_text('book.isbn')

    @property
    def id(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.id')

    @property
    def language(self):
        # type: () -> unicode or str or None
        if self._safe_get_element_text('book.language_code') and self._safe_get_element_text('book.language_code') == 'en-US':
            return 'eng'
        else:
            return None

    @property
    def image_url(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.image_url')

    @property
    def publisher(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.publisher')

    @property
    def comments(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.description')

    @property
    def average_rating(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.average_rating')

    @property
    def tags(self):
        # type: () -> list(unicode) or list(str)
        return [shelf.attrib['name'] for shelf in self._safe_get_element('book.popular_shelves.shelf') if
                int(shelf.attrib['count']) >= self.tags_threshold]

    @property
    def series(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.series_works.series_work.series.title')

    @property
    def series_index(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.series_works.series_work.user_position')

    @property
    def num_pages(self):
        # type: () -> unicode or str or None
        return self._safe_get_element_text('book.num_pages')

    @property
    def pubdate(self):
        # type: () -> datetime.date or None
        year = self._safe_get_element_text('book.work.original_publication_year')
        month = self._safe_get_element_text('book.work.original_publication_month')
        day = self._safe_get_element_text('book.work.original_publication_day')
        if year and month and day:
            return  datetime.date(int(year), int(month), int(day))
        return None


class GoodreadsAPI(Source):
    name = 'GoodreadsAPI'
    description = 'GoodreadsAPI'
    author = 'botmtl'
    version = (0, 0, 1)
    minimum_calibre_version = (0, 8, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(
        ['title', 'authors', 'identifier:goodreads', 'identifier:amazon', 'identifier:isbn', 'rating', 'comments',
         'publisher', 'pubdate',
         'tags', 'series'])
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    MAX_EDITIONS = 5
    GOODREADS_API_KEY = 'GOODREADS_API_KEY'
    BASE_URL = 'https://www.goodreads.com'
    ISBN_TO_BOOKID = 'https://www.goodreads.com/book/isbn_to_id/{0}?key={1}'
    BOOK_SHOW = 'https://www.goodreads.com/book/show/{0}.xml?key={1}'
    BOOK_SHOW_ISBN = 'https://www.goodreads.com/book/isbn/{0}.xml?key={1}'
    DISABLE_TITLE_AUTHOR_SEARCH=False

    #options = [Option(u'GOODREADS_API_KEY', u'string', u'', u'GOODREADS_API_KEY', u'GOODREADS_API_KEY'),
    #           Option(u'DISABLE_TITLE_AUTHOR_SEARCH', u'bool', False, u'DISABLE_TITLE_AUTHOR_SEARCH:', u'DISABLE_TITLE_AUTHOR_SEARCH')]

    def __init__(self, *args, **kwargs):
        """

        Args:
            args:
            kwargs:
        """
        Source.__init__(self, *args, **kwargs)

    # def is_configured(self):
    #     # type: () -> bool
    #     """
    #     :return: False if your plugin needs to be configured before it can be used. For example, it might need a username/password/API key.
    #     :rtype: bool
    #     """
    #     if 'f9c3KJCkdBVktDF6WuCy3w':
    #         return True
    #
    #     return False

    def _clean_title(self, title):
        # type: (unicode) -> unicode
        """
        :param title: Text: title
        :return: Text: cleaned-up title
        """
        title = re.sub('\(.*?\)', '', title)
        title = re.sub('\[.*?\]', '', title)
        return titlecase(title)

    def get_cached_cover_url(self, identifiers):
        url = None
        goodreads_id = identifiers.get('goodreads', None)
        if goodreads_id is None:
            isbn = identifiers.get('isbn', None)
            if isbn is not None:
                goodreads_id = self.cached_isbn_to_identifier(isbn)
        if goodreads_id is not None:
            url = self.cached_identifier_to_cover_url(goodreads_id)

        return url

    def clean_downloaded_metadata(self, mi):
        """
        Overridden from the calibre default so that we can stop this plugin messing
        with the tag casing coming from Goodreads
        """
        docase = mi.language == 'eng' or mi.is_null('language')

        if docase and mi.title:
            mi.title = fixcase(mi.title)

        mi.authors = fixauthors(mi.authors)
        try:
            from calibre.utils.config import JSONConfig
            plugin_prefs = JSONConfig('plugins/Quality Check')
            from calibre_plugins.quality_check.config import STORE_OPTIONS, KEY_AUTHOR_INITIALS_MODE, \
                AUTHOR_INITIALS_MODES
            initials_mode = plugin_prefs[STORE_OPTIONS].get(KEY_AUTHOR_INITIALS_MODE, AUTHOR_INITIALS_MODES[0])
            from quality_check.helpers import get_formatted_author_initials
            mi.authors = [get_formatted_author_initials(initials_mode, author) for author in mi.authors]
        except:
            pass

        try:
            mi.isbn = check_isbn(_ISBNConvert.toI13(mi.isbn))
        except:
            pass

    def autocomplete_api(self, search_terms, timeout, log):
        # type: (unicode, int, ThreadSafeLog) -> dict or None
        """
        :param timeout: int: urlopen will raise an exception
        (caught in get_goodreads_id_from_autocomplete) after this time
        :param search_terms: unicode: search term(s)
        :param log: ThreadSafeLog: logging utility
        :return: dict: a dictionnary representing the first book found by the api.
        """
        from urllib2 import urlopen
        import json
        search_terms = search_terms.strip()
        if search_terms is None: return None

        autocomplete_api_url = "https://www.goodreads.com/book/auto_complete?format=json&q="
        log.info('autocomplete url:', autocomplete_api_url, search_terms)
        response = urlopen(autocomplete_api_url + search_terms, timeout=timeout).read()
        if response:
            result = json.loads(response)
            if len(result) >= 1:
                return result[0]['bookId']
        return None

    def identify(self, log, result_queue, abort, title=None, authors=None,
                 identifiers={}, timeout=30):
        """
        Note this method will retry without identifiers automatically if no
        match is found with identifiers.
        """
        if not identifiers: identifiers = {}
        # Unlike the other metadata sources, if we have a goodreads id then we
        # do not need to fire a "search" at Goodreads.com. Instead we will be
        # able to go straight to the URL for that book.
        # By using the autocomplete api, the previous comment is true for any book
        # having an identifier that is either goodreads_id, isbn or amazon
        goodreads_id = None
        print('test')
        if identifiers.get('amazon'):
            request = GoodreadsAPI.ISBN_TO_BOOKID.format(identifiers.get('amazon'), 'f9c3KJCkdBVktDF6WuCy3w')
            goodreads_id = urlopen(request).read()
        if not goodreads_id and identifiers.get('goodreads'):
            goodreads_id = identifiers.get('goodreads')
        if not goodreads_id and identifiers.get('isbn'):
            request = GoodreadsAPI.ISBN_TO_BOOKID.format(identifiers.get('isbn'), 'f9c3KJCkdBVktDF6WuCy3w')
            goodreads_id = urlopen(request).read()

        if not goodreads_id and title and not self.DISABLE_TITLE_AUTHOR_SEARCH:
            goodreads_id = self.autocomplete_api(' '.join(self.get_title_tokens(title)) + ' '.join(self.get_author_tokens(authors)), 10,
                                                 log)

        if goodreads_id:
            request_book = GoodreadsAPI.BOOK_SHOW.format(goodreads_id, 'f9c3KJCkdBVktDF6WuCy3w')
            response = urlopen(request_book).read()
            mi=self.GoodreadsBook_to_Metadata(_GoodreadsBook(response, 2))
            result_queue.put(mi)

        return None

    def GoodreadsBook_to_Metadata(self, book):
        # type: (_GoodreadsBook) -> Metadata
        """
        :param book: _GoodreadsBook: book
        :return: Metadata: Metadata
        """
        mi = Metadata(book.title, book.authors)
        mi.source_relevance = 0
        mi.set_identifier('goodreads', book.id)

        if book.asin:
            mi.set_identifier('amazon', book.asin)

        if book.isbn:
            mi.set_identifier('isbn', _ISBNConvert.toI13(book.isbn))

        if book.image_url:
            # self.log.info(u'cache_identifier_to_cover_url:' + book.asin + u',' + book.large_image_url)
            self.cache_identifier_to_cover_url(book.id, book.image_url)

        if book.publisher:
            # self.log.info(u'book.publisher is:', book.publisher)
            mi.publisher = book.publisher

        if book.pubdate:
            # self.log.info(u'book.publication_date is:', book.publication_date.strftime(u'%Y-%m-%d'))
            mi.pubdate = book.pubdate

        if book.comments:
            # self.log.info(u'book.editorial_review is:', book.editorial_review)
            mi.comments = book.comments

        if len(book.tags) > 0:
            mi.tags = book.tags

        if book.series and book.series_index:
            # self.log.info(u'series:', series_name, u' ', series_index)
            mi.series = book.series
            mi.series_index = book.series_index

        self.clean_downloaded_metadata(mi)
        return mi

    def download_cover(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30,
                       get_best_cover=False):
        """

        :param log: ThreadSafeLog: log
        :param result_queue: Queue: result queue
        :param abort: Event: abort
        :param title: str: Title to search for
        :param authors: list(str): authors
        :param identifiers: list(str): list identifiers
        :param timeout: int: timeout
        :param get_best_cover: bool: get best cover
        :return:
        """
        pass


if __name__ == '__main__':  # tests
    # To run these test use:
    # calibre-debug -e __init__.py
    from calibre.ebooks.metadata.sources.test import (test_identify_plugin,
                                                      title_test, authors_test, series_test)

    test_identify_plugin(GoodreadsAPI.name,
                         [
                             (  # A book with an ISBN
                                 {'identifiers': {'isbn': '9780385340588'}},
                                 [title_test('61 Hours', exact=True),
                                  authors_test(['Lee Child']),
                                  series_test('Jack Reacher', 14.0)]
                             )
                         ])
