"""
#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
"""
from __future__ import (absolute_import, division, print_function, unicode_literals)

import re
# noinspection PyUnresolvedReferences
import sys
import traceback
from Queue import Queue
from threading import Event
from urllib2 import urlopen

# noinspection PyUnresolvedReferences
from lxml import etree, objectify
# noinspection PyUnresolvedReferences
from lxml.etree import Element

from calibre.ebooks.metadata import check_isbn13
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Option, Source, fixauthors, fixcase
from calibre.utils.config import JSONConfig
from calibre.utils.logging import ThreadSafeLog

try:
    from typing import List, AnyStr, Any, Dict, FrozenSet, Text
except:
    pass

__license__ = 'GPL v3'
__copyright__ = '2017, botmtl@gmail.com'
__docformat__ = 'restructuredtext en'

class _ISBNConvert(object):

    @staticmethod
    def _isbn_strip(isbn):
        """Strip whitespace, hyphens, etc. from an ISBN number and return
    the result."""
        short = re.sub("\W", "", isbn)
        return re.sub("\D", "X", short)

    @staticmethod
    def convert(isbn):
        """Convert an ISBN-10 to ISBN-13 or vice-versa."""
        short = _ISBNConvert._isbn_strip(isbn)
        if not _ISBNConvert.isValid(short):
            raise Exception("Invalid ISBN")
        if len(short) == 10:
            stem = "978" + short[:-1]
            return stem + _ISBNConvert._check(stem)
        else:
            if short[:3] == "978":
                stem = short[3:-1]
                return stem + _ISBNConvert._check(stem)
            else:
                raise Exception("ISBN not convertible")

    @staticmethod
    def isValid(isbn):
        """Check the validity of an ISBN. Works for either ISBN-10 or ISBN-13."""
        short = _ISBNConvert._isbn_strip(isbn)
        if len(short) == 10:
            return _ISBNConvert.isI10(short)
        elif len(short) == 13:
            return _ISBNConvert.isI13(short)
        else:
            return False

    @staticmethod
    def _check(stem):
        """Compute the check digit for the stem of an ISBN. Works with either
        the first 9 digits of an ISBN-10 or the first 12 digits of an ISBN-13."""
        short = _ISBNConvert._isbn_strip(stem)
        if len(short) == 9:
            return _ISBNConvert.checkI10(short)
        elif len(short) == 12:
            return _ISBNConvert._checkI13(short)
        else:
            return False

    @staticmethod
    def checkI10(stem):
        """Computes the ISBN-10 check digit based on the first 9 digits of a stripped ISBN-10 number."""
        chars = list(stem)
        sum_isbn = 0
        digit = 10
        for char in chars:
            sum_isbn += digit * int(char)
            digit -= 1
        check = 11 - (sum_isbn % 11)
        if check == 10:
            return "X"
        elif check == 11:
            return "0"
        else:
            return str(check)

    @staticmethod
    def isI10(isbn):
        """Checks the validity of an ISBN-10 number."""
        short = _ISBNConvert._isbn_strip(isbn)
        if len(short) != 10:
            return False
        chars = list(short)
        sum_isbn = 0
        digit = 10
        for char in chars:
            if char == 'X' or char == 'x':
                char = "10"
            sum_isbn += digit * int(char)
            digit -= 1
        remainder = sum_isbn % 11
        if remainder == 0:
            return True
        else:
            return False

    @staticmethod
    def _checkI13(stem):
        """Compute the ISBN-13 check digit based on the first 12 digits of a stripped ISBN-13 number. """
        chars = list(stem)
        sum_isbn = 0
        count = 0
        for char in chars:
            if count % 2 == 0:
                sum_isbn += int(char)
            else:
                sum_isbn += 3 * int(char)
            count += 1
        check = 10 - (sum_isbn % 10)
        if check == 10:
            return "0"
        else:
            return str(check)

    @staticmethod
    def isI13(isbn):
        """Checks the validity of an ISBN-13 number."""
        short = _ISBNConvert._isbn_strip(isbn)
        if len(short) != 13:
            return False
        chars = list(short)
        sum_isbn = 0
        count = 0
        for char in chars:
            if count % 2 == 0:
                sum_isbn += int(char)
            else:
                sum_isbn += 3 * int(char)
            count += 1
        remainder = sum_isbn % 10
        if remainder == 0:
            return True
        else:
            return False

    @staticmethod
    def _toI10(isbn):
        """Converts supplied ISBN (either ISBN-10 or ISBN-13) to a stripped ISBN-10."""
        if not isbn:
            raise Exception('Invalid ISBN')
        if not _ISBNConvert.isValid(isbn):
            raise Exception("Invalid ISBN")
        if _ISBNConvert.isI10(isbn):
            return _ISBNConvert._isbn_strip(isbn)
        else:
            return _ISBNConvert.convert(isbn)

    @staticmethod
    def _toI13(isbn):
        """Converts supplied ISBN (either ISBN-10 or ISBN-13) to a stripped ISBN-13.
        :param isbn: unicode
        :return: unicode
        """
        if not isbn:
            raise Exception('Invalid ISBN')
        if not _ISBNConvert.isValid(isbn):
            raise Exception("Invalid ISBN")
        if _ISBNConvert.isI13(isbn):
            return _ISBNConvert._isbn_strip(isbn)
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
            String path (i.e. 'Items.Item.Offers.Offer').
        :return:
            Element or None.
        """
        elements = path.split('.')
        parent = root if root is not None else self.parsed_response
        for element in elements[:-1]:
            parent = getattr(parent, element, None)
            if parent is None:
                return None
        return getattr(parent, elements[-1], None)

    def _safe_get_element_text(self, path, root=None):
        # type: (Element, (unicode or None)) -> Text or None
        """Safe get element text.

        Get element as string or None,
        :rtype: Text or None
        :param root: Lxml element.
        :param path: String path (i.e. 'Items.Item.Offers.Offer').
        :return: unicode or None
        """
        element = self._safe_get_element(path, root)
        if element is not None and hasattr(element, 'text') and element.text is not None and len(element.text) > 0:
            if isinstance(element.text, str) or isinstance(element.text, unicode):
                return unicode(element.text.strip())
        else:
            return None

    def _safe_get_element_date(self, path, root=None):
        """Safe get elemnent date.

        Get element as datetime.date or None,
        :param root:
            Lxml element.
        :param path:
            String path (i.e. 'Items.Item.Offers.Offer').
        :return:
            datetime.date or None.
        """
        value = self._safe_get_element_text(path=path, root=root)
        if value is not None and value:
            try:
                from datetime import datetime
                value = datetime.strptime(value, '%Y-%m-%d')
                if value is not None:
                    value = value.date()
            except ValueError:
                value = None

        return value

class _GoodreadsBook(_LXMLWrapper):
    """A wrapper class for an BottlenoseAmazon product.
    """

    def __init__(self, unparsedBook, tags_threshold=2):
        self.tags_threshold = tags_threshold
        super(_GoodreadsBook, self).__init__(unparsedBook)

    @property
    def title(self):
        """
        :return: Text or None: title
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.title')

    @property
    def authors(self):
        """
        :return: list(unicode) or list(str): book authors
        """
        # type: () -> list
        return [author.name.text for author in self._safe_get_element('book.authors.author')]

    @property
    def asin(self):
        """

        :return: Text or None: asin
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.kindle_asin') or self._safe_get_element_text('book.asin')

    @property
    def isbn(self):
        """
        :return: Text or None: isbn
        """
        # type: () -> Text or None
        return unicode(self._safe_get_element_text('book.isbn13')) or unicode(self._safe_get_element_text('book.isbn'))

    @property
    def id(self):
        """
        :return: Text or None: id
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.id')

    @property
    def language(self):
        """
        :return: Text or None: language
        """
        # type: () -> Text or None
        if self._safe_get_element_text('book.language_code') and self._safe_get_element_text('book.language_code') == 'en-US':
            return 'eng'
        else:
            return None

    @property
    def image_url(self):
        """
        :return: Text or None: image url
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.image_url')

    @property
    def publisher(self):
        """

        :return: Text or None: publisher
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.publisher')

    @property
    def comments(self):
        """

        :return: Text or None: comments
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.description')

    @property
    def average_rating(self):
        """
        :return: float or None: rating
        """
        # type: () -> float or None
        try:
            return float(self._safe_get_element_text('book.average_rating'))
        except:
            pass
        return None

    @property
    def tags(self):
        """
        :return: list(): tags
        """
        # type: () -> list()
        tags = []
        shelf = self._safe_get_element('book.popular_shelves.shelf')
        if shelf is not None:
            try:
                for shelf in self._safe_get_element('book.popular_shelves.shelf'):
                    if int(shelf.attrib['count']) >= self.tags_threshold:
                        tags.append(shelf.attrib['name'])
            except:
                pass
        return tags

    @property
    def series(self):
        """
        :return: Text or None: series name
        """
        # type: () -> Text or None
        return self._safe_get_element_text('book.series_works.series_work.series.title')

    @property
    def series_index(self):
        """
        :return: float or None: series index
        """
        # type: () -> float or None
        try:
            return float(self._safe_get_element_text('book.series_works.series_work.user_position'))
        except:
            pass
        return None

    @property
    def num_pages(self):
        """
        :return: Text or None: number of pages
        """
        # type: () -> Text or None
        try:
            return int(self._safe_get_element_text('book.num_pages'))
        except:
            pass
        return None

    @property
    def pubdate(self):
        """
        :return: datetime.date or None: publication date
        """
        # type: () -> datetime.date or None
        year = self._safe_get_element_text('book.work.original_publication_year')
        month = self._safe_get_element_text('book.work.original_publication_month')
        day = self._safe_get_element_text('book.work.original_publication_day')
        if year and month and day:
            try:
                from datetime import datetime
                from datetime import date
                return datetime.combine(date(int(year), int(month), int(day)), datetime.min.time())
            except:
                pass
        return None

    def to_string(self):
        """

        :return:
        """
        # type: () -> Text
        return "title:{0}; authors:{1}; series:{2}; series_index:{3}; asin:{4}; isbn:{5}".format(self.title, ' '.join(self.authors), self.series, self.series_index, self.asin,
                                                                                                 self.isbn)

class GoodreadsAPI(Source):
    """
    Goodreads API
    """
    name = 'GoodreadsAPI'
    description = 'GoodreadsAPI'
    author = 'botmtl'
    version = (0, 0, 2)
    minimum_calibre_version = (0, 8, 1)
    capabilities = frozenset(['identify'])
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    BASE_URL = 'https://www.goodreads.com'
    ISBN_TO_BOOKID = 'https://www.goodreads.com/book/isbn_to_id/{0}?key={1}'
    BOOK_SHOW = 'https://www.goodreads.com/book/show/{0}.xml?key={1}'
    BOOK_SHOW_ISBN = 'https://www.goodreads.com/book/isbn/{0}.xml?key={1}'
    # name, type_, default, label, desc, choices=None
    options = [Option(name='GOODREADS_API_KEY', type_='string', default='', label='GOODREADS_API_KEY', desc='GOODREADS_API_KEY'),
               Option(name='SHELF_COUNT_THRESHOLD', type_='number', default=2, label='SHELF_COUNT_THRESHOLD:',
                      desc='How many shelves does this book have to be in to be considered a tag.'),
               Option(name='NEVER_REPLACE_AMAZONID', type_='bool', default=True, label='NEVER_REPLACE_AMAZONID:', desc='NEVER_REPLACE_AMAZONID'),
               Option(name='NEVER_REPLACE_ISBN', type_='bool', default=True, label='NEVER_REPLACE_ISBN:', desc='NEVER_REPLACE_ISBN'),
               Option(name='CHECK_AMAZONID_VALIDITY', type_='bool', default=True, label='CHECK_AMAZONID_VALIDITY:', desc='Not Implemented.'),
               Option(name='ADD_THESE_TAGS', type_='string', default='GoodreadsAPI', label='Additioal tags:',
                      desc='A comma separated list of tags to add on a sucessful metadata download.'),
               Option(u'DISABLE_TITLE_AUTHOR_SEARCH', u'bool', False, u'Disable title/author search:',
                      u'Only books with identifiers will have a chance for to find a match with the metadata provider.')]

    def __init__(self, *args, **kwargs):
        """
        Args:
            args:
            kwargs:
        """
        self.touched_fields = frozenset(
            ['title', 'authors', 'identifier:goodreads', 'identifier:amazon', 'identifier:isbn', 'rating', 'comments', 'publisher', 'pubdate', 'tags', 'series'])
        Source.__init__(self, *args, **kwargs)

    def is_configured(self):
        # type: () -> bool
        """
        :return: False if your plugin needs to be configured before it can be used. For example, it might need a username/password/API key.
        :rtype: bool
        """
        if self.prefs['GOODREADS_API_KEY']:
            return True

        return False

    def get_cached_cover_url(self, identifiers):
        """
        :param identifiers: list(unicode) or list(str)
        :return: Text: url
        """
        url = None
        if identifiers.get('goodreads'):
            url = self.cached_identifier_to_cover_url(identifiers.get('goodreads'))

        return url

    def clean_downloaded_metadata(self, mi):
        """
        Overridden from the calibre default so that we can stop this plugin messing
        with the tag casing coming from Goodreads
        """
        series_in_title = r'\s*{0}\s*#?{1}\s*'.format(mi.series, mi.series_index)
        if mi.title:
            mi.title = re.sub(series_in_title + r'[:-]', r'', mi.title, flags=re.IGNORECASE).strip()
            mi.title = re.sub(r'(?:[^:-]+)[:-]' + series_in_title, r'', mi.title, flags=re.IGNORECASE).strip()
            mi.title = re.sub(r'\(.*?\)', r'', mi.title, flags=re.IGNORECASE).strip()
            mi.title = re.sub(r'\[.*?\]', r'', mi.title, flags=re.IGNORECASE).strip()
            mi.title = fixcase(mi.title)
            mi.title = mi.title.strip()

        if mi.authors:
            mi.authors = fixauthors(mi.authors)
            try:
                plugin_prefs = JSONConfig('plugins/Quality Check')
                from calibre_plugins.quality_check.config import STORE_OPTIONS, KEY_AUTHOR_INITIALS_MODE, AUTHOR_INITIALS_MODES
                initials_mode = plugin_prefs[STORE_OPTIONS].get(KEY_AUTHOR_INITIALS_MODE, u'A. B.')
                from calibre_plugins.quality_check.helpers import get_formatted_author_initials
                mi.authors = [get_formatted_author_initials(initials_mode, author) for author in mi.authors]
            except:
                pass

    def _autocomplete_api(self, search_terms, timeout=10):
        # type: (Text, int) -> dict or None
        """
        :param timeout: int: urlopen will raise an exception
        :param search_terms: unicode: search term(s)
        :return: dict: a dictionnary representing the first book found by the api.
        """
        from urllib2 import urlopen
        import json
        search_terms = search_terms.strip()
        if search_terms is None: return None
        search_terms = search_terms.replace(' and ', ' ').replace(' or ', ' ').replace(' & ', ' ').replace('-', ' ')
        search_terms = search_terms.replace('  ', ' ')
        search_terms = search_terms.strip().replace(' ', '+')
        autocomplete_api_url = "https://www.goodreads.com/book/auto_complete?format=json&q="
        self.log.info('autocomplete url:', autocomplete_api_url, search_terms)
        response = urlopen(autocomplete_api_url + search_terms, timeout=timeout).read()
        if response is not None:
            result = json.loads(response)
            if len(result) >= 1:
                return result[0]['bookId']
        return None

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers=None, timeout=30):
        """

        :param log:
        :param result_queue:
        :param abort:
        :param title:
        :param authors:
        :param identifiers:
        :param timeout:
        :return:
        """
        if not identifiers: identifiers = {}
        goodreads_id = None
        # noinspection PyAttributeOutsideInit
        self.log = log
        if identifiers.get('amazon'):
            try:
                self.log.info('ISBN_TO_BOOKID', identifiers.get('amazon'))
                request = GoodreadsAPI.ISBN_TO_BOOKID.format(identifiers.get('amazon'), self.prefs['GOODREADS_API_KEY'])
                goodreads_id = urlopen(request).read()
            except:
                pass
        if not goodreads_id and identifiers.get('goodreads'):
            goodreads_id = identifiers.get('goodreads')
        if not goodreads_id and identifiers.get('isbn'):
            try:
                self.log.info('ISBN_TO_BOOKID', identifiers.get('isbn'))
                request = GoodreadsAPI.ISBN_TO_BOOKID.format(identifiers.get('isbn'), self.prefs['GOODREADS_API_KEY'])
                goodreads_id = urlopen(request).read()
            except:
                pass

        if not goodreads_id and title and not self.prefs['DISABLE_TITLE_AUTHOR_SEARCH']:
            self.log.info('AUTOCOMPLETEAPI:', ' '.join(self.get_title_tokens(title)) + ' ' + ' '.join(self.get_author_tokens(authors)))
            goodreads_id = self._autocomplete_api(' '.join(self.get_title_tokens(title)) + ' ' + ' '.join(self.get_author_tokens(authors)), 10)

        if goodreads_id:
            try:
                self.log.info('BOOK_SHOW ', goodreads_id)
                request_book = GoodreadsAPI.BOOK_SHOW.format(goodreads_id, self.prefs['GOODREADS_API_KEY'])
                response = urlopen(request_book).read()
                response = re.sub(re.compile(r'>\s+<', re.MULTILINE), '><', response)
                response = re.sub(re.compile(r'\r\n', re.MULTILINE), r'', response)
                mi = self._GoodreadsBook_to_Metadata(_GoodreadsBook(str(response), self.prefs['SHELF_COUNT_THRESHOLD']))
            except Exception as e:
                self.log.error(e.message)
                self.log.error(traceback.print_stack())
                traceback.print_exc()
                return

            self.clean_downloaded_metadata(mi)
            result_queue.put(mi)

        return None

    def _GoodreadsBook_to_Metadata(self, book):
        # type: (_GoodreadsBook) -> Metadata
        """
        :param book: _GoodreadsBook: book
        :return: Metadata: Metadata
        """
        mi = Metadata(book.title, book.authors)
        mi.source_relevance = 0
        mi.set_identifier('goodreads', book.id)

        if self.prefs['NEVER_REPLACE_ISBN'] and mi.get_identifiers().get('isbn'):
            mi.set_identifier('isbn', '')

        if book.asin and not self.prefs['NEVER_REPLACE_AMAZONID']:
            mi.set_identifier('amazon', book.asin)

        if book.isbn and not self.prefs['NEVER_REPLACE_ISBN']:
            try:
                if len(book.isbn) == 10:
                    mi.isbn = check_isbn13(_ISBNConvert.convert(book.isbn))
                else:
                    mi.isbn = check_isbn13(book.isbn)
            except:
                self.log.error("ISBN CONVERSION ERROR:", book.isbn)
                self.log.exception()

        if book.image_url:
            self.log.info('cache_identifier_to_cover_url:', book.asin, ':', book.image_url)
            self.cache_identifier_to_cover_url(book.id, book.image_url)

        if book.publisher:
            self.log.info('book.publisher is:', book.publisher)
            mi.publisher = book.publisher

        if book.pubdate:
            self.log.info('book.pubdate is:', book.pubdate.strftime('%Y-%m-%d'))
            mi.pubdate = book.pubdate

        if book.comments:
            self.log.info('book.editorial_review is:', book.comments)
            mi.comments = book.comments

        tags = self.prefs['ADD_THESE_TAGS'].split(',')
        tags.extend(book.tags)
        # tag_mappings = JSONConfig('plugins/GenreMappings')['genreMappings']
        # mi.tags = list(set(sorted(filter(lambda x: tag_mappings.get(x, x), tags))))

        if book.series:
            mi.series = book.series
            self.log.info(u'series:', book.series)
            if book.series_index:
                mi.series_index = book.series_index
                self.log.info(u'series_index:', "{0:.2f}".format(book.series_index))
            else:
                mi.series_index = 0

        if book.average_rating:
            mi.rating = book.average_rating

        self.clean_downloaded_metadata(mi)

        return mi

    def cli_main(self, args):
        """
        :type args: list
        :param args: args
        """
        pass

    # noinspection PyDefaultArgument
    def download_cover(self, log, result_queue, abort, title=None, authors=[], identifiers={}, timeout=30, get_best_cover=False):
        # type: (ThreadSafeLog, Queue, Event, Text, list(), dict(), int, bool) -> Text
        """
        Download a cover and put it into result_queue. The parameters all have
        the same meaning as for :meth:`identify`. Put (self, cover_data) into
        result_queue.

        This method should use cached cover URLs for efficiency whenever
        possible. When cached data is not present, most plugins simply call
        identify and use its results.

        If the parameter get_best_cover is True and this plugin can get
        multiple covers, it should only get the best one.
        :type result_queue: Queue
        :param log: ThreadSafeLog: log
        :param result_queue: Queue: results
        :param abort: Event: if is_set,abort
        :param title: Optional[unicode]: title
        :param authors: Optional[List]: authors
        :param timeout: int: timeout
        :param get_best_cover: bool:cover
        :return:
        :type identifiers: Optional[Dict]: identifiers
        """
        # noinspection PyAttributeOutsideInit
        self.log = log
        cached_url = self.get_cached_cover_url(identifiers)
        if cached_url is None:
            self.log.info(u'No cached cover found, running identify')
            try:
                rq = Queue()
                self.identify(self.log, rq, abort, title, authors, identifiers)
                cached_url = self.get_cached_cover_url(identifiers)
                if cached_url is None:
                    return u'Download cover failed.  Could not identify.'
            except Exception as e:
                return e.message

        if abort.is_set():
            return "abort"

        br = self.browser
        self.log.info(u'Downloading cover from:', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            self.log.error(u'Failed to download cover from:', cached_url)
            return u'Failed to download cover from:%s' % cached_url  # }}}

if __name__ == '__main__':  # tests
    # To run these test use:
    # calibre-debug -e __init__.py
    from calibre.ebooks.metadata.sources.test import (test_identify_plugin, title_test, authors_test)

    test_identify_plugin(GoodreadsAPI.name, [
        ({u'title': u'The Omega''s Fake Mate', u'authors': [u'Ann-Katrin Byrde']}, [title_test(u'Expert C# 2008 Business Objects'), authors_test([u'Rockford Lhotka'])])])
